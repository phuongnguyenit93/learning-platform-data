# Giới hạn sử dụng kiểu nguyên thủy làm đối số kiểu

## 1. Khái niệm: int không phải là Integer

Java phân biệt **kiểu nguyên thủy** như `int`, `long`, `boolean` với **kiểu tham chiếu** như `Integer`, `Long`, `String` và kiểu mảng.

Khi dùng generics, một đối số kiểu cụ thể phải là kiểu tham chiếu, không được là kiểu nguyên thủy. Vì thế:

```java
// Minh họa lỗi; không biên dịch.
java.util.List<int> scores;
```

Cách khai báo hợp lệ:

```java
// Khai báo minh họa.
java.util.List<Integer> scores = new java.util.ArrayList<>();
```

`Integer` là lớp bao (wrapper class) tương ứng với `int`. Nó không phải một cách viết khác của từ khóa `int`: biến `Integer` giữ tham chiếu và có thể nhận `null`; biến `int` giữ giá trị nguyên thủy và không nhận `null`.

Quy tắc này áp dụng cho kiểu generic tự viết, các collection và phương thức generic, chứ không chỉ riêng `List`. Bài học tập trung vào những quy tắc còn áp dụng trong Java hiện đại; chương trình thực hành biên dịch bằng Java 17 trở lên.

## 2. Vì sao cần hiểu giới hạn này?

Một lời gọi như `scores.add(10)` trông giống đang đưa `int` trực tiếp vào collection. Trên thực tế, mã được chấp nhận nhờ **chuyển đổi boxing** từ `int` sang `Integer`.

Nếu chỉ nhìn cú pháp ngắn gọn, người học dễ suy ra sai rằng:

- `List<int>` cũng phải hợp lệ.
- Đọc từ `List<Integer>` luôn an toàn như đọc từ `int[]`.
- Một mảng `int[]` sẽ tự biến thành nhiều đối tượng `Integer` khi truyền cho API generic.
- Mọi kiểu số có thể tự chuyển qua lại khi truyền vào `List<Long>` hoặc `List<Integer>`.

Những suy luận này đều không được Java bảo đảm. Cần tách **đối số kiểu trong khai báo** khỏi **chuyển đổi giá trị khi gán hoặc gọi phương thức**.

Trong mô hình generics hiện hành, việc truyền kiểu không tạo một bản triển khai generic riêng cho từng kiểu nguyên thủy. Boxing giúp một giá trị nguyên thủy đi qua API dùng kiểu tham chiếu; nó không mở rộng cú pháp đối số kiểu để chấp nhận `int`.

## 3. Các lớp bao tương ứng

| Kiểu nguyên thủy | Lớp bao dùng được làm đối số kiểu |
| --- | --- |
| `byte` | `Byte` |
| `short` | `Short` |
| `int` | `Integer` |
| `long` | `Long` |
| `float` | `Float` |
| `double` | `Double` |
| `char` | `Character` |
| `boolean` | `Boolean` |

Ví dụ:

```java
// Các khai báo minh họa; cần import java.util.List.
List<Integer> counts;
List<Long> durations;
List<Boolean> flags;
List<Character> letters;
```

Chú ý tên `Integer` và `Character`: không có lớp chuẩn tên `Int` hoặc `Char` để thay vào đây.

`void` biểu diễn phương thức không trả về giá trị, không phải một trong tám kiểu nguyên thủy dùng để lưu giá trị ở bảng trên. `Void` là một lớp tham chiếu có mục đích riêng trong một số API; nó không phải “giá trị nguyên thủy void được boxing”. Không dùng `List<Void>` như cách xây một danh sách số hay một tập các giá trị trống có ý nghĩa nghiệp vụ.

## 4. Quy tắc áp dụng ở đâu?

### 4.1. Kiểu generic tự viết

```java
// Khai báo minh họa.
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

`Box<Integer>` hợp lệ; `Box<int>` không hợp lệ.

Giới hạn của tham số kiểu cũng không được viết bằng kiểu nguyên thủy:

```java
// Minh họa lỗi; không biên dịch.
class BadBox<T extends int> {
}
```

Nếu API cần các lớp biểu diễn số, một giới hạn tham chiếu như `T extends Number` có thể phù hợp. Tuy nhiên, `Number` không bao gồm `Boolean` hay `Character`, và không biến biến kiểu `T` thành một kiểu số nguyên thủy.

### 4.2. Phương thức generic

```java
// Phương thức minh họa, đặt bên trong một lớp.
static <T> T identity(T value) {
    return value;
}
```

Lời gọi `identity(7)` có thể hợp lệ vì đối số `7` được boxing, và tham số kiểu được suy luận phù hợp với kiểu tham chiếu.

```java
// Câu lệnh minh họa trong một phương thức.
Integer result = identity(7);
```

Điều đó không cho phép chỉ định tường minh một đối số kiểu nguyên thủy. Chẳng hạn, nếu phương thức nằm trong lớp `Utils`, `Utils.<int>identity(7)` không hợp lệ; `Utils.<Integer>identity(7)` mới có đối số kiểu hợp lệ.

### 4.3. Wildcard

Không thể lách giới hạn bằng cách viết `List<? extends int>` hoặc `List<? super int>`. Giới hạn wildcard cũng phải dùng kiểu tham chiếu phù hợp, chẳng hạn `? extends Number`.

Đây là quy tắc cú pháp và hệ thống kiểu; ép kiểu một giá trị ở nơi sử dụng không thể làm một khai báo `List<int>` trở nên hợp lệ.

## 5. Boxing và unboxing: cầu nối giữa giá trị và lớp bao

Xét:

```java
// Minh họa trong một phương thức; cần import ArrayList và List.
List<Integer> scores = new ArrayList<>();
scores.add(10);

Integer boxed = scores.get(0);
int primitive = scores.get(0);
int next = primitive + 1;
```

Luồng dữ liệu:

1. `add` cần một giá trị tương thích với `Integer`.
2. Literal `10` có kiểu `int`; boxing chuyển nó thành giá trị kiểu `Integer` phù hợp.
3. Gán kết quả `get(0)` cho `Integer boxed` giữ cách nhìn tham chiếu.
4. Gán kết quả ấy cho `int primitive` cần unboxing từ `Integer` sang `int`.
5. Phép cộng trong ví dụ cuối làm việc với giá trị `int`.

Để hiểu cơ chế, có thể liên hệ boxing với `Integer.valueOf(...)` và unboxing với `intValue()`. Không suy ra rằng mỗi lần boxing chắc chắn tạo một đối tượng mới: lớp bao có thể tái sử dụng đối tượng và JVM có thể tối ưu.

Trong đoạn trên, `List<Integer>` vẫn là collection của các giá trị tham chiếu `Integer`, dù cú pháp thêm và đọc có thể ngắn giống dùng số nguyên thủy.

## 6. Null: lỗi runtime dễ xuất hiện sau khi dùng lớp bao

`Integer` có thể là `null`. Unboxing `null` gây `NullPointerException`:

```java
// Minh họa trong một phương thức.
Integer missing = null;
int value = missing;  // NullPointerException khi thực thi.
```

Với collection cho phép `null`, lỗi có thể xuất hiện khi đọc hoặc tính toán, không nhất thiết ở lúc thêm:

```java
// Minh họa; cần import ArrayList và List.
List<Integer> values = new ArrayList<>();
values.add(null);

int first = values.get(0);  // Unboxing null: lỗi runtime.
```

Chính sách xử lý tùy ý nghĩa dữ liệu:

- Nếu `null` là dữ liệu không hợp lệ, kiểm tra ngay tại ranh giới nhận dữ liệu.
- Nếu `null` biểu diễn “chưa có giá trị”, kiểm tra trước khi unboxing và xử lý trường hợp thiếu rõ ràng.
- Không tự thay `null` bằng `0` trừ khi `0` đúng là ý nghĩa nghiệp vụ được yêu cầu.

Ví dụ kiểm tra trước:

```java
// Minh họa trong một phương thức có biến Integer candidate.
if (candidate != null) {
    int value = candidate;
    System.out.println(value);
} else {
    System.out.println("missing");
}
```

Không phải mọi `List<Integer>` đều chấp nhận `null`. `ArrayList` chấp nhận, còn các danh sách tạo bởi `List.of(...)` không chấp nhận phần tử `null`. Quy tắc unboxing giống nhau, nhưng hợp đồng collection quyết định lỗi có thể bị phát hiện sớm đến đâu.

## 7. Không tự mở rộng số rồi boxing theo mọi cách

Kiểu nguyên thủy có một số phép mở rộng ngầm định, ví dụ từ `int` sang `long`. Điều đó không đồng nghĩa mọi lời gọi generic tự thực hiện chuỗi “mở rộng rồi boxing”:

```java
// Minh họa lỗi; cần import ArrayList và List.
List<Long> totals = new ArrayList<>();
totals.add(1);  // int không tự trở thành Long ở lời gọi này.
```

Các cách phù hợp:

```java
// Minh họa trong một phương thức.
List<Long> totals = new ArrayList<>();
totals.add(1L);

int count = 2;
totals.add((long) count);
```

`1L` có kiểu `long`, nên boxing tạo ra kiểu `Long` phù hợp. Phép ép `(long) count` cũng chủ động tạo một giá trị `long` trước bước boxing.

Tương tự, `Integer` không phải kiểu con của `Long`. Hai lớp có chung một số tổ tiên không có nghĩa là chuyển đổi tham chiếu tùy ý giữa chúng.

Nếu dùng `List<Number>`, có thể thêm nhiều lớp con của `Number`, như `Integer` và `Long`. Khi đọc, kết quả có kiểu `Number`; đó là hợp đồng khác với `List<Long>`, không phải cách biến mọi phần tử thành `Long`.

## 8. Mảng nguyên thủy là một kiểu tham chiếu

Đây là điểm cần phân biệt kỹ:

- `int` là kiểu nguyên thủy.
- `int[]` là kiểu mảng, thuộc nhóm kiểu tham chiếu.
- Vì vậy `List<int[]>` hợp lệ.

```java
// Minh họa trong một phương thức; cần import ArrayList và List.
List<int[]> batches = new ArrayList<>();
batches.add(new int[] {1, 2, 3});

int[] firstBatch = batches.get(0);
int firstValue = firstBatch[0];
```

Danh sách này chứa các **mảng**, không chứa trực tiếp từng số của mảng. Đối số kiểu là toàn bộ `int[]`; các phần tử bên trong mảng vẫn là `int`.

Điều này dẫn đến một nhầm lẫn phổ biến với API nhận tham số biến độ dài:

```java
// Minh họa trong một phương thức; cần import Arrays và List.
List<int[]> grouped = Arrays.asList(new int[] {1, 2, 3});
```

Kết quả có **một phần tử**, là mảng `int[]` đã truyền vào. Java không tự boxing từng phần tử để tạo `List<Integer>`.

Muốn có danh sách các lớp bao từ mảng số nguyên:

```java
// Minh họa trên Java 17+; cần import Arrays và List.
int[] source = {1, 2, 3};
List<Integer> converted = Arrays.stream(source).boxed().toList();
```

Ở đây `boxed()` thể hiện bước chuyển từng phần tử sang `Integer`. Danh sách do `Stream.toList()` trả về không cho phép thêm/xóa/thay phần tử; nếu cần danh sách thay đổi được, có thể tạo `new ArrayList<>(converted)`.

Mảng `int[]` và mảng `Integer[]` cũng là hai kiểu khác nhau. Không có chuyển đổi tự động toàn bộ mảng theo từng phần tử chỉ vì Java hỗ trợ boxing một giá trị đơn.

## 9. Hai lưu ý khi thay kiểu nguyên thủy bằng lớp bao

### 9.1. So sánh đối tượng và so sánh giá trị

Với hai biến kiểu `Integer`, `==` có thể kiểm tra danh tính tham chiếu thay vì giá trị số. Không dựa vào việc một số giá trị được tái sử dụng đối tượng để quyết định logic.

```java
// Minh họa trong một phương thức.
Integer left = Integer.valueOf(1000);
Integer right = Integer.valueOf(1000);

boolean sameValue = left.equals(right);
```

`sameValue` là `true`. Không cần và không nên dự đoán `left == right` để so sánh giá trị.

Nếu một hoặc cả hai biến có thể `null`, `java.util.Objects.equals(left, right)` có thể phù hợp khi ý định là so sánh hai giá trị bao gồm trường hợp thiếu. Nếu chủ động unboxing để so sánh số, phải xử lý `null` trước.

### 9.2. Overload vẫn phân biệt int và Integer

`List<Integer>` có hai phương thức dễ nhầm:

- `remove(int index)`: xóa theo vị trí.
- `remove(Object value)`: xóa phần tử bằng giá trị.

```java
// Minh họa trong một phương thức; cần import ArrayList và List.
List<Integer> numbers = new ArrayList<>(List.of(10, 20, 10));
numbers.remove(1);                    // Xóa vị trí 1, tức giá trị 20.
numbers.remove(Integer.valueOf(10));  // Xóa một phần tử có giá trị 10.
```

Sau hai thao tác, danh sách còn `[10]`. Cùng một con số xuất hiện trong mã nguồn không có nghĩa Java sẽ chọn cùng một overload; kiểu của đối số vẫn quan trọng.

## 10. Chương trình đầy đủ để quan sát các trường hợp

Lưu vào `PrimitiveTypeArgumentsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;

public class PrimitiveTypeArgumentsDemo {
    static <T> T identity(T value) {
        return value;
    }

    public static void main(String[] args) {
        List<Integer> values = new ArrayList<>();
        values.add(10);
        values.add(20);
        System.out.println(values);

        int total = values.get(0) + values.get(1);
        System.out.println(total);

        Integer fromGeneric = identity(7);
        System.out.println(fromGeneric.getClass().getSimpleName());

        List<int[]> grouped = Arrays.asList(new int[] {1, 2, 3});
        System.out.println("groups=" + grouped.size()
                + ", length=" + grouped.get(0).length);

        int[] source = {1, 2, 3};
        List<Integer> converted = Arrays.stream(source).boxed().toList();
        System.out.println(converted);

        List<Long> longs = new ArrayList<>();
        longs.add(1L);
        System.out.println(longs);

        List<Integer> nullable = new ArrayList<>();
        nullable.add(null);
        try {
            int value = nullable.get(0);
            System.out.println(value);
        } catch (NullPointerException ex) {
            System.out.println("null cannot unbox");
        }

        List<Integer> removals = new ArrayList<>(List.of(10, 20, 10));
        removals.remove(1);
        System.out.println(removals);
        removals.remove(Integer.valueOf(10));
        System.out.println(removals);

        int sum = IntStream.of(1, 2, 3).sum();
        System.out.println(sum);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 PrimitiveTypeArgumentsDemo.java
java PrimitiveTypeArgumentsDemo
```

Stdout chính xác:

```text
[10, 20]
30
Integer
groups=1, length=3
[1, 2, 3]
[1]
null cannot unbox
[10, 10]
[10]
6
```

Chương trình bắt `NullPointerException` chỉ để minh họa rõ kết quả của unboxing `null` và tiếp tục các thí nghiệm. Trong ứng dụng, nên xác định chính sách dữ liệu thiếu trước khi tính toán.

Dòng cuối sử dụng `IntStream`, một API chuyên biệt cho các phần tử `int`. Đây không phải cú pháp `Stream<int>`.

## 11. Chọn cấu trúc nào khi xử lý số?

| Cấu trúc | Phần tử | Khi phù hợp |
| --- | --- | --- |
| `List<Integer>` | Tham chiếu `Integer` | Cần API danh sách và tương tác với generics |
| `int[]` | Giá trị `int` | Cần mảng số có kích thước cố định |
| `List<int[]>` | Tham chiếu tới từng mảng `int[]` | Dữ liệu được chia thành nhiều nhóm mảng |
| `IntStream` | Luồng giá trị `int` | Cần chuỗi thao tác số như lọc, ánh xạ, tổng hợp |

Thư viện chuẩn còn có `LongStream` và `DoubleStream` cho các giá trị tương ứng. Đây là những API chuyên biệt được thiết kế sẵn, không phải bằng chứng rằng mọi lớp generic đều nhận được kiểu nguyên thủy.

Dùng lớp bao có thể kéo theo chi phí lưu tham chiếu, boxing/unboxing và quản lý đối tượng. Mức chi phí phụ thuộc dữ liệu, việc tái sử dụng đối tượng và tối ưu của JVM. Không khẳng định mỗi phần tử luôn tạo một đối tượng mới, không gán một con số bộ nhớ cố định cho mọi môi trường, và không thay cấu trúc chỉ dựa trên phỏng đoán hiệu năng.

Nếu cần tối ưu một đoạn xử lý số lớn, đo đoạn xử lý thực tế và xem xét cấu trúc nguyên thủy phù hợp. Nếu cần sự linh hoạt của collection generic, dùng lớp bao với hợp đồng `null` rõ ràng thường giúp mã dễ hiểu hơn.

## 12. Tự kiểm tra

1. Vì sao `List<int>` không hợp lệ nhưng `list.add(1)` lại hợp lệ khi `list` là `List<Integer>`?
2. Đoán kiểu và số phần tử của `Arrays.asList(new int[] {4, 5})`. Kiểm tra bằng biến khai báo tường minh `List<int[]>`.
3. Một `ArrayList<Integer>` đang chứa `null`. Việc gọi `get(0)` để gán cho `Integer` và để gán cho `int` khác nhau ở đâu?
4. Vì sao `List<Long>.add(1)` không hợp lệ trong khi `add(1L)` hợp lệ?
5. Với danh sách `[1, 2, 1]`, hãy viết riêng thao tác xóa theo vị trí và xóa một phần tử có giá trị `1`.
6. Chuyển một `int[]` sang `List<Integer>`, sau đó tạo bản danh sách cho phép thêm phần tử mà không thay đổi mảng nguồn.

Khi giải thích, luôn gọi tên hai bước riêng: **chọn đối số kiểu tham chiếu trong khai báo** và **chuyển đổi giá trị tại nơi sử dụng**.

## Tài liệu đối chiếu

- [Java Language Specification — Type Arguments (§4.5.1)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.5.1): các dạng đối số kiểu được chấp nhận.
- [Java Language Specification — Boxing và Unboxing (§5.1.7–§5.1.8)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.7): chuyển đổi giữa kiểu nguyên thủy và lớp bao.
- [Java API — Arrays.asList](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html#asList(T...)): hợp đồng phương thức generic nhận các phần tử qua varargs.
- [Java API — IntStream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/IntStream.html): API chuyên biệt cho giá trị `int` và bước `boxed()`.
