# Vị trí cuối cùng của tham số varargs

## 1. Quy tắc: chỉ một tham số varargs và phải đứng cuối

Varargs cho phép người gọi truyền một dãy đối số vào một tham số biến độ dài. Trong khai báo Java, dấu `...` đứng sau kiểu và trước tên tham số:

```java
// Phương thức minh họa, đặt bên trong một lớp.
static void show(String label, int... values) {
    System.out.println(label + ":" + values.length);
}
```

Hai quy tắc bắt buộc:

1. Một phương thức hoặc constructor có tối đa một tham số varargs.
2. Nếu có, tham số varargs phải là tham số cuối cùng trong danh sách khai báo.

Với ví dụ, `label` là tham số cố định; `values` là phần đuôi biến độ dài.

```java
// Các lời gọi minh họa.
show("empty");
show("one", 5);
show("many", 5, 6, 7);
```

Quy tắc này vẫn áp dụng trong Java hiện đại. Các chương trình trong bài dùng Java 17 trở lên.

## 2. Vì sao phần biến độ dài nằm ở cuối?

Ở một lời gọi, những đối số đầu tiên được ghép với các tham số cố định. Phần còn lại có thể được gom cho tham số varargs.

Với:

```java
// Chữ ký minh họa.
static void show(String label, int... values) {
    System.out.println(label + ":" + values.length);
}
```

Lời gọi `show("sample", 5, 6, 7)` có cách ghép:

```text
"sample"      -> label
5, 6, 7       -> các phần tử của values
```

Phần đuôi có một ranh giới rõ ràng sau các đối số cố định. Java không hỗ trợ khai báo một nhóm varargs rồi lại đặt thêm một tham số thông thường ở phía sau.

Không nên hiểu rằng trình biên dịch sẽ tự tìm “đối số cuối là cấu hình” theo quy ước do người viết nghĩ ra. Vị trí được quyết định bởi chữ ký và quy tắc ngôn ngữ, không bởi tên biến hoặc ý nghĩa nghiệp vụ của đối số.

## 3. Những khai báo không hợp lệ

### 3.1. Thêm tham số sau varargs

```java
// Minh họa lỗi; không biên dịch.
static void wrong(int... values, String label) {
}
```

`values` không ở vị trí cuối. Việc `label` có kiểu khác với các số không tạo ra một ngoại lệ cho quy tắc.

Một ví dụ khác:

```java
// Minh họa lỗi; không biên dịch.
static void wrong(String separator, String... parts, boolean uppercase) {
}
```

Phải thiết kế lại thứ tự tham số hoặc đổi phần dãy dữ liệu sang một tham số mảng/collection thông thường.

### 3.2. Hai tham số varargs

```java
// Minh họa lỗi; không biên dịch.
static void wrong(String... labels, int... values) {
}
```

Không thể có hai phần biến độ dài độc lập như vậy trong cùng một chữ ký. Tham số đầu đã không đứng cuối, đồng thời một phương thức không được khai báo hai varargs.

Nếu thật sự cần hai nhóm dữ liệu, dùng các tham số có ranh giới rõ, chẳng hạn hai mảng:

```java
// Phương thức minh họa hợp lệ.
static void groups(String[] labels, int[] values) {
    System.out.println(labels.length + ":" + values.length);
}
```

Hoặc giữ nhóm đầu là mảng và chỉ nhóm cuối là varargs:

```java
// Phương thức minh họa hợp lệ.
static void groups(String[] labels, int... values) {
    System.out.println(labels.length + ":" + values.length);
}
```

Hai đoạn `groups` là hai thiết kế thay thế, không đặt đồng thời thành hai overload chỉ khác `int[]` và `int...` trong cùng lớp.

Điểm cần phân biệt là **mảng thông thường không phải varargs**. Một tham số mảng có thể đứng trước tham số khác mà không vi phạm quy tắc vị trí của `...`.

## 4. Tham số cố định vẫn là bắt buộc

Varargs cho phép số phần tử của phần đuôi bằng `0`. Nó không tự làm các tham số phía trước thành tùy chọn.

Với `show(String label, int... values)`:

| Lời gọi | Hợp lệ? | Cách hiểu |
| --- | --- | --- |
| `show("x")` | Có | Có label, không có phần tử varargs |
| `show("x", 1)` | Có | Có label và một phần tử |
| `show("x", 1, 2)` | Có | Có label và hai phần tử |
| `show()` | Không | Thiếu tham số cố định label |
| `show(1, 2)` | Không | Đối số đầu không phù hợp với String label |

Một tham số bắt buộc cùng kiểu với phần đuôi cũng có thể thể hiện yêu cầu “ít nhất một giá trị”:

```java
// Phương thức minh họa.
static int total(int first, int... rest) {
    int result = first;
    for (int value : rest) {
        result += value;
    }
    return result;
}
```

`total(4)` hợp lệ: `first = 4`, `rest` rỗng. `total(4, 5, 6)` có `first = 4`, `rest` chứa `5, 6`.

`total()` không hợp lệ. Thiết kế chữ ký đã biểu đạt yêu cầu tối thiểu một đối số, thay vì nhận một dãy có thể rỗng rồi mới kiểm tra độ dài.

## 5. Trong thân phương thức, varargs là một tham số mảng

Với `int... values`, kiểu của biến tham số trong thân phương thức là `int[]`.

Có thể dùng:

```java
// Minh họa trong thân phương thức có tham số int... values.
int count = values.length;

for (int value : values) {
    System.out.println(value);
}
```

Cách hiểu này giải thích vì sao người gọi cũng có thể truyền một mảng đã chuẩn bị:

```java
// Minh họa trong một phương thức.
int[] prepared = {8, 9};
show("array", prepared);
```

Ở lời gọi này, mảng được truyền ở vị trí tham số cuối. Không viết cú pháp trải mảng `...prepared` ở nơi gọi; `...` là một phần của khai báo varargs trong Java.

Khi gọi với các đối số lẻ cho phần biến độ dài, chúng được đóng gói theo cơ chế lời gọi varargs. Khi gọi bằng một mảng phù hợp, phương thức có thể được áp dụng theo dạng nhận mảng.

Hai điều này không cho phép thêm một tham số mới sau varargs trong khai báo.

### Không có phần tử khác với truyền mảng null

`show("empty")` cung cấp một phần đuôi rỗng ở cách gọi varargs thông thường.

Người gọi vẫn có thể truyền `(int[]) null` tường minh cho tham số mảng ấy. Nếu thân phương thức dùng `values.length`, nó sẽ ném `NullPointerException`.

Quy tắc varargs đứng cuối không tự bảo đảm mọi mảng truyền vào đều khác `null`. Các lời gọi trong chương trình đầy đủ bên dưới không truyền mảng `null`.

## 6. Thiết kế tham số cấu hình: đặt trước phần dãy

Một hàm nối chuỗi thường cần dấu phân cách và một dãy phần tử. Chữ ký hợp lệ:

```java
// Phương thức minh họa.
static String joinParts(String separator, String... parts) {
    return String.join(separator, parts);
}
```

Lời gọi:

```java
// Minh họa.
String result = joinParts("-", "A", "B", "C");
```

`separator` là một đối số cố định, còn các phần cần nối nằm ở cuối.

Nếu muốn giữ dấu phân cách ở cuối nơi gọi, hãy dùng mảng thông thường thay cho varargs:

```java
// Phương thức minh họa hợp lệ.
static String joinArray(String[] parts, String separator) {
    return String.join(separator, parts);
}
```

```java
// Minh họa.
String result = joinArray(new String[] {"A", "B"}, ":");
```

Ở đây `parts` không có `...`, nên đứng trước `separator` là hợp lệ.

Chọn thiết kế theo khả năng đọc của lời gọi. Không cố đặt mọi thứ trong `Object...` rồi tự đoán đâu là cấu hình, đâu là dữ liệu chỉ để lách một chữ ký chưa phù hợp; cách đó làm yếu hợp đồng kiểu.

## 7. Quy tắc cũng áp dụng cho constructor

Constructor có thể nhận varargs, và phần biến độ dài vẫn phải ở cuối:

```java
// Khai báo minh họa hợp lệ.
class Batch {
    private final String label;
    private final int size;

    Batch(String label, int... ids) {
        this.label = label;
        this.size = ids.length;
    }

    String summary() {
        return label + ":" + size;
    }
}
```

`new Batch("job", 1, 2, 3)` có tham số cố định `"job"` và ba mã ở phần cuối.

Không thể sửa constructor thành `Batch(int... ids, String label)`. Đây vẫn là cùng quy tắc danh sách tham số, không có ngoại lệ vì đang tạo đối tượng.

Trong ví dụ, constructor chỉ lưu số lượng mã nên không giữ tham chiếu mảng đầu vào. Một thiết kế cần giữ cả mảng sẽ phải cân nhắc thêm quyền sửa đổi và việc sao chép dữ liệu; đó là yêu cầu riêng với vị trí varargs.

## 8. “Đứng cuối” khác với từ khóa final

Hai khái niệm không liên quan trực tiếp:

```java
// Phương thức minh họa hợp lệ.
static int count(final int... values) {
    return values.length;
}
```

- “Đứng cuối” là vị trí trong danh sách tham số.
- `final` ngăn gán lại biến tham số `values` trong thân phương thức.

`final` không cho phép đặt thêm tham số sau `values`, cũng không tự làm các phần tử của mảng bất biến.

Không cần thêm `final` để một varargs trở thành hợp lệ; điều bắt buộc trong chủ đề này là chỉ có tối đa một phần biến độ dài và nó nằm cuối.

## 9. Chương trình đầy đủ

Lưu vào `VarargsPositionDemo.java`:

```java
import java.util.Arrays;

public class VarargsPositionDemo {
    static String describe(String label, int... values) {
        return label + ":count=" + values.length
                + ", values=" + Arrays.toString(values);
    }

    static int total(int first, int... rest) {
        int result = first;
        for (int value : rest) {
            result += value;
        }
        return result;
    }

    static String joinParts(String separator, String... parts) {
        return String.join(separator, parts);
    }

    static String joinArray(String[] parts, String separator) {
        return String.join(separator, parts);
    }

    static final class Batch {
        private final String label;
        private final int size;

        Batch(String label, int... ids) {
            this.label = label;
            this.size = ids.length;
        }

        String summary() {
            return label + ":" + size;
        }
    }

    public static void main(String[] args) {
        System.out.println(describe("zero"));
        System.out.println(describe("one", 5));
        System.out.println(describe("many", 5, 6, 7));

        int[] prepared = {8, 9};
        System.out.println(describe("array", prepared));

        System.out.println("singleTotal=" + total(4));
        System.out.println("manyTotal=" + total(4, 5, 6));

        System.out.println(joinParts("-", "A", "B", "C"));
        System.out.println(joinArray(new String[] {"A", "B"}, ":"));

        Batch batch = new Batch("job", 1, 2, 3);
        System.out.println(batch.summary());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 VarargsPositionDemo.java
java VarargsPositionDemo
```

Stdout chính xác:

```text
zero:count=0, values=[]
one:count=1, values=[5]
many:count=3, values=[5, 6, 7]
array:count=2, values=[8, 9]
singleTotal=4
manyTotal=15
A-B-C
A:B
job:3
```

Các điểm cần đối chiếu:

1. Bỏ hết các đối số phần đuôi không làm mất tham số cố định.
2. Một mảng phù hợp có thể được truyền trực tiếp vào vị trí varargs cuối.
3. `first` của `total` luôn được nhận riêng; nó không nằm trong mảng `rest`.
4. Tham số cấu hình đứng trước varargs khi dùng `joinParts`.
5. Dữ liệu mảng thông thường có thể đứng trước một tham số khác như ở `joinArray`.
6. Constructor cũng nhận phần varargs ở cuối.

Ví dụ tính tổng dùng các giá trị nhỏ để minh họa ghép tham số. Nó không xử lý yêu cầu riêng về tràn số trong một API tính toán tổng quát.

## 10. Kiểm tra lỗi khai báo riêng

Tạo `InvalidVarargsPosition.java`:

```java
public class InvalidVarargsPosition {
    static void afterVarargs(int... values, String label) {
    }

    static void twoVarargs(String... labels, int... values) {
    }
}
```

Biên dịch:

```shell
javac --release 17 InvalidVarargsPosition.java
```

Tệp cố ý không biên dịch vì tham số varargs đầu tiên của mỗi phương thức không đứng cuối. Không có chương trình chạy hoặc stdout kỳ vọng cho tệp này.

Không thêm một lời gọi “đủ rõ ràng” để cố làm khai báo hợp lệ. Lỗi đã nằm ở chữ ký; phải sửa thứ tự hoặc hình dạng tham số trước.

## 11. Cách tự kiểm tra một chữ ký

1. Tìm tất cả dấu `...` trong danh sách tham số.
2. Xác nhận có tối đa một tham số varargs.
3. Nếu có, xác nhận không có tham số nào đứng sau nó.
4. Đọc các tham số phía trước như phần bắt buộc của mỗi lời gọi.
5. Xác định cần cho phép phần đuôi rỗng hay cần một phần tử bắt buộc riêng.
6. Nếu cần nhiều nhóm dữ liệu, dùng mảng/collection/kiểu miền để thể hiện ranh giới thay vì nhiều varargs.
7. Kiểm tra các lời gọi không có, có một, có nhiều phần tử và có mảng được chuẩn bị sẵn.

Bài tập:

- Sửa chữ ký sai `format(String... words, String separator)` theo hai cách: giữ varargs hoặc giữ separator ở cuối.
- Với `total(int first, int... rest)`, liệt kê `first` và `rest` trong các lời gọi `total(1)`, `total(1, 2)`, `total(1, 2, 3)`.
- Vì sao `int[] values, String label` có thể hợp lệ nhưng `int... values, String label` không hợp lệ?
- Thiết kế một phương thức nhận một mảng tên và một dãy số lượng, chỉ dùng một varargs ở cuối.
- Giải thích khác biệt giữa phần đuôi rỗng và truyền mảng `null`.
- Thêm `final` vào tham số varargs rồi giải thích điều gì thay đổi và điều gì không thay đổi.

## Tài liệu đối chiếu

- [Java Language Specification — Formal Parameters (§8.4.1)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.1): tối đa một varargs, vị trí cuối và kiểu mảng của tham số.
- [Java Language Specification — Constructor Parameters (§8.8.1)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.8.1): cùng quy tắc tham số cho constructor.
- [Java Language Specification — Evaluate Arguments (§15.12.4.2)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12.4.2): đóng gói đối số khi gọi varargs.
- [Java API — String.join](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#join(java.lang.CharSequence,java.lang.CharSequence...)): ví dụ API đặt dấu phân cách trước dãy phần tử.
