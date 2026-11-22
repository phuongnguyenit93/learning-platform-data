# Varargs kết hợp với kiểu nguyên thủy và boxing

Khi một phương thức nhận `int...`, `Integer...` hoặc `Object...`, cùng lời gọi nhìn giống nhau có thể tạo các loại mảng và thực hiện các phép chuyển đổi khác nhau. Điểm cần nắm là: **kiểu phần tử của tham số varargs quyết định mỗi đối số phải chuyển thành gì**.

Bài này dùng Java 17+ để quan sát những quy tắc vẫn áp dụng trong Java hiện hành.

## 1. Ba cơ chế cần phân biệt

- **Đóng gói đối số varargs:** gom các đối số phần tử vào mảng để truyền cho phương thức.
- **Đóng hộp (boxing):** chuyển giá trị nguyên thủy sang kiểu bao tương ứng, chẳng hạn `int → Integer`.
- **Mở hộp (unboxing):** lấy giá trị nguyên thủy từ đối tượng kiểu bao, chẳng hạn `Integer → int`. Mở hộp một tham chiếu `null` gây `NullPointerException`.

Ngoài ra còn có mở rộng kiểu nguyên thủy, ví dụ `int → long`. Nó khác boxing: kết quả vẫn là giá trị nguyên thủy.

Xét ba khai báo minh họa bên trong một lớp:

```java
static void primitives(int... values) { }
static void wrappers(Integer... values) { }
static void objects(Object... values) { }
```

| Lời gọi | Mảng nhận được | Chuyển đổi phần tử |
| --- | --- | --- |
| `primitives(1, 2)` | `int[]` | Không cần boxing |
| `wrappers(1, 2)` | `Integer[]` | Mỗi `int` được boxing thành `Integer` |
| `objects(1, 2)` | `Object[]` | Boxing thành `Integer`, rồi dùng tham chiếu như `Object` |

Tạo một mảng không đồng nghĩa với boxing các phần tử. `int[]` là đối tượng mảng nhưng các phần tử của nó vẫn là `int`.

## 2. Chuyển đổi theo từng phần tử

Với cách gọi truyền các phần tử rời, hãy đọc kiểu sau dấu khai báo varargs như kiểu đích của từng đối số.

Các khai báo `primitives(int...)`, `wide(long...)`, `wrappers(Integer...)` và `longWrappers(Long...)` cho những ví dụ sau:

| Lời gọi minh họa | Hợp lệ? | Vì sao |
| --- | --- | --- |
| `primitives((byte) 3, 4)` | Có | `byte → int`; đối số thứ hai đã là `int` |
| `primitives(Integer.valueOf(5))` | Có | `Integer → int` bằng unboxing |
| `primitives(Byte.valueOf((byte) 6))` | Có | Unboxing `Byte → byte`, rồi mở rộng `byte → int` |
| `wide(7)` | Có | Mở rộng `int → long` |
| `wide(Integer.valueOf(8))` | Có | Unboxing `Integer → int`, rồi mở rộng `int → long` |
| `wrappers(9)` | Có | Boxing `int → Integer` |
| `longWrappers(10L)` | Có | Boxing `long → Long` |
| `longWrappers(10)` | Không | Không tự ghép `int → long → Long` cho lời gọi này |
| `wrappers((byte) 11)` | Không | Boxing `byte` tạo `Byte`, không tạo `Integer` |
| `primitives(12L)` | Không | Không tự thu hẹp `long → int` |
| `wrappers(Long.valueOf(13))` | Không | Không tự đổi `Long` thành `Integer` |

Các dòng “Không” chỉ minh họa lỗi biên dịch, không phải mã để chép vào chương trình chạy hoàn chỉnh.

Muốn truyền `int n` cho `Long...`, có thể chuyển rõ ràng bằng `(long) n` hoặc `Long.valueOf(n)`. Cách đầu tạo biểu thức `long` để boxing; cách sau gọi phương thức có thể nhận giá trị `int` thông qua mở rộng thành `long`.

Đừng suy luận rằng mọi chuỗi chuyển đổi có vẻ hợp lý đều được Java tự động ghép lại. Đặc biệt, việc unboxing rồi mở rộng kiểu nguyên thủy được chấp nhận trong nhiều lời gọi, nhưng mở rộng kiểu nguyên thủy rồi boxing sang một kiểu bao khác không phải một phép chuyển đổi lời gọi tự động tương ứng.

## 3. Mảng không tự boxing hoặc unboxing toàn bộ

Khác biệt giữa đối số phần tử và đối số mảng rất quan trọng:

```java
// Đoạn minh họa; giả sử các phương thức đã được khai báo trong lớp.
Integer a = 1;
Integer b = 2;
primitives(a, b);              // Hợp lệ: mở hộp từng phần tử.

Integer[] boxed = {1, 2};
// primitives(boxed);          // Không hợp lệ: Integer[] không thành int[].

int[] raw = {1, 2};
// wrappers(raw);              // Không hợp lệ: int[] không thành Integer[].
// wide(raw);                  // Không hợp lệ: int[] không thành long[].
```

Mặc dù `int` mở rộng được thành `long`, quan hệ này không biến `int[]` thành `long[]`. Tương tự, hỗ trợ boxing từng giá trị không tạo phép chuyển đổi giữa `int[]` và `Integer[]`.

Nếu cần đổi kiểu mảng, hãy tạo mảng đích và chuyển từng phần tử có chủ đích. Với `Integer[]`, phải quyết định cách xử lý phần tử `null` trước khi unboxing. Không có một cách xử lý `null` phù hợp cho mọi nghiệp vụ.

### Trường hợp Object...

Với `Object...`, truyền một `int[]` sẽ cung cấp **một đối số phần tử** vì `int[]` là `Object` nhưng không phải `Object[]`. Lời gọi không tự trải nó thành nhiều `Integer`.

Ngược lại, `Integer[]` có thể được dùng như `Object[]` và có thể làm toàn bộ mảng tham số. Ép thành `(Object) boxed` diễn đạt ý định truyền chính mảng đó như một phần tử duy nhất.

Trong ví dụ chạy dưới đây, ép `(Object[]) boxed` làm rõ trường hợp muốn dùng mảng `Integer[]` làm mảng tham số và tránh cảnh báo của `javac` về cách gọi không rõ ý định.

## 4. Chương trình hoàn chỉnh để quan sát

Lưu thành `VarargsBoxingDemo.java`:

```java
import java.util.Arrays;

public class VarargsBoxingDemo {
    static void primitives(int... values) {
        System.out.println("int[] " + Arrays.toString(values));
    }

    static void wide(long... values) {
        System.out.println("long[] " + Arrays.toString(values));
    }

    static void wrappers(Integer... values) {
        System.out.println("Integer[] " + Arrays.toString(values));
    }

    static void objects(Object... values) {
        StringBuilder result = new StringBuilder();
        for (Object value : values) {
            if (result.length() > 0) {
                result.append(", ");
            }
            result.append(value).append(":")
                    .append(value.getClass().getSimpleName());
        }
        System.out.println(result);
    }

    static void count(String label, Object... values) {
        System.out.println(label + " -> " + values.length);
    }

    static int total(int... values) {
        int result = 0;
        for (int value : values) {
            result += value;
        }
        return result;
    }

    static void prefer(long value) {
        System.out.println("selected long: " + value);
    }

    static void prefer(Integer... values) {
        System.out.println("selected Integer...: " + Arrays.toString(values));
    }

    public static void main(String[] args) {
        primitives(1, 2);
        primitives(Integer.valueOf(3), Byte.valueOf((byte) 4));
        wide(5, Integer.valueOf(6));
        wrappers(7, 8);
        objects(9, 10L);

        int[] raw = {11, 12};
        Integer[] boxed = {13, 14};
        count("int[]", raw);
        count("Integer[]", (Object[]) boxed);
        count("Integer[] as Object", (Object) boxed);

        Integer missing = null;
        wrappers(missing);
        try {
            System.out.println(total(missing));
        } catch (NullPointerException e) {
            System.out.println("unboxing null -> NullPointerException");
        }

        prefer(15);
        prefer(16, 17);
    }
}
```

Chạy với JDK 17 trở lên:

```shell
javac -encoding UTF-8 VarargsBoxingDemo.java
java VarargsBoxingDemo
```

Stdout:

```text
int[] [1, 2]
int[] [3, 4]
long[] [5, 6]
Integer[] [7, 8]
9:Integer, 10:Long
int[] -> 1
Integer[] -> 2
Integer[] as Object -> 1
Integer[] [null]
unboxing null -> NullPointerException
selected long: 15
selected Integer...: [16, 17]
```

### Những gì kết quả chứng minh

Hai lời gọi `primitives` đều cho mảng `int[]`. Lời gọi thứ hai thực hiện unboxing trước khi các giá trị nằm trong mảng; riêng `Byte` còn cần mở rộng `byte → int`.

`wide` nhận giá trị `long` dù các biểu thức đầu vào là `int` và `Integer`. Không cần tạo `Long` vì kiểu phần tử đích là nguyên thủy.

`objects(9, 10L)` cho thấy boxing giữ đúng loại giá trị đầu vào: `int` thành `Integer`, `long` thành `Long`. Việc cùng đặt trong một `Object[]` không biến chúng thành cùng một lớp số.

Ba dòng `count` kiểm chứng rằng mảng nguyên thủy không tự được trải ra hoặc boxing theo từng phần tử. Kiểu của đối số và phép ép kiểu quyết định mảng đang được truyền dưới vai trò nào.

## 5. Null: lỗi có thể xuất hiện trước khi vào thân phương thức

Trong chương trình, `wrappers(missing)` hợp lệ và tạo mảng `Integer[]` có một phần tử `null`. `Arrays.toString` hiển thị phần tử đó nên lời gọi này không lỗi.

Với `total(missing)`, đích là phần tử `int`. Java phải mở hộp `missing` trong lúc chuẩn bị đối số. Vì `missing == null`, lỗi xuất hiện trước khi thân `total` bắt đầu chạy.

Đừng nhầm điều này với:

```java
// Minh họa hai trường hợp khác nhau:
total((int[]) null);           // Truyền mảng null; vòng lặp trong total gây lỗi.
wrappers((Integer) null);      // Truyền một phần tử null trong mảng dài 1.
wrappers((Integer[]) null);    // Truyền cả tham chiếu mảng bằng null.
```

Nếu một phương thức nhận `Integer...` rồi cộng các phần tử vào biến `int`, thao tác cộng sẽ cần unboxing. Vì vậy, chọn kiểu bao không loại bỏ nguy cơ `NullPointerException`; nó chỉ cho phép biểu diễn `null`, còn hợp đồng xử lý dữ liệu phải được quyết định rõ.

Trong API tính toán không chấp nhận giá trị thiếu, tham số nguyên thủy thường thể hiện ý định tốt hơn. Nếu giá trị thiếu có ý nghĩa nghiệp vụ, nên chọn kiểu dữ liệu cùng cách kiểm tra và thông báo lỗi phù hợp.

## 6. Overload: không thể dùng một khẩu quyết “boxing thắng varargs”

Hai phương thức `prefer` trong chương trình có cùng tên:

```java
static void prefer(long value) { /* ... */ }
static void prefer(Integer... values) { /* ... */ }
```

Với `prefer(15)`, ứng viên `long` được chọn trong giai đoạn xét lời gọi số tham số cố định bằng mở rộng `int → long`. Không cần chuyển sang giai đoạn đóng gói đối số varargs để chọn `Integer...`.

Với `prefer(16, 17)`, ứng viên nhận một `long` không phù hợp số lượng đối số. Lời gọi dùng `Integer...` và boxing hai giá trị.

Một phương thức được khai báo varargs vẫn có thể tham gia các giai đoạn gọi số tham số cố định khi đối số đã là mảng phù hợp. Do đó, khẩu quyết “phương thức thường luôn thắng phương thức có dấu ba chấm” cũng dễ dẫn đến kết luận sai.

Cũng cần tránh overload sau nếu muốn lời gọi với số nguyên được giải quyết rõ ràng:

```java
// Đoạn cố ý minh họa lỗi, không phải chương trình chạy độc lập:
static void choose(int... values) { }
static void choose(Integer... values) { }

// choose(1);  // Lỗi biên dịch: lời gọi nhập nhằng giữa hai overload.
```

Trong trường hợp này, cả hai ứng viên cần xét theo varargs và không có ứng viên cụ thể nhất để chọn cho lời gọi trên. Thay vì yêu cầu người dùng API nhớ các phép ép kiểu, ưu tiên tên phương thức hoặc hợp đồng đầu vào rõ ràng.

## 7. Chọn API và đánh giá chi phí

| Nhu cầu | Hướng chọn |
| --- | --- |
| Nhóm giá trị số để tính toán, không chấp nhận null | Varargs nguyên thủy như `int...`, `long...` |
| Cần phân biệt phần tử thiếu bằng null | Kiểu bao như `Integer...`, với kiểm tra rõ ràng |
| Nhận nhiều kiểu đối tượng khác nhau | `Object...`, chấp nhận giảm mức bảo đảm kiểu |
| Dữ liệu đầu vào đã là collection | Cân nhắc nhận collection trực tiếp |
| Đường chạy được gọi rất nhiều lần | Đo chi phí cấp phát/chuyển đổi trước khi tối ưu |

Varargs nguyên thủy có thể cần mảng để đóng gói nhưng không cần boxing từng phần tử nguyên thủy. Varargs kiểu bao với đầu vào nguyên thủy cần các phép boxing; tuy nhiên, không được kết luận rằng mỗi phép boxing chắc chắn tạo một đối tượng mới, vì một số giá trị có thể dùng đối tượng đã lưu sẵn và JVM có thể tối ưu.

Không so sánh các đối tượng kiểu bao bằng `==` để đánh giá giá trị số hoặc suy ra số lần cấp phát. Dùng phép so sánh giá trị thích hợp và công cụ đo nếu cần phân tích hiệu năng.

## 8. Tự kiểm tra

1. Với khai báo `wide(long... values)`, lời gọi `wide(1, 2)` có cần boxing không?
2. Vì sao một đối số `Integer` vào `int...` được chấp nhận nhưng `Integer[]` vào `int...` không được?
3. Một biến `Integer` bằng null vào `int...` gây lỗi ở giai đoạn nào?
4. `Long...` có tự nhận literal `1` như một `Long` không?
5. Một `int[]` truyền vào `Object...` là bao nhiêu phần tử?

Đáp án:

1. Không; hai giá trị `int` được mở rộng thành `long` để đặt trong `long[]`.
2. Chuyển đổi từng giá trị bằng unboxing được hỗ trợ; Java không tự chuyển đổi toàn bộ mảng giữa hai kiểu đó.
3. Khi chuẩn bị đối số cần unboxing, trước khi thân phương thức bắt đầu.
4. Không; hãy dùng `1L` hoặc tạo `Long` rõ ràng.
5. Một phần tử: chính đối tượng mảng `int[]`.

## Tài liệu đối chiếu

Các quy tắc chuyển đổi được mô tả tại [JLS 21 §5.1.7 — Boxing Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.7), [§5.1.8 — Unboxing Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.8) và [§5.3 — Invocation Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.3). Thứ tự xét overload nằm ở [JLS 21 §15.12.2](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12.2).
