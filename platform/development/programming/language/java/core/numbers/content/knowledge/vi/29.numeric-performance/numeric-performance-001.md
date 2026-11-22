# Primitive so với wrapper về cấp phát và bố trí dữ liệu trong Java

## 1. Vấn đề hiệu năng cần hiểu

Java phân biệt **kiểu nguyên thủy** (*primitive*) như `int`, `long`, `double` với các **lớp bao** (*wrapper*) như `Integer`, `Long`, `Double`.

Về mặt giá trị số học, một `int` chứa 100 và một `Integer` đại diện cho 100 có thể phục vụ cùng phép tính. Nhưng về mô hình dữ liệu, bố trí bộ nhớ và chi phí chạy, chúng không tương đương:

- Một biến hoặc ô mảng kiểu primitive biểu diễn **giá trị trực tiếp** theo kiểu đã khai báo; không yêu cầu một đối tượng wrapper riêng chỉ để giữ con số.
- Một biến hoặc ô mảng kiểu wrapper chứa **tham chiếu** tới đối tượng (hoặc `null`). Khi đối tượng wrapper thực sự được cấp phát, nó cần vùng lưu dữ liệu đối tượng bên cạnh giá trị số.
- Việc đổi giữa primitive và wrapper bằng **boxing/unboxing** có thể gây cấp phát đối tượng, tăng lượng dữ liệu phải đọc, tăng áp lực GC và tốn các bước chuyển đổi. Tuy nhiên, JVM có thể tái sử dụng wrapper hoặc tối ưu bỏ một số cấp phát; không thể mặc định *mỗi phép boxing luôn tạo một đối tượng mới*.

Bài này phân tích sự khác biệt về **cấp phát và bố trí dữ liệu**, cách nó ảnh hưởng đến thao tác trên tập số lớn, và cách chọn cấu trúc dữ liệu đúng. Đây là mô hình Java Core và những đặc trưng JVM cần hiểu để đo hiệu năng có căn cứ.

## 2. Primitive và wrapper tương ứng

| Primitive | Wrapper | Kích thước giá trị primitive theo Java | Đặc điểm |
| --- | --- | --- | --- |
| `byte` | `Byte` | 8 bit | Số nguyên có dấu |
| `short` | `Short` | 16 bit | Số nguyên có dấu |
| `int` | `Integer` | 32 bit | Số nguyên có dấu |
| `long` | `Long` | 64 bit | Số nguyên có dấu |
| `float` | `Float` | 32 bit | Số chấm động IEEE 754 |
| `double` | `Double` | 64 bit | Số chấm động IEEE 754 |
| `char` | `Character` | 16 bit | Đơn vị mã UTF-16 |
| `boolean` | `Boolean` | Không quy định một kích thước lưu trữ byte duy nhất trong mọi ngữ cảnh | Hai giá trị logic `true`, `false` |

Các số bit trong bảng áp dụng cho **miền giá trị/biểu diễn primitive**, **không phải kích thước một đối tượng wrapper**. Ví dụ `Integer` chứa một trường `int`, nhưng đối tượng `Integer` có thể cần thêm phần quản lý đối tượng của JVM. Kích thước đối tượng phụ thuộc JVM, kiến trúc, cấu hình nén tham chiếu và căn chỉnh.

Ví dụ về kiểu:

```java
int direct = 42;
Integer reference = Integer.valueOf(42);

int[] directArray = {10, 20, 30};
Integer[] referenceArray = {10, 20, 30};
```

`direct` mang giá trị `42` theo kiểu `int`; `reference` là tham chiếu có kiểu `Integer`. Với dữ liệu số học số lượng lớn, sự khác biệt thường rõ nhất ở **mảng primitive** so với **mảng wrapper** hoặc collection lưu wrapper.

## 3. Bố trí bộ nhớ của int[] và Integer[]

### 3.1. int[]: phần tử giá trị nguyên thủy nằm ngay trong mảng

`int[] values = new int[4]` tạo **một đối tượng mảng** chứa bốn ô `int`. Phần dữ liệu phần tử của mảng chiếm tổng cộng `4 × 4 = 16` byte cho bốn giá trị `int`, **chưa tính header và padding của đối tượng mảng**.

Sơ đồ logic:

```text
Biến values
      |
      v
+-----------------------------------------+
| int[]: header | 10 | 20 | 30 | 40 | ...  |
+-----------------------------------------+
                4B   4B   4B   4B
```

Các ô phần tử nằm liên tiếp trong vùng phần tử của một đối tượng mảng. JVM có thể quét dữ liệu tuần tự với locality tốt, nhiều giá trị nằm trong cùng cache line. Không có **đối tượng `Integer` riêng** chỉ để giữ từng phần tử.

Lưu ý: `int[]` vẫn là **đối tượng** trong Java. Tuyên bố “primitive luôn nằm trên stack” là sai. Nơi dữ liệu được đặt vật lý do JVM quyết định; một biến cục bộ kiểu primitive có thể nằm trong thanh ghi, stack frame hoặc bị tối ưu, còn phần tử `int[]` thuộc dữ liệu của đối tượng mảng.

### 3.2. Integer[]: mảng lưu tham chiếu, giá trị nằm trong wrapper

`Integer[] values = new Integer[4]` tạo **một đối tượng mảng gồm bốn tham chiếu**. Ban đầu cả bốn tham chiếu là `null`. Để lưu các giá trị số, chương trình phải có các đối tượng `Integer` được tham chiếu.

Sơ đồ logic (không thể hiện kích thước thực tế):

```text
Biến values
      |
      v
+-----------------------------------+
| Integer[] header | ref | ref | ref |
+--------------------|-----|-----|--+
                     |     |     |
                     v     v     v
                  +----+ +----+ +----+
                  |1000| |2000| |3000|
                  +----+ +----+ +----+
                  Mỗi ô là một đối tượng Integer
                  nếu không được tái sử dụng/tối ưu
```

Các tham chiếu nằm liên tiếp trong mảng, nhưng các đối tượng wrapper mà chúng trỏ tới **không được Java bảo đảm nằm sát nhau**. Khi duyệt mảng, CPU có thể cần truy cập thêm vùng dữ liệu theo các tham chiếu, làm giảm locality so với `int[]`. Các wrapper vẫn cần được tính là đối tượng có thể được GC quản lý nếu chúng tồn tại thực sự trong heap.

Đối với ví dụ:

```java
int[] primitive = {1000, 2000, 3000};
Integer[] boxed = {1000, 2000, 3000};
```

- Cả hai đều là **một mảng** và có `length = 3`.
- Mảng `primitive` chứa trực tiếp ba giá trị `int`.
- Mảng `boxed` chứa ba tham chiếu `Integer`; cú pháp gán số nguyên vào `Integer[]` kích hoạt autoboxing. Các đối tượng tương ứng có thể đã tồn tại, được tạo mới, hoặc được JVM tối ưu theo ngữ cảnh.
- Không được tính `Integer[]` như “12 byte dữ liệu cho ba số” vì nó chứa **tham chiếu**, còn dữ liệu số thuộc wrapper.

### 3.3. Mô hình ước lượng, không phải con số tuyệt đối

Với `N` phần tử kiểu `int`:

- `int[]`: phần dữ liệu phần tử là **`4 × N` byte**, cộng một header mảng và padding.
- `Integer[]`: phần dữ liệu mảng là **`N × kích thước tham chiếu`**, cộng header mảng; ngoài ra có dữ liệu của các **wrapper phân biệt thực sự còn tồn tại**, mỗi wrapper có header, trường `int`, padding và có thể được dùng chung giữa nhiều ô.
- `ArrayList<Integer>`: ngoài đối tượng danh sách và backing array của tham chiếu, còn có wrapper cho các phần tử được lưu, nếu không dùng chung; backing array có thể có capacity lớn hơn size.

Không có một con số “mỗi `Integer` chính xác 16 byte trên mọi JVM” hoặc “tham chiếu luôn 8 byte”. Ví dụ, một HotSpot 64 bit thường có thể dùng **compressed ordinary object pointers** (compressed oops) để lưu tham chiếu nhỏ hơn kích thước con trỏ máy; thiết lập nén tham chiếu, header, alignment và cấu hình khác sẽ thay đổi kết quả thực tế.

Phép so sánh có ích là **cấu trúc cấp phát và số lần theo tham chiếu**, sau đó đo bằng công cụ phù hợp trên JVM ứng dụng.

## 4. Autoboxing/unboxing và chi phí ẩn

**Boxing** chuyển primitive thành wrapper. **Unboxing** lấy primitive từ wrapper. Java thường tự chèn các chuyển đổi này:

```java
int a = 7;
Integer b = a; // autoboxing: tương đương Integer.valueOf(a)
int c = b;     // unboxing: tương đương b.intValue()
```

Điểm quan trọng:

1. `Integer.valueOf(int)` có thể trả lại đối tượng đã cache thay vì tạo đối tượng mới.
2. Java bắt buộc hỗ trợ vùng cache nhất định, bao gồm giá trị `Integer` trong khoảng **-128 đến 127** với boxing/`valueOf`; giá trị ngoài vùng có thể có chiến lược tái sử dụng khác tùy JVM.
3. Với wrapper được tạo mới nhưng không “thoát” ra khỏi một phạm vi tối ưu, JIT có thể loại bỏ cấp phát hoặc phép boxing bằng các kỹ thuật như escape analysis và scalar replacement. Đây là **khả năng tối ưu**, không phải cam kết về mọi đường chạy.
4. Unboxing `null` gây `NullPointerException`.
5. Khi boxing diễn ra trên hàng triệu phần tử không tận dụng cache hoặc tối ưu, lượng cấp phát có thể đáng kể.

Ví dụ:

```java
Integer smallA = Integer.valueOf(127);
Integer smallB = Integer.valueOf(127);
System.out.println(smallA == smallB);       // true: cùng đối tượng cached

Integer largeA = Integer.valueOf(1000);
Integer largeB = Integer.valueOf(1000);
System.out.println(largeA.equals(largeB)); // true: cùng giá trị
// Không dựa vào largeA == largeB: chiến lược cache có thể thay đổi.
```

Toán tử `==` với **hai tham chiếu `Integer`** so sánh danh tính đối tượng, còn `equals()` so sánh giá trị `int` mà wrapper chứa. Khi một bên là `int`, Java có thể unbox bên còn lại rồi so sánh số học, khiến code dùng `==` có ngữ nghĩa khác theo kiểu toán hạng. Nên dùng `equals()` khi chủ ý so sánh hai wrapper theo giá trị, và kiểm tra `null` khi cần.

## 5. Chương trình Java 17 độc lập, có đầu ra kiểm chứng

Tạo tệp **`PrimitiveWrapperLayoutDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class PrimitiveWrapperLayoutDemo {
    public static void main(String[] args) {
        int[] primitive = {1000, 2000, 3000};
        Integer[] wrapper = {1000, 2000, 3000};

        System.out.println("primitiveType=" + primitive.getClass().getName());
        System.out.println("wrapperType=" + wrapper.getClass().getName());
        System.out.println("primitiveSum=" + Arrays.stream(primitive).sum());
        System.out.println("wrapperSum=" + Arrays.stream(wrapper)
                .mapToInt(Integer::intValue).sum());

        List<Integer> list = new ArrayList<>();
        for (int number : primitive) {
            list.add(number);
        }
        System.out.println("listSum=" + list.stream()
                .mapToInt(Integer::intValue).sum());

        int[] zeroDefaults = new int[2];
        Integer[] nullDefaults = new Integer[2];
        System.out.println("primitiveDefault=" + zeroDefaults[0]);
        System.out.println("wrapperDefault=" + nullDefaults[0]);

        Integer first = Integer.valueOf(127);
        Integer second = Integer.valueOf(127);
        System.out.println("cachedIdentity=" + (first == second));
        System.out.println("cachedEquality=" + first.equals(second));

        Integer[] nullable = {1, null, 3};
        System.out.println("wrapperCanContainNull="
                + Arrays.asList(nullable).contains(null));
        try {
            int invalid = nullable[1];
            System.out.println(invalid);
        } catch (NullPointerException exception) {
            System.out.println("unboxNull=NullPointerException");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac PrimitiveWrapperLayoutDemo.java
java PrimitiveWrapperLayoutDemo
```

Kết quả đã chạy kiểm chứng với `javac --release 17`:

```text
primitiveType=[I
wrapperType=[Ljava.lang.Integer;
primitiveSum=6000
wrapperSum=6000
listSum=6000
primitiveDefault=0
wrapperDefault=null
cachedIdentity=true
cachedEquality=true
wrapperCanContainNull=true
unboxNull=NullPointerException
```

Giải thích từng nhóm:

- `[I` là tên runtime của mảng `int[]`; `[Ljava.lang.Integer;` là tên runtime của mảng tham chiếu `Integer[]`. Tên dạng này xuất hiện ở `Class.getName()` theo quy ước JVM.
- Ba đường tính tổng đều cho 6000. Kết quả số học bằng nhau **không có nghĩa** ba cấu trúc dữ liệu được lưu với cùng lượng bộ nhớ hoặc tốc độ.
- `new int[2]` khởi tạo phần tử về `0`; `new Integer[2]` khởi tạo phần tử về `null`.
- Hai lời gọi `Integer.valueOf(127)` trả cùng đối tượng trong vùng cache bảo đảm; cả `==` và `equals()` đều trả true ở ví dụ này.
- `Integer[]` có thể lưu `null`. Đưa `null` qua phép chuyển thành `int` gây `NullPointerException`.
- Chương trình không tự đo heap vì phép kiểm tra `Runtime.totalMemory() - freeMemory()` trước/sau một vòng lặp nhỏ không phải phép đo tin cậy cho kích thước đối tượng; GC, JIT và các cấp phát khác ảnh hưởng số liệu.

## 6. ArrayList<Integer> so với int[] trong tập dữ liệu lớn

Khi cần một triệu số:

```java
int[] raw = new int[1_000_000];

List<Integer> items = new ArrayList<>();
// items.add(number) sẽ boxing nếu number có kiểu int.
```

**Mảng primitive**:
- Dữ liệu `int` ở các ô liên tiếp, cho locality tốt khi duyệt tuần tự.
- Không có trường hợp phần tử `null`.
- Có độ dài cố định; không tự tăng kích thước.
- Có thể đổi giá trị tại chỉ số trực tiếp, không cần boxing.

**`ArrayList<Integer>`**:
- Danh sách quản lý một backing array chứa tham chiếu, capacity có thể lớn hơn số phần tử thực.
- Các phần tử biểu diễn bằng `Integer`, có thể có những đối tượng wrapper được dùng chung, tái sử dụng hoặc riêng lẻ.
- Cung cấp API `List` linh hoạt, tăng/giảm kích thước, tích hợp Collections/Generics.
- Chấp nhận `null` và có các phép tra cứu/thao tác đối tượng phù hợp.
- Khi thao tác `get(i)` để tính toán với `int`, thường có bước unboxing và có thể thêm truy cập gián tiếp.

Nếu kích thước được biết trước, `new ArrayList<>(capacity)` có thể giảm các lần mở rộng backing array, nhưng không tự xóa chi phí tham chiếu/wrapper. Nếu cần số liệu lưu trữ dày đặc và xử lý số học, `int[]` thường là lựa chọn khởi đầu hợp lý.

Với `long[]`, `double[]` cũng tương tự. Giá trị primitive `long`/`double` có 8 byte mỗi phần tử, còn `Long[]`/`Double[]` lưu tham chiếu tới đối tượng. Không dùng bảng kích thước `int[]` để suy ra chính xác overhead của tất cả loại wrapper.

## 7. Primitive stream: giảm nhu cầu boxing trong pipeline

Java có các stream dành cho số nguyên thủy:

- `IntStream` cho `int`.
- `LongStream` cho `long`.
- `DoubleStream` cho `double`.

Từ `int[]` có thể tạo `IntStream` bằng `Arrays.stream(intArray)`. Từ `Integer[]`, `Arrays.stream(wrapperArray)` tạo `Stream<Integer>` và thường cần unboxing khi xử lý số học:

```java
int[] numbers = {1, 2, 3};
Integer[] wrappers = {1, 2, 3};

int directSum = Arrays.stream(numbers).sum();
int unboxedSum = Arrays.stream(wrappers)
        .mapToInt(Integer::intValue)
        .sum();
// Hai tổng đều là 6.
```

`IntStream` còn có `average()`, `min()`, `max()`, `summaryStatistics()` và `toArray()` cho các bước xử lý số, giúp tránh việc tạo `Stream<Integer>` và boxing mỗi giá trị nếu không cần.

Khi thật sự cần đối tượng, có thể dùng:

```java
List<Integer> boxed = Arrays.stream(new int[] {1, 2, 3})
        .boxed()
        .toList(); // Java 16+, trả List<Integer>
```

`boxed()` là ranh giới chuyển primitive thành wrapper: nếu kết quả giữ các đối tượng lâu dài thì chi phí lưu trữ có thể tăng. Không có khẳng định rằng stream luôn nhanh hơn vòng lặp: với pipeline rất nhỏ, chi phí tạo/điều phối pipeline và mức tối ưu JIT có thể làm vòng lặp nhanh hơn. Hãy đo trên workload thật.

## 8. Cấp phát xảy ra ở đâu, và JVM có thể tối ưu thế nào?

### 8.1. Không đồng nhất “wrapper” với “mỗi biểu thức có một allocation”

`Integer.valueOf(42)` có thể trả đối tượng từ cache. Mã tạo wrapper tạm thời đôi khi được JIT tối ưu hết nếu không cần danh tính đối tượng.

Ví dụ về ý tưởng:

```java
static int compute(int x) {
    Integer boxed = Integer.valueOf(x);
    return boxed.intValue() * 2;
}
```

Đây là một **phương thức minh họa** để đặt trong một lớp. Trình biên dịch hoặc JIT có thể tối ưu phần boxing/unboxing vì đối tượng không cần được giữ lại. Nhưng không nên khẳng định lời gọi trên **luôn** được loại bỏ allocation ở mọi JVM, mọi mức tối ưu hoặc cách chạy.

### 8.2. Khi nào wrapper khó bị tối ưu bỏ?

Nếu wrapper được lưu lâu dài trong một collection, được trả ra khỏi một hàm, hoặc danh tính của nó được quan sát, JIT có ít cơ hội hơn để loại bỏ biểu diễn đối tượng. Ví dụ:

```java
static List<Integer> makeList(int[] values) {
    List<Integer> result = new ArrayList<>(values.length);
    for (int value : values) {
        result.add(value); // autoboxing
    }
    return result;
}
```

Với dữ liệu ở ngoài vùng cache và các phần tử được giữ lại bởi danh sách, các đối tượng wrapper có thể tạo thêm nhiều cấp phát so với `int[]`. Phải đo lượng heap đã giữ (*retained size*) hoặc cấp phát thực tế thay vì suy ra một lượng byte cố định từ source code.

### 8.3. Heap, stack và thanh ghi

Không nên viết “primitive nằm trên stack, object nằm trên heap” như một quy tắc tuyệt đối:

- Biến cục bộ `int` có thể được giữ trong thanh ghi hoặc stack tùy tối ưu của JVM.
- Trường `int` của một đối tượng là một phần dữ liệu trong đối tượng đó.
- Mảng `int[]` và `Integer[]` đều là các đối tượng Java.
- Một đối tượng wrapper có thể được JVM loại bỏ thông qua tối ưu và không còn một allocation heap thực tế.
- Kích thước header/căn chỉnh, compressed references và cách GC di chuyển đối tượng thuộc chi tiết triển khai JVM.

Trong phân tích hiệu năng, câu hỏi tốt hơn là **“dữ liệu này được lưu và truy cập bằng bao nhiêu đối tượng/tham chiếu ở runtime đã đo?”** thay vì suy đoán chỉ từ việc một biến được khai báo bên trong phương thức.

## 9. Ảnh hưởng tới CPU cache và garbage collection

### CPU cache và duyệt tuần tự

`int[]` lưu phần tử `int` trực tiếp và liên tiếp, nên khi duyệt một vùng số lớn, CPU thường có lợi từ locality và prefetch. `Integer[]` hoặc `ArrayList<Integer>` phải đọc tham chiếu rồi thường đọc wrapper tương ứng; nếu các wrapper ở vị trí rải rác, có thể cần thêm cache line và nhiều truy cập bộ nhớ hơn.

Điều này thường quan trọng trong thống kê, đồ thị số, dữ liệu đo lường hoặc pipeline tính toán trên tập lớn. Nhưng hiệu năng cụ thể vẫn phụ thuộc CPU, cache, kích thước mảng, branch prediction, JIT và công việc trong mỗi vòng lặp.

### Áp lực GC

Nếu ứng dụng tạo hàng triệu wrapper sống ngắn, GC có thêm đối tượng cần theo dõi và thu hồi. Nếu wrapper sống lâu trong collection, chúng chiếm retained heap và có thể tăng chi phí đánh dấu/duyệt đối tượng của GC.

Không tự động kết luận “cứ xuất hiện `Integer` trong code là có một object allocation”. Caching, scalar replacement và các tối ưu khác có thể làm số allocation runtime khác số biểu thức boxing ở source.

### Tính toán và bộ nhớ không luôn là cùng bottleneck

Một vòng lặp cộng `int[]` đơn giản có thể chịu ảnh hưởng mạnh bởi băng thông bộ nhớ, trong khi phép tính phức tạp trên từng phần tử có thể bị giới hạn CPU trước. Lựa chọn wrapper hay primitive cần xét tổng chi phí của chương trình, không chỉ tốc độ một thao tác.

## 10. Khi nào bắt buộc hoặc nên dùng wrapper?

Dù có chi phí tiềm ẩn, wrapper có những vai trò chính đáng:

1. **Generics/Collections:** `List<int>`, `Map<String, long>` không hợp lệ trong Java 17; cần `List<Integer>`, `Map<String, Long>` (hoặc thiết kế mảng/cấu trúc chuyên biệt).
2. **Giá trị có thể vắng mặt:** `Integer` có thể `null`, còn `int` không thể. Nhưng đừng dùng `null` tùy tiện nếu có thể thiết kế trạng thái rõ ràng hơn.
3. **API yêu cầu đối tượng:** framework, reflection, generic processing hoặc một API nhận `Object`/`Number` có thể cần wrapper.
4. **Khả năng tích hợp:** wrapper cung cấp các phương thức như `Integer.parseInt`, `Integer.compare`, `Long.parseLong`. Các phương thức này là thành viên của lớp wrapper nhưng vẫn có thể trả giá trị primitive.
5. **Tập hợp số lượng nhỏ hoặc không phải đường nóng:** ưu tiên API rõ ràng, đơn giản và đúng nghiệp vụ nếu overhead không đáng kể.

Khi cần biểu diễn kết quả tính toán “có hoặc không” mà không cần trả `null`, Java cũng có `OptionalInt`, `OptionalLong`, `OptionalDouble`. Chúng là đối tượng Optional nhưng giúp tránh boxing giá trị số vào `Integer`/`Long`/`Double` bên trong API đó.

**Không đánh đổi correctness lấy hiệu năng:** nếu “không có dữ liệu” khác với số 0, chuyển một `Integer nullable` thành `int` mà không thiết kế quy ước vắng mặt có thể làm sai nghiệp vụ hoặc gây `NullPointerException`.

## 11. Các cạm bẫy thường gặp

### 11.1. Null unboxing

```java
Integer amount = null;
// int x = amount; // Ném NullPointerException tại runtime.
```

Cần kiểm tra `null` trước khi unbox, sử dụng giá trị mặc định phù hợp hoặc định nghĩa trạng thái vắng mặt rõ ràng.

### 11.2. So sánh tham chiếu thay vì giá trị

```java
Integer a = Integer.valueOf(1000);
Integer b = Integer.valueOf(1000);

boolean sameValue = a.equals(b); // true
boolean sameIdentity = a == b;   // không dựa vào kết quả này
```

Tái sử dụng wrapper là tối ưu triển khai; `==` giữa hai tham chiếu không phải phép so sánh giá trị số. Tương tự, `Double` và `Float` có quy tắc `equals()`/`compareTo()` cần hiểu đối với `NaN` và dấu của số 0.

### 11.3. Nhầm mảng primitive với danh sách wrapper

```java
int[] values = {1, 2, 3};
List<int[]> oneArray = Arrays.asList(values);
// oneArray.size() == 1, không phải 3
```

`Arrays.asList(int[])` nhận cả mảng nguyên thủy như **một đối tượng mảng**. Nếu muốn `List<Integer>`, có thể dùng `Arrays.stream(values).boxed().toList()`.

### 11.4. Quên tràn số hoặc độ chính xác

Primitive nhanh và gọn không có nghĩa mọi phép toán đều chính xác:

- `int`/`long` có thể tràn khi cộng/nhân, kể cả bên trong `IntStream.sum()` hoặc `LongStream.sum()`.
- `double` có sai số dấu chấm động nhị phân. `Double` là wrapper của cùng kiểu `double`, **không phải** cách tăng độ chính xác số.
- Để tính toán thập phân tài chính chính xác, cân nhắc `BigDecimal` với quy tắc làm tròn cụ thể; nó là đối tượng với đặc điểm cấp phát và thuật toán khác primitive.

Không giải bài toán tràn hoặc sai số bằng cách thay `int` thành `Integer` hay `double` thành `Double`.

### 11.5. Giả định kích thước wrapper cố định

Không nên dùng một “kích thước đối tượng `Integer`” cố định để tính heap trên mọi JVM. Phần tử `int[]` là giá trị 4 byte nhưng đối tượng mảng còn header; `Integer[]` chứa các tham chiếu có kích thước cấu hình phụ thuộc JVM. Kích thước wrapper và cách cache/GC làm số liệu thực tế khác nhau.

### 11.6. Microbenchmark dễ bị sai

Không đo bằng cách thực hiện một lần `System.nanoTime()` quanh một loop rất nhỏ rồi kết luận. Những yếu tố làm lệch số đo gồm:

- JVM chưa warm-up để JIT tối ưu.
- GC chạy trong thời gian đo hoặc allocation biến mất do tối ưu.
- Code có thể bị loại bỏ vì kết quả không được sử dụng (*dead code elimination*).
- Dữ liệu test không phản ánh phân phối giá trị/cache/trường hợp `null` thực tế.
- Benchmark gộp cả thời gian tạo dữ liệu, boxing, tính toán và thu gom mà không phân biệt phần nào đang đo.
- Chế độ JVM, kiến trúc CPU, số luồng và kích thước dữ liệu khác nhau.

Với các câu hỏi latency/throughput, dùng **JMH** hoặc công cụ benchmark thích hợp, công bố môi trường JVM và các tham số, có warm-up/fork hợp lý. Để đo allocation hoặc retained memory, dùng profiler như Java Flight Recorder/JDK Mission Control hoặc công cụ heap profiler phù hợp. Không đưa ra con số tốc độ hay byte/object nếu chưa đo trong ngữ cảnh đó.

## 12. Tiêu chí chọn cấu trúc dữ liệu

| Nhu cầu | Lựa chọn nên cân nhắc | Lý do |
| --- | --- | --- |
| Một lượng lớn số nguyên, duyệt tuần tự/tính tổng | `int[]` / `long[]` | Dữ liệu phần tử trực tiếp, không cần wrapper trên mỗi phần tử |
| Một lượng lớn số thực | `double[]` | Lưu double trực tiếp; cần hiểu sai số dấu chấm động |
| Dữ liệu thay đổi số phần tử, API List | `ArrayList<Integer>` / `ArrayList<Long>` | Đáp ứng API collection; chấp nhận overhead tham chiếu/boxing |
| Cần `null` để phân biệt vắng mặt | `Integer` / `Long` | Có thể thiếu giá trị nhưng phải kiểm tra null |
| Pipeline chỉ làm toán trên mảng primitive | `IntStream` / `LongStream` / `DoubleStream` | Tránh boxing không cần thiết |
| API đòi `Stream<Integer>` hoặc `List<Integer>` | `boxed()` ở điểm biên | Chuyển kiểu khi thực sự cần đối tượng |
| Cần chính xác số thập phân theo quy tắc nghiệp vụ | `BigDecimal` | Correctness quan trọng hơn so sánh primitive-wrapper đơn thuần |
| Đường nóng nhạy allocation và cache | Đo nhiều phương án | Layout, JIT và GC quyết định hiệu quả thực tế |

Một quy trình quyết định hiệu quả: **xác định ngữ nghĩa** (độ chính xác, nullability, collection cần có), **chọn cấu trúc lưu số đơn giản**, rồi **đo profile trên dữ liệu thật** nếu hiệu năng là vấn đề. Đừng thay toàn bộ `List<Integer>` thành `int[]` nếu điều đó phá giao diện hoặc làm phức tạp cách xử lý mà chưa có bằng chứng chi phí.

## 13. Bài tự kiểm tra

**Câu 1.** Với một triệu giá trị `int`, tại sao `int[]` thường có locality tốt hơn `Integer[]`?  
**Đáp án:** dữ liệu `int` được lưu liên tiếp bên trong một mảng; `Integer[]` lưu tham chiếu và thường phải theo tham chiếu tới các đối tượng wrapper có thể nằm rải rác.

**Câu 2.** `Integer[] refs = new Integer[2]` chứa gì trước khi gán phần tử?  
**Đáp án:** hai tham chiếu `null`. `int[] values = new int[2]` tương ứng chứa hai giá trị 0.

**Câu 3.** Nếu source code có 1000 lần `Integer.valueOf(x)`, có chắc runtime đã cấp phát 1000 đối tượng `Integer` không?  
**Đáp án:** không. `valueOf` có cache và JVM có thể tối ưu hoặc tái sử dụng đối tượng tùy ngữ cảnh.

**Câu 4.** `new ArrayList<Integer>()` có tạo ngay một `Integer` cho mỗi vị trí capacity dự kiến không?  
**Đáp án:** không. Danh sách quản lý backing array của **tham chiếu**; các phần tử `Integer` là đối tượng được tham chiếu khi thêm giá trị tương ứng.

**Câu 5.** Vì sao `int[]` vẫn có overhead bộ nhớ?  
**Đáp án:** `int[]` là một đối tượng mảng có header và padding, dù mỗi ô phần tử `int` chiếm 4 byte.

**Câu 6.** `Integer sum = null; int value = sum;` gây gì?  
**Đáp án:** `NullPointerException` khi unboxing.

**Câu 7.** Nếu thay `double` thành `Double`, phép tính `0.1 + 0.2` có trở nên chính xác theo thập phân không?  
**Đáp án:** không. `Double` bọc giá trị `double` cùng ngữ nghĩa chấm động nhị phân, không tạo số thập phân chính xác tùy ý.

**Câu 8.** Khi nào dùng `List<Integer>` dù `int[]` thường gọn hơn?  
**Đáp án:** khi cần API Generic/Collection, danh sách thay đổi kích thước hoặc giao tiếp với các thành phần nhận đối tượng, và chi phí được chấp nhận theo yêu cầu.

## 14. Ghi nhớ

- Primitive là **giá trị trực tiếp**; wrapper là **đối tượng được tham chiếu** và có thể thêm overhead, dereference, boxing/unboxing, GC.
- `int[]` lưu trực tiếp các phần tử `int` trong cùng một mảng; `Integer[]`/`ArrayList<Integer>` lưu **tham chiếu tới wrapper**.
- JVM có cache và JIT tối ưu: **không phải mọi boxing đều tạo allocation mới**, cũng không có kích thước wrapper chính xác áp dụng mọi JVM.
- Chọn `int[]`, `long[]`, `double[]` và primitive streams khi xử lý khối lượng lớn số học; chọn wrapper khi cần ngữ nghĩa đối tượng/nullable/Generics.
- Đo hiệu năng với benchmark và profiler phù hợp trước khi kết luận về tốc độ hoặc lượng bộ nhớ trong một ứng dụng cụ thể.

Tài liệu tra cứu chính thức (Java SE 17): [Java Language Specification — Primitive Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html), [Boxing and Unboxing Conversions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.7), [Integer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html), [Arrays](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html), [IntStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html).
