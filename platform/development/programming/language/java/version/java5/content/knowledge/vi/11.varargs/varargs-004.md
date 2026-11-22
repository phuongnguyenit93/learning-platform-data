# Lời gọi không có đối số, một đối số hoặc nhiều đối số

## 1. Một tham số varargs nhận một dãy giá trị

Một phương thức khai báo tham số cuối dạng `T...` cho phép nơi gọi cung cấp số lượng giá trị thay đổi ở vị trí đó. Ví dụ:

```java
static String describe(String... values) {
    if (values == null) {
        return "array=null";
    }
    return "length=" + values.length + " values=" + Arrays.toString(values);
}
```

Đây là phương thức đặt trong một lớp, cần `import java.util.Arrays;`. Trong thân phương thức, `values` có kiểu `String[]`, nên có thể đọc `length`, truy cập theo chỉ số hoặc duyệt bằng `for-each`.

Với một khai báo này, có thể gọi:

```java
describe();
describe("A");
describe("A", "B", "C");
```

Ba lời gọi cung cấp lần lượt 0, 1 và 3 phần tử cho vùng varargs. Khi dùng dạng truyền các phần tử riêng lẻ như vậy, Java tổ chức những giá trị ấy thành mảng phù hợp để truyền vào phương thức.

Đây vẫn là một lời gọi phương thức, không phải ba phiên bản phương thức được sinh theo số đối số. Cơ chế vẫn dùng trong Java hiện hành; ví dụ của bài chạy bằng JDK 17 trở lên.

## 2. Không có phần tử varargs nghĩa là mảng độ dài 0

```java
describe();
```

Trong lời gọi varargs không cung cấp phần tử, tham số nhận một mảng không null có độ dài 0. Vòng `for-each` trên mảng ấy không chạy lượt nào.

Điều này không giống truyền một mảng null và cũng không giống truyền một phần tử có giá trị null.

| Lời gọi của phương thức describe | Dữ liệu tham số nhận |
| --- | --- |
| `describe()` | Mảng rỗng, độ dài 0 |
| `describe("A")` | Mảng có 1 phần tử là `"A"` |
| `describe("A", "B", "C")` | Mảng có 3 phần tử theo thứ tự đối số |

Không tự dùng `values[0]` nếu phương thức chấp nhận lời gọi không có phần tử. Cần kiểm tra độ dài hoặc chọn thuật toán xử lý được dãy rỗng.

Ví dụ một hàm cộng có thể chủ đích trả 0 khi dãy rỗng. Đó là quyết định của phần triển khai và hợp đồng phép cộng, không phải giá trị trả về mà cú pháp varargs tự áp đặt.

## 3. Một phần tử và nhiều phần tử vẫn tuân kiểu dữ liệu

Mỗi đối số được đưa vào vùng varargs phải tương thích với kiểu phần tử của mảng theo quy tắc lời gọi. Với `String...`, không được truyền một số nguyên chỉ vì số lượng đối số được thay đổi.

```java
// describe(123); // Lỗi biên dịch nếu bỏ chú thích
```

Với kiểu nguyên thủy:

```java
static int sum(int... values) {
    int total = 0;
    for (int value : values) {
        total += value;
    }
    return total;
}
```

`sum()` dùng mảng `int` rỗng và trả 0 theo phần triển khai trên; `sum(4)` trả 4; `sum(1, 2, 3)` trả 6.

Varargs không có nghĩa nhận mọi kiểu hoặc tự phân tích chuỗi thành số. Các phép chuyển hợp lệ như mở rộng nguyên thủy, boxing/unboxing khi phù hợp vẫn phụ thuộc kiểu tham số và ngữ cảnh lời gọi.

Trong ví dụ tổng, các giá trị nhỏ cho kết quả nằm trong phạm vi `int`. Với dữ liệu lớn, vẫn phải có chính sách số học/tràn số phù hợp; số đối số linh hoạt không tự đổi kiểu kết quả.

## 4. Nếu có tham số đứng trước varargs

Một phương thức có thể có các tham số bắt buộc trước tham số cuối varargs:

```java
static String report(String title, String... messages) {
    return title + ": " + describe(messages);
}
```

Các cách gọi hợp lệ:

```java
report("batch");
report("batch", "started");
report("batch", "started", "completed");
```

Trong ba lời gọi, `title` luôn được cung cấp. Phần `messages` nhận lần lượt 0, 1 và 2 phần tử. Vì vậy câu “varargs gọi được không có đối số” phải hiểu theo danh sách tham số thực tế: không có **phần tử bổ sung ở vùng varargs** không có nghĩa bỏ được tham số bắt buộc.

`report()` không hợp lệ vì thiếu `title`. Nếu API muốn bắt buộc có ít nhất một giá trị trong một dãy, có thể dùng một tham số đầu tiên riêng cùng phần varargs còn lại, hoặc kiểm tra điều kiện số lượng theo hợp đồng rõ ràng.

Java chỉ cho một tham số varargs và nó phải đứng cuối danh sách tham số. Quy tắc khai báo được nêu tại [JLS §8.4.1](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.1).

## 5. Truyền một mảng có sẵn

Vì kiểu khai báo của tham số varargs là kiểu mảng, có thể truyền trực tiếp một mảng phù hợp:

```java
String[] names = {"A", "B"};
describe(names);
describe(new String[0]);
```

Lời gọi đầu cung cấp mảng có 2 phần tử; tham số không trở thành mảng có 1 phần tử kiểu `String[]`. Lời gọi sau cung cấp mảng rỗng đã được tạo rõ ràng.

Khi truyền mảng có sẵn phù hợp với tham số, phương thức nhận tham chiếu tới mảng đó; không có lời hứa tự sao chép phòng vệ. Nếu phương thức ghi `values[0] = ...`, mảng của người gọi có thể bị thay đổi.

Ngược lại, nếu gọi `replaceFirst(original)` với một biến `String original`, đó là truyền một giá trị phần tử riêng lẻ vào vùng varargs. Việc phương thức thay ô mảng varargs không gán lại biến `original` của người gọi.

Quy tắc đóng gói đối số và truyền mảng thuộc [JLS §15.12.4.2](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12.4.2). Cần tách kiểu tham số mảng khỏi việc nơi gọi viết một biểu thức mảng hay một dãy biểu thức phần tử.

### List không được tự trải thành các đối số

Một `List<String>` không tự được chuyển thành dãy đối số `String...`. Có thể chuyển sang mảng đúng kiểu:

```java
List<String> source = List.of("X", "Y");
describe(source.toArray(String[]::new));
```

Đoạn này cần `import java.util.List;`. Dạng `toArray` dùng hàm tạo mảng có trong Java hiện hành và phù hợp với JDK 17 trở lên của ví dụ; xem [Collection.toArray](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collection.html#toArray(java.util.function.IntFunction)).

Không dùng cast một `Object[]` thành `String[]` chỉ để tránh tạo đúng loại mảng. Kiểu runtime của mảng cũng phải phù hợp.

## 6. Một phần tử null khác một mảng null

Với tham số `String...`, dùng cast rõ để diễn đạt hai trường hợp khác nhau:

```java
describe((String) null);
describe((String[]) null);
```

- `(String) null` là một phần tử: phương thức nhận mảng độ dài 1, ô đầu bằng null.
- `(String[]) null` là cả tham chiếu mảng: phương thức nhận giá trị null thay vì một mảng.

Trong ví dụ `describe`, trường hợp mảng null được kiểm tra riêng để in ra khác với mảng rỗng. Nếu thân phương thức đọc `values.length` mà không kiểm tra trong trường hợp đó, nó sẽ gây `NullPointerException`.

Còn:

```java
describe("A", null);
```

cung cấp hai phần tử riêng lẻ cho vùng varargs. Mảng nhận được có độ dài 2, chứa `"A"` và null.

Lời gọi chỉ viết `describe(null)` dễ gây nhầm và có thể tạo cảnh báo ở lời gọi: với chữ ký này, null phù hợp với tham số mảng trong cách gọi cố định. Viết cast theo đúng ý định thay vì để người đọc đoán mình muốn “không có giá trị”, “một giá trị null” hay “mảng null”.

Varargs không tự cấm phần tử null của kiểu tham chiếu. Phương thức cần kiểm tra theo hợp đồng của nó nếu từng phần tử phải có giá trị.

## 7. Chương trình chạy đầy đủ

Lưu thành `VarargsCallCountsDemo.java`:

```java
import java.util.Arrays;
import java.util.List;

public class VarargsCallCountsDemo {
    static String describe(String... values) {
        if (values == null) {
            return "array=null";
        }
        return "length=" + values.length + " values=" + Arrays.toString(values);
    }

    static int sum(int... values) {
        int total = 0;
        for (int value : values) {
            total += value;
        }
        return total;
    }

    static String report(String title, String... messages) {
        return title + ": " + describe(messages);
    }

    static void replaceFirst(String... values) {
        if (values != null && values.length > 0) {
            values[0] = "changed";
        }
    }

    public static void main(String[] args) {
        System.out.println("zero=" + describe());
        System.out.println("one=" + describe("A"));
        System.out.println("many=" + describe("A", "B", "C"));
        System.out.println("empty array=" + describe(new String[0]));
        System.out.println("ready array=" + describe(new String[] {"A", "B"}));
        System.out.println("one null=" + describe((String) null));
        System.out.println("null array=" + describe((String[]) null));
        System.out.println("two with null=" + describe("A", null));

        System.out.println("sum zero=" + sum());
        System.out.println("sum one=" + sum(4));
        System.out.println("sum many=" + sum(1, 2, 3));
        System.out.println("fixed prefix=" + report("batch"));

        List<String> source = List.of("X", "Y");
        System.out.println("from list=" + describe(source.toArray(String[]::new)));

        String[] supplied = {"old", "second"};
        replaceFirst(supplied);
        System.out.println("supplied array after call=" + Arrays.toString(supplied));

        String original = "old";
        replaceFirst(original);
        System.out.println("single variable after call=" + original);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror VarargsCallCountsDemo.java
java VarargsCallCountsDemo
```

Stdout:

```text
zero=length=0 values=[]
one=length=1 values=[A]
many=length=3 values=[A, B, C]
empty array=length=0 values=[]
ready array=length=2 values=[A, B]
one null=length=1 values=[null]
null array=array=null
two with null=length=2 values=[A, null]
sum zero=0
sum one=4
sum many=6
fixed prefix=batch: length=0 values=[]
from list=length=2 values=[X, Y]
supplied array after call=[changed, second]
single variable after call=old
```

Các dòng đầu kiểm tra số phần tử và ba ý nghĩa rỗng/null. Các dòng cuối cho thấy truyền mảng có sẵn và truyền một phần tử riêng lẻ có ảnh hưởng khác nhau khi phương thức sửa ô mảng.

`replaceFirst` cố ý sửa phần tử để minh họa cơ chế truyền. Với một API chỉ cần đọc, tránh làm thay đổi mảng của người gọi; nếu cần giữ dữ liệu để sửa độc lập, hãy xác định chính sách sao chép riêng.

## 8. Lỗi thường gặp khi suy luận theo số đối số

### Không có phần tử không có nghĩa có một phần tử mặc định

`sum()` không nhận một mảng `{0}`; nó nhận mảng rỗng. Tổng 0 đến từ biến `total` được khởi tạo trong phần triển khai. Một hàm tính giá trị lớn nhất không thể tự chọn một phần tử đầu tiên nếu dãy không có phần tử.

### Một mảng không phải một phần tử T

`describe(new String[] {"A", "B"})` nhận một mảng phù hợp làm tham số `String[]`. Nó không phải lời gọi chứa một phần tử `String` mà nội dung là mảng. Muốn nhận các mảng như từng phần tử sẽ cần một kiểu tham số khác có chủ đích.

### Không trộn mảng và các phần tử bằng cách tưởng có cú pháp trải mảng

Java không tự ghép `describe("A", existingStringArray)` thành một dãy chuỗi phẳng. Đối số mảng ở vị trí phần tử không phải `String`. Nếu cần ghép dãy, tạo dữ liệu kết hợp hoặc một mảng kết quả phù hợp trước khi gọi.

### Có overload thì số đối số chưa đủ để kết luận

Nếu API có thêm nhiều phương thức cùng tên, còn phải xét kiểu đối số và quy tắc chọn overload. Chẳng hạn hai overload `pick(int...)` và `pick(String...)` có thể khiến lời gọi `pick()` mơ hồ vì không có phần tử nào giúp chọn một kiểu phù hợp duy nhất.

Bài này dùng các tên/chữ ký không mơ hồ cho các lần gọi chính. Không xem tính hợp lệ của một lời gọi varargs đơn lẻ là bảo đảm rằng nó vẫn hợp lệ sau khi thêm mọi overload khác.

## 9. Tự kiểm tra

1. `describe()` có truyền null cho tham số mảng không?
2. `describe((String) null)` nhận mảng có bao nhiêu phần tử?
3. `describe(new String[] {"A", "B"})` nhận một hay hai phần tử trong mảng?
4. `report(String title, String... messages)` có gọi được bằng `report()` không?
5. Nếu phương thức sửa một ô của mảng có sẵn được truyền vào, mảng của người gọi có thể đổi không?

Đáp án:

1. Không. Lời gọi không cung cấp phần tử varargs dùng một mảng rỗng không null.
2. Một phần tử, và phần tử đó bằng null.
3. Mảng có hai phần tử; nó được truyền trực tiếp như tham số mảng phù hợp.
4. Không. Tham số title vẫn bắt buộc.
5. Có. Varargs không tự sao chép một mảng có sẵn để bảo vệ người gọi.

Hãy đếm phần tử của vùng varargs sau khi đã tách các tham số bắt buộc, rồi xác định nơi gọi đang truyền các phần tử riêng lẻ hay một mảng. Cách đọc đó làm rõ cả lời gọi 0, 1, nhiều phần tử và các trường hợp null.
