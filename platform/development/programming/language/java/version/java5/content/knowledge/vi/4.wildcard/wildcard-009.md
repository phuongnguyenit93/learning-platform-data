# Capture conversion và tham số kiểu được trình biên dịch ghi nhận

## 1. Vấn đề: biết có một kiểu nhưng chưa biết tên kiểu đó

Khi nhận `List<?>`, mã biết danh sách có một kiểu phần tử nào đó, nhưng không biết kiểu đó là gì. Ký hiệu đại diện (wildcard) `?` không có nghĩa phần tử được tùy ý thay bằng bất kỳ `Object` nào.

Ví dụ dưới đây là đoạn minh họa lỗi trong một phương thức, không phải chương trình chạy độc lập:

```java
static void resetFirst(List<?> values) {
    values.set(0, values.get(0)); // Lỗi biên dịch.
}
```

Ý định ở đây có vẻ an toàn: lấy phần tử đầu rồi đặt lại chính phần tử ấy. Tuy nhiên, trình biên dịch không duy trì một tên kiểu chung mà mã có thể dùng trực tiếp giữa các lần sử dụng biểu thức wildcard như trên.

**Capture conversion** là cơ chế trình biên dịch thay một wildcard bằng một biến kiểu mới trong quá trình kiểm tra kiểu. Nhờ biến kiểu này, một số quan hệ kiểu vẫn được biểu diễn chính xác, dù chương trình không biết tên kiểu phần tử cụ thể.

Cơ chế này vẫn được quy định trong [JLS §5.1.10 của Java 25](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.10). Bài dùng ví dụ tương thích Java 17 trở lên, không cần kiểu thô hoặc ép kiểu không kiểm tra.

## 2. `CAP#1` thực chất biểu thị điều gì?

Trong thông báo lỗi của `javac`, có thể gặp dạng:

```text
CAP#1 extends Object from capture of ?
```

Đây là cách công cụ chẩn đoán đặt nhãn cho một biến kiểu được tạo khi capture. Có thể đọc là: “một kiểu chưa biết, có cận trên là `Object`, được ghi nhận từ dấu `?`”.

Điều cần phân biệt:

| Ký hiệu | Vai trò |
| --- | --- |
| `?` trong `List<?>` | Wildcard xuất hiện trong mã nguồn |
| `CAP#1` trong lỗi | Nhãn chẩn đoán cho một biến kiểu capture do trình biên dịch tạo |
| `T` trong `<T> void work(List<T> values)` | Tham số kiểu do lập trình viên khai báo và có thể dùng trong thân phương thức |
| `String` trong `List<String>` | Đối số kiểu cụ thể được khai báo tại nơi sử dụng |

Không viết `List<CAP#1>` trong mã nguồn. Số thứ tự `#1`, `#2` không phải tên chuẩn có thể dựa vào giữa các lần biên dịch; cách trình bày lỗi có thể thay đổi theo JDK và tùy chọn chẩn đoán.

Trình biên dịch cũng không mở danh sách để nhìn phần tử rồi kết luận rằng wildcard là `String`. Capture biểu diễn những điều **được bảo đảm bởi kiểu tĩnh**, không khám phá kiểu phần tử từ dữ liệu đang có lúc chạy. Danh sách rỗng vẫn có thể được capture.

## 3. Từ `List<?>` sang “`List` của một kiểu chưa biết”

Để suy luận, có thể tưởng tượng trình biên dịch đang làm việc với:

```text
List<?>  →  List<CAP>
            với CAP có cận trên Object
```

Đây là sơ đồ giải thích, không phải phép gán hoặc cú pháp Java mà người dùng phải viết.

Nếu một biểu thức đã được xét dưới dạng `List<CAP>`:

- `get(int)` trả về phần tử có kiểu `CAP`; vì cận trên là `Object`, có thể đọc dưới dạng `Object`.
- `set(int, E)` yêu cầu giá trị phù hợp với `CAP`.
- Một biến kiểu `Object` không tự động phù hợp với `CAP`: nó có thể đang giữ một đối tượng không thuộc kiểu phần tử của danh sách.

Ví dụ minh họa:

```java
static void wrong(List<?> values) {
    Object value = values.get(0);
    // values.set(0, value); // Không chứng minh được Object thuộc CAP.
}
```

Lưu vào `Object` giữ nguyên tham chiếu đối tượng khi chạy, nhưng kiểu tĩnh `Object` không biểu đạt rằng đối tượng thuộc đúng kiểu phần tử đang bị che đi. Hệ thống kiểu cần bằng chứng từ khai báo và các quan hệ kiểu, không chỉ lập luận bằng lời của người viết.

Ngay cả biểu thức `values.set(0, values.get(0))` ở đầu bài cũng bị từ chối. Không nên hiểu rằng mọi lần dùng cùng biến `values` đều được tự động gắn một capture chung có tên ổn định trong toàn bộ thân phương thức. Mỗi lần thực hiện capture tạo biến kiểu mới; các capture không tự trở thành cùng một kiểu chỉ vì chúng có chung cận trên.

## 4. Phương thức trợ giúp đặt tên cho quan hệ kiểu

Cách giải quyết là chuyển thao tác cần giữ cùng kiểu phần tử vào phương thức generic:

```java
static void resetFirst(List<?> values) {
    resetFirstCaptured(values);
}

private static <T> void resetFirstCaptured(List<T> values) {
    if (!values.isEmpty()) {
        T first = values.get(0);
        values.set(0, first);
    }
}
```

Tại lời gọi `resetFirstCaptured(values)`, trình biên dịch có thể suy luận đối số kiểu của `T` từ kiểu capture của đối số truyền vào. Trong thân phương thức trợ giúp, cùng một `T` được dùng xuyên suốt:

```text
List<T>.get(0)  →  T first  →  List<T>.set(0, first)
```

Vì vậy, kết quả đọc phù hợp chính xác với kiểu mà thao tác ghi yêu cầu. Không có bước chuyển danh sách thành `List<Object>` và không cần khẳng định `T` cụ thể là `String` hoặc `Integer`.

Tên `resetFirstCaptured` chỉ là cách đặt tên dễ đọc. Không có từ khóa đặc biệt nào khiến tên này hoạt động; điều quan trọng là chữ ký `<T> ... List<T>` và việc các thao tác liên quan cùng dùng một `T`.

Nếu API ngay từ đầu cần diễn đạt quan hệ kiểu trong nhiều vị trí, có thể thiết kế phương thức public là generic. Nếu API chỉ muốn nhận danh sách bất kỳ và thao tác nội bộ cần tên kiểu, phương thức trợ giúp private giữ giao diện `List<?>` gọn hơn.

## 5. Cận của wildcard vẫn được giữ khi capture

Capture không bỏ qua các cận (bounds). Với `List<E>`, `E` có cận trên ngầm định là `Object`:

| Kiểu tại nơi dùng | Thông tin về biến kiểu capture |
| --- | --- |
| `List<?>` | Cận trên `Object`; cận dưới là kiểu null |
| `List<? extends Number>` | Cận trên `Number`; cận dưới là kiểu null |
| `List<? super Integer>` | Cận trên `Object`; cận dưới `Integer` |

Cận trên cho biết có thể an toàn đọc phần tử như kiểu nào; cận dưới giúp xác định những giá trị có thể truyền vào vị trí nhận phần tử. “Kiểu null” trong bảng là khái niệm của đặc tả, không phải lớp Java để khai báo biến.

Ví dụ đọc số qua cận trên:

```java
static double firstAsDouble(List<? extends Number> values) {
    return firstAsDoubleCaptured(values);
}

private static <T extends Number> double firstAsDoubleCaptured(List<T> values) {
    return values.get(0).doubleValue();
}
```

Đoạn minh họa giả định danh sách có phần tử đầu khác `null`. `T extends Number` cho phép gọi `doubleValue()` trên giá trị kiểu `T`. Nó không cho phép chèn mọi `Number` vào `List<T>`: kiểu thực tế được biểu diễn bởi `T` vẫn có thể là `Integer`.

Với cận dưới:

```java
static void addOne(List<? super Integer> values) {
    values.add(1);               // Hợp lệ: Integer phù hợp với cận dưới.
    Object first = values.get(0); // Chỉ bảo đảm đọc được như Object.
}
```

Đối số kiểu sau capture còn phải tôn trọng cận khai báo của lớp generic. Chẳng hạn với `class Box<T extends Number> {}`, capture của `Box<?>` có cận trên `Number`, không phải luôn là `Object`. Với `? extends B`, đặc tả kết hợp `B` với cận khai báo phù hợp; đừng học thuộc rằng mọi dấu `?` đều có cùng cận.

Một giới hạn kỹ thuật khác: capture conversion không tự áp dụng đệ quy vào mọi tầng generic lồng nhau trong cùng một bước. Với `List<List<?>>`, đối số kiểu ngoài là `List<?>`, không phải trực tiếp một wildcard. Khi xử lý danh sách bên trong, cần xét riêng ngữ cảnh kiểu của nó.

## 6. Hai wildcard không bảo đảm cùng một kiểu

Xét đoạn minh họa không hợp lệ:

```java
static void moveFirst(List<? extends Number> source,
                      List<? extends Number> target) {
    // target.set(0, source.get(0)); // Lỗi biên dịch.
}
```

Cả hai wildcard đều có cận trên `Number`, nhưng nguồn có thể là `List<Integer>` trong khi đích là `List<Double>`. Cùng cận trên chỉ cho biết các phần tử đều có thể được đọc như `Number`; nó không chứng minh kiểu phần tử nguồn và đích giống nhau.

Một phương thức trợ giúp không thể biến hai kiểu không liên quan thành cùng một kiểu. Cần viết lại hợp đồng theo điều mã thực sự cần làm, chẳng hạn:

```java
static <T> void copyFirst(List<? extends T> source,
                          List<? super T> target) {
    if (source.isEmpty() || target.isEmpty()) {
        throw new IllegalArgumentException("Both lists must be nonempty");
    }
    target.set(0, source.get(0));
}
```

Chữ ký này biểu diễn quan hệ: nguồn cung cấp một giá trị phù hợp với `T`, đích nhận được giá trị `T`. Ví dụ chuyển phần tử từ `List<Integer>` sang `List<Number>` phù hợp; chuyển tùy ý từ `List<Integer>` sang `List<Double>` vẫn bị từ chối.

Đây là sửa mô hình kiểu của API, không phải lách lỗi capture. Các đối tượng danh sách cụ thể vẫn phải hỗ trợ thao tác được gọi.

## 7. Chương trình chạy hoàn chỉnh: đảo danh sách qua capture

Ví dụ sau nhận `List<?>` ở giao diện bên ngoài, rồi dùng một `T` chung để hoán đổi hai phần tử bên trong. Lưu vào `CaptureDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class CaptureDemo {
    static void reverse(List<?> values) {
        reverseCaptured(values);
    }

    private static <T> void reverseCaptured(List<T> values) {
        int left = 0;
        int right = values.size() - 1;
        while (left < right) {
            T saved = values.get(left);
            values.set(left, values.get(right));
            values.set(right, saved);
            left++;
            right--;
        }
    }

    static <T> void copyFirst(List<? extends T> source,
                              List<? super T> target) {
        if (source.isEmpty() || target.isEmpty()) {
            throw new IllegalArgumentException("Both lists must be nonempty");
        }
        target.set(0, source.get(0));
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("Lan", "Minh", "An"));
        List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3, 4));
        List<Number> target = new ArrayList<>(List.of(0.5));

        reverse(names);
        reverse(numbers);
        System.out.println("names = " + names);
        System.out.println("numbers = " + numbers);

        List<?> unknown = names;
        reverse(unknown);
        System.out.println("names again = " + names);

        copyFirst(numbers, target);
        System.out.println("target = " + target);

        List<String> empty = new ArrayList<>();
        reverse(empty);
        System.out.println("empty = " + empty);
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 CaptureDemo.java
java CaptureDemo
```

Kết quả chuẩn:

```text
names = [An, Minh, Lan]
numbers = [4, 3, 2, 1]
names again = [Lan, Minh, An]
target = [4]
empty = []
```

Không cần biết `T` là kiểu nào để chứng minh mỗi phần tử được hoán đổi vẫn thuộc cùng kiểu phần tử của một danh sách. Đó là lợi ích cốt lõi của capture kết hợp suy luận kiểu.

`reverse` sửa danh sách gốc, không tạo bản sao. Việc biên dịch thành công không bảo đảm đối tượng hỗ trợ sửa: truyền `List.of("A", "B")` vào `reverse` sẽ gặp `UnsupportedOperationException` khi gọi `set`. Điều này thuộc hợp đồng của đối tượng danh sách, độc lập với kiểm tra kiểu generic.

## 8. Cách đọc và xử lý lỗi capture

Khi gặp thông báo có `capture of` hoặc `CAP#...`, nên làm theo thứ tự:

1. Xác định wildcard ở tham số hoặc biến nào đã dẫn tới lỗi.
2. Xác định phương thức đang yêu cầu kiểu phần tử gì: ví dụ `set(int, E)` cần `E`.
3. Xem giá trị truyền vào đang có kiểu tĩnh gì: `Object`, `Number` hay một capture khác.
4. Nếu thao tác chỉ xoay quanh **cùng một danh sách**, dùng phương thức trợ giúp generic để biểu diễn cùng kiểu bằng `T`.
5. Nếu thao tác liên quan **nhiều danh sách**, kiểm tra quan hệ nguồn–đích có thực sự được chữ ký biểu đạt chưa. Sửa chữ ký khi có quan hệ hợp lệ; từ chối thao tác khi không có quan hệ an toàn.

Có thể dùng chẩn đoán chi tiết để xem kiểu yêu cầu và kiểu được cung cấp:

```shell
javac -Xdiags:verbose CaptureError.java
```

Tên tệp này chỉ dành cho chương trình lỗi riêng mà người học tự tạo, không phải tệp `CaptureDemo.java` ở trên. Không cần ghi nhớ nguyên văn thông báo lỗi của một phiên bản JDK; cần hiểu sự thiếu hụt bằng chứng tương thích kiểu mà nó chỉ ra.

## 9. Những nhầm lẫn thường gặp

**Capture là ép kiểu lúc chạy.** Không. Đây là cơ chế kiểm tra kiểu khi biên dịch. Bản thân capture không tạo đối tượng, sao chép danh sách hoặc thêm phép kiểm tra lúc chạy.

**Trình biên dịch đã biết kiểu thật của `?`.** Không nhất thiết. Nó biết một biến kiểu với các cận và quan hệ nhất định; điều này đủ để chứng minh một số thao tác, dù không biết tên lớp cụ thể.

**`CAP#1 extends Number` có nghĩa `CAP#1` chính là `Number`.** Không. Cận trên cho phép đọc như `Number`; kiểu phần tử được biểu diễn có thể hẹp hơn.

**Hai `? extends Number` có thể đổi chỗ phần tử cho nhau.** Không. Cận giống nhau không làm hai kiểu phần tử thành cùng một kiểu.

**Thêm `@SuppressWarnings` là sửa được lỗi capture.** Không. Annotation này không biến một phép gọi sai kiểu thành hợp lệ. Kiểu thô hoặc ép kiểu không kiểm tra có thể che mất bảo đảm cần giữ, không phải giải pháp thay cho quan hệ kiểu đúng.

**Giữ lại kết quả `get` trong `var` luôn đủ.** Không. `var` suy luận một kiểu có thể dùng cho biến cục bộ; nó không tạo một tham số kiểu có tên để liên kết mọi lần sử dụng wildcard. Khi cần mối quan hệ `List<T> → T → List<T>`, hãy biểu diễn mối quan hệ ấy trực tiếp.

## 10. Tự kiểm tra cách suy luận

**Câu 1.** Tại sao phương thức `<T> void reset(List<T> values)` có thể đọc một `T` rồi đặt lại vào cùng danh sách?

Vì cùng một tham số kiểu `T` liên kết kết quả `get` với đối số của `set`. Không cần biết `T` cụ thể là lớp nào.

**Câu 2.** Một `List<? extends Number>` cho đọc ra `Number`. Tại sao không được tùy ý ghi một `Double` vào?

Vì kiểu phần tử chưa biết có thể là `Integer`. `Double` là `Number` không chứng minh nó thuộc kiểu phần tử đó.

**Câu 3.** Phương thức trợ giúp có làm một danh sách không cho sửa trở thành có thể sửa không?

Không. Nó giải quyết quan hệ kiểu lúc biên dịch; khả năng sửa vẫn do đối tượng danh sách quyết định khi chạy.

**Câu 4.** Khi nào cần `<T>` thay cho việc dùng nhiều dấu `?` độc lập?

Khi cần đặt tên và ràng buộc mối quan hệ giữa các vị trí kiểu: kết quả đọc và giá trị ghi, tham số nguồn và đích, hoặc tham số và kiểu trả về. Wildcard diễn đạt chấp nhận một kiểu chưa biết; tham số kiểu có tên giúp giữ quan hệ giữa những phần việc cần dùng cùng kiểu.
