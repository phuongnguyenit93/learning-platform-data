# Tham số số lượng thay đổi và ký hiệu ba dấu chấm

## 1. Varargs giải quyết vấn đề gì?

Một thao tác như tính tổng hoặc ghi nhiều nhãn có thể nhận số lượng giá trị khác nhau ở mỗi lời gọi. Thay vì viết nhiều overload cho một, hai, ba giá trị, Java cho phép khai báo **tham số số lượng thay đổi (varargs)**.

```java
static int sum(int... values) {
    java.util.Objects.requireNonNull(values, "values");
    int total = 0;
    for (int value : values) {
        total += value;
    }
    return total;
}
```

Phương thức minh họa trên đặt trong một lớp. Các lời gọi sau đều phù hợp:

```java
int empty = sum();
int one = sum(5);
int several = sum(2, 3, 4);
```

Với implementation này, kết quả lần lượt là `0`, `5`, `9`. Varargs làm lời gọi linh hoạt về số đối số ở phần cuối, nhưng các đối số vẫn phải phù hợp với kiểu phần tử đã khai báo.

Đây là cú pháp và cơ chế còn áp dụng trong Java hiện hành. Chương trình đầy đủ bên dưới chạy với Java 17 trở lên.

## 2. Cú pháp Type... name

Trong `int... values`:

| Thành phần | Ý nghĩa |
| --- | --- |
| `int` | Kiểu của từng giá trị được tiếp nhận |
| `...` | Ba dấu chấm báo tham số số lượng thay đổi |
| `values` | Tên tham số dùng bên trong phương thức |

Dấu ba chấm nằm sau kiểu và trước tên tham số. Dùng ba ký tự chấm `...` trong mã nguồn, không thay bằng ký tự dấu lửng đơn `…` của văn bản.

Có thể dùng kiểu tham chiếu:

```java
static void showNames(String... names) {
    java.util.Objects.requireNonNull(names, "names");
    System.out.println(java.util.Arrays.toString(names));
}
```

Ở phần thân, `names` có kiểu `String[]`; với ví dụ đầu, `values` có kiểu `int[]`. Dùng `.length`, truy cập chỉ số hoặc for-each giống một mảng thông thường. Không dùng `values.size()` như với một collection.

Varargs không phải một kiểu collection mới. Nó là cách khai báo tham số mảng để nơi gọi có thể cung cấp các đối số tách rời phù hợp.

## 3. Tham số varargs phải là tham số cuối cùng

Có thể có các tham số cố định đứng trước:

```java
static void report(String label, int... codes) {
    java.util.Objects.requireNonNull(label, "label");
    java.util.Objects.requireNonNull(codes, "codes");
    System.out.println(label + ": " + codes.length);
}
```

Ví dụ lời gọi đặt trong một phương thức:

```java
report("empty");
report("batch", 10, 20, 30);
```

`label` là một đối số cố định bắt buộc. Phần `codes` nhận không, một hoặc nhiều giá trị còn lại.

Mỗi khai báo chỉ có tối đa một tham số varargs và nó phải đứng cuối. Các dạng sau không hợp lệ:

```java
// Không hợp lệ về vị trí tham số:
// void invalid(int... values, String label);

// Không hợp lệ vì có hai tham số varargs:
// void invalid(String... names, int... values);
```

Nếu muốn hai nhóm dữ liệu có số lượng phần tử thay đổi độc lập, dùng hai tham số mảng/collection có tên rõ ràng hoặc một kiểu dữ liệu phù hợp, không đặt hai dấu varargs trong cùng danh sách tham số.

## 4. Tại nơi gọi, các giá trị có thể được gom thành mảng

Với lời gọi:

```java
int result = sum(2, 3, 4);
```

Có thể hình dung về mặt ý nghĩa như truyền một mảng chứa ba phần tử:

```java
int result = sum(new int[] {2, 3, 4});
```

Hai đoạn là hai cách viết minh họa độc lập, không khai báo cùng biến `result` hai lần trong một phạm vi. Khi dùng lời gọi có các đối số tách rời ở dạng varargs, compiler sắp xếp dữ liệu thành mảng để phương thức nhận tham số mảng.

Không có đối số ở phần varargs tương ứng với một mảng rỗng, không phải null:

```java
int result = sum(); // values.length là 0 trong lời gọi này.
```

Đây là lý do `sum()` của bài có thể trả `0` mà không lỗi. Tuy nhiên, API khác có thể không cho phép số phần tử bằng 0 theo hợp đồng nghiệp vụ; khi đó cần kiểm tra hoặc thiết kế một tham số bắt buộc đứng trước.

Không nói rằng mọi lời gọi varargs luôn tạo một mảng mới. Khi đã truyền đúng một mảng phù hợp, trường hợp ở mục tiếp theo có thể dùng chính mảng ấy. Hơn nữa, mô tả gom mảng là cơ chế ngôn ngữ, không phải một kết luận đo hiệu năng cấp phát cụ thể sau mọi tối ưu hóa của JVM.

## 5. Có thể truyền một mảng đã tồn tại

```java
int[] numbers = {5, 6};
int result = sum(numbers);
```

`numbers` đã có kiểu `int[]`, phù hợp với tham số mảng mà phương thức nhận. Lời gọi này không biến cả `int[]` thành một phần tử số nguyên đơn lẻ và không sao chép nội dung tự động chỉ vì khai báo có dấu `...`.

Điều đó ảnh hưởng đến quyền sở hữu dữ liệu. Nếu phương thức sửa mảng tham số, mảng của bên gọi có thể bị sửa:

```java
static void incrementFirst(int... values) {
    java.util.Objects.requireNonNull(values, "values");
    if (values.length > 0) {
        values[0]++;
    }
}
```

Khi gọi `incrementFirst(numbers)`, hai bên cùng giữ tham chiếu tới một mảng. Nếu `numbers` ban đầu là `{5, 6}`, sau lời gọi nó là `{6, 6}`.

Ngược lại:

```java
int first = 7;
incrementFirst(first, 8);
System.out.println(first); // 7
```

Giá trị primitive của `first` được đưa vào mảng dùng cho lời gọi. Việc sửa phần tử mảng đó không gán lại biến cục bộ `first` ở bên gọi. Java vẫn truyền giá trị tham số; varargs không tạo cơ chế truyền biến primitive theo tham chiếu.

Với phần tử là đối tượng có thể thay đổi, cần tiếp tục phân biệt sửa một ô của mảng với sửa trạng thái của đối tượng được ô đó tham chiếu. Nếu API hứa không làm thay đổi dữ liệu nguồn, hãy không sửa mảng hoặc tạo bản sao phù hợp với hợp đồng; một bản sao mảng cũng chỉ sao chép các tham chiếu phần tử ở trường hợp mảng đối tượng.

## 6. Không có phần tử, một phần tử null và mảng null là ba trường hợp khác nhau

Với phương thức `showNames(String... names)`:

| Lời gọi | Dữ liệu nhận được |
| --- | --- |
| `showNames()` | Một mảng `String[]` rỗng |
| `showNames((String) null)` | Một mảng có đúng một phần tử null |
| `showNames((String[]) null)` | Tham chiếu mảng null |

`Objects.requireNonNull(names, "names")` chỉ từ chối **mảng null**, không tự từ chối mọi phần tử null bên trong. Nếu hợp đồng không cho phần tử null, cần kiểm tra từng phần tử hoặc chọn API khác có quy tắc phù hợp.

Không dùng lời gọi bare `showNames(null)` để diễn đạt ý định một cách mập mờ. Null literal có thể phù hợp với kiểu mảng `String[]`; compiler có thể cảnh báo về ý nghĩa lời gọi và phương thức nhận một mảng null, không phải tự bảo đảm một phần tử null. Cast đúng kiểu như bảng trên giúp xác định rõ hai ý định khác nhau.

Với `int...`, kiểu tham số là `int[]`: mảng có thể là null nếu được truyền tường minh, nhưng một phần tử `int` không thể là null. Với `Integer...`, cả mảng và các phần tử có thể là null về mặt kiểu; unboxing phần tử null trong thuật toán có thể gây lỗi nếu không có hợp đồng xử lý.

## 7. Chương trình chạy đầy đủ

Lưu thành **`VarargsBasicsDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

public class VarargsBasicsDemo {
    static int sum(int... values) {
        Objects.requireNonNull(values, "values");
        int total = 0;
        for (int value : values) {
            total += value;
        }
        return total;
    }

    static void incrementFirst(int... values) {
        Objects.requireNonNull(values, "values");
        if (values.length > 0) {
            values[0]++;
        }
    }

    static void show(String label, String... values) {
        Objects.requireNonNull(label, "label");
        Objects.requireNonNull(values, "values");
        System.out.println(label + " count=" + values.length
                + ", values=" + Arrays.toString(values));
    }

    public static void main(String[] args) {
        System.out.println("sum empty=" + sum());
        System.out.println("sum values=" + sum(2, 3, 4));

        int[] source = {5, 6};
        System.out.println("sum array=" + sum(source));
        incrementFirst(source);
        System.out.println("mutated array=" + Arrays.toString(source));

        int first = 7;
        incrementFirst(first, 8);
        System.out.println("primitive variable=" + first);

        show("empty");
        show("names", "An", "Binh");
        show("one null", (String) null);
        try {
            show("null array", (String[]) null);
        } catch (NullPointerException ex) {
            System.out.println("null array rejected");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all VarargsBasicsDemo.java
java VarargsBasicsDemo
```

Stdout chính xác:

```text
sum empty=0
sum values=9
sum array=11
mutated array=[6, 6]
primitive variable=7
empty count=0, values=[]
names count=2, values=[An, Binh]
one null count=1, values=[null]
null array rejected
```

`show` có một tham số cố định `label`; số lượng in ở `count` chỉ tính các phần tử của phần varargs. Mảng rỗng và mảng một phần tử null được xử lý bình thường theo hợp đồng minh họa, còn mảng null bị từ chối ngay đầu phương thức.

`sum` sử dụng phép cộng `int` thông thường. Nó không tự phát hiện tràn số chỉ vì tham số được khai báo varargs; một API tính toán có yêu cầu miền giá trị khác cần quy tắc phù hợp riêng.

## 8. Varargs và tham số mảng có cùng hình dạng chữ ký

Không khai báo đồng thời hai phương thức cùng tên trong một lớp chỉ khác ở các dạng sau:

```java
// Hai dạng này không tạo hai overload khác nhau:
// static void consume(int... values);
// static void consume(int[] values);
```

Tham số varargs có kiểu mảng; dấu `...` mở khả năng gọi bằng các đối số tách rời, không tạo một kiểu tham số mới phân biệt với `int[]` cho việc nạp chồng ấy.

Nếu chỉ có `consume(int[] values)`, bên gọi truyền một mảng. Nếu chỉ có `consume(int... values)`, bên gọi có thêm cách cung cấp nhiều đối số phù hợp hoặc không cung cấp phần tử nào. Phần thân trong cả hai trường hợp đều làm việc với một mảng.

Không chọn varargs chỉ để trông ngắn hơn khi API thực sự cần một collection đã có hoặc một cấu trúc dữ liệu giàu ý nghĩa. Nó hữu ích nhất khi các lời gọi thường nêu một nhóm giá trị ngắn trực tiếp tại nơi dùng.

## 9. Các lỗi và kỳ vọng sai thường gặp

- **Đặt varargs giữa danh sách tham số:** khai báo không hợp lệ; mọi tham số cố định phải đứng trước.
- **Nghĩ varargs cho nhận mọi kiểu:** `sum("2")` không hợp lệ với `int...`; số lượng linh hoạt không bỏ ràng buộc kiểu.
- **Nghĩ một List được tự trải thành nhiều đối số:** `sum(List.of(1, 2))` không tự biến thành lời gọi nhận hai số. Cần một đường chuyển đổi dữ liệu hoặc một API nhận collection đúng ý định.
- **Nghĩ varargs luôn không null:** lời gọi không phần tử tạo mảng rỗng, nhưng bên gọi vẫn có thể truyền tường minh một mảng null.
- **Nghĩ mảng truyền vào luôn được sao chép:** sửa mảng trong phương thức có thể đổi dữ liệu của bên gọi.
- **Nghĩ sửa phần tử mảng primitive là sửa biến primitive đã truyền:** các giá trị đã được đưa vào mảng; biến ở bên gọi không trở thành một ô tham chiếu chung.
- **Dùng cú pháp ba dấu chấm như một lời hứa về số lượng tối thiểu:** varargs tự nó cho phép không có phần tử ở phần thay đổi; kiểm tra hợp đồng nếu thuật toán cần ít nhất một.

Các khai báo varargs dùng tham số kiểu generic còn có các vấn đề kiểm tra kiểu riêng. Không thêm annotation để tắt cảnh báo chỉ vì mọi varargs đều “là mảng”; cần xem đúng kiểu phần tử và thao tác mà phương thức thực hiện.

## 10. Tự thực hành

1. Viết `count(String... values)` và gọi với không phần tử, một phần tử và ba phần tử. Kiểm tra số lượng là độ dài mảng nhận được.
2. Viết một phương thức có `String label` cố định và `int... numbers` cuối cùng; xác định đối số nào là bắt buộc.
3. Truyền một `int[]` có sẵn vào `incrementFirst`, rồi truyền các biến `int` tách rời. Giải thích kết quả qua mảng được dùng ở mỗi lời gọi.
4. Thử ba cách gọi với `String...`: không đối số, `(String) null`, `(String[]) null`. Nêu riêng chính sách cho mảng null và phần tử null.
5. Thử khai báo hai overload chỉ khác `int...` và `int[]`, quan sát lỗi trùng chữ ký rồi giữ lại khai báo đúng ý định của API.

Ký hiệu `...` giúp nơi gọi cung cấp một số lượng giá trị thay đổi, còn phần thân vẫn nhận một mảng có kiểu rõ ràng. Hiểu đồng thời cú pháp, cách gom đối số và quyền sở hữu mảng sẽ giúp dùng varargs gọn mà không bỏ sót ràng buộc kiểu hoặc hành vi null.

## Tài liệu đối chiếu

- [JLS §8.4.1 — Formal Parameters](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.1): tham số số lượng thay đổi, vị trí và kiểu mảng.
- [JLS §15.12.4.2 — Evaluate Arguments](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12.4.2): cách chuẩn bị đối số cho lời gọi varargs.
- [Arrays — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html): các phương thức hỗ trợ hiển thị và thao tác mảng trong ví dụ.
