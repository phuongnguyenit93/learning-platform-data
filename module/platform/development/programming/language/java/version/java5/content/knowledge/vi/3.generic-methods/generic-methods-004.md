# Suy luận đối số kiểu từ lời gọi phương thức

## 1. Không ghi đối số kiểu không có nghĩa là bỏ kiểm tra kiểu

Với phương thức generic, bên gọi thường không phải ghi đối số kiểu tường minh. Trình biên dịch có thể xác định các đối số kiểu phù hợp từ biểu thức đối số và ngữ cảnh của lời gọi. Cơ chế này gọi là **suy luận kiểu (type inference)**.

```java
static <T> T echo(T value) {
    return value;
}
```

Khi dùng `String text = echo("hello")`, trình biên dịch có đủ dữ kiện để lời gọi trả về một giá trị phù hợp với `String`. Không cần viết `Example.<String>echo("hello")` trong trường hợp thông thường.

Điều được suy luận là **đối số kiểu tại thời điểm biên dịch**, không phải nội dung dữ liệu hoặc lớp thực tế được đoán khi chương trình đang chạy. Phương thức vẫn phải có khai báo `<T>` và một phần thân hợp lệ với các ràng buộc đã khai báo.

Bài này dùng quy tắc Java hiện hành, với ví dụ chạy bằng Java 17 trở lên. Các đoạn ngắn minh họa câu lệnh đặt trong phương thức; phần chương trình đầy đủ có đủ import và lệnh chạy.

## 2. Các nguồn dữ kiện của một lời gọi

Một cách đọc hữu ích là xét đồng thời ba nhóm thông tin:

| Nguồn dữ kiện | Ví dụ | Điều nó ràng buộc |
| --- | --- | --- |
| Kiểu tĩnh của đối số | `echo("hello")` | Đối số phải phù hợp với tham số `T` |
| Kiểu đích khi ngữ cảnh hỗ trợ | `List<String> names = freshList()` | Kết quả lời gọi phải phù hợp với `List<String>` |
| Giới hạn khai báo | `<T extends Number>` | Đối số kiểu phải thỏa điều kiện đã đặt |

Trình biên dịch phải tìm cách thỏa các ràng buộc liên quan, không đơn giản “lấy kiểu của đối số đầu tiên”. Đối với lời gọi lồng nhau, suy luận còn có thể dùng thông tin từ ngữ cảnh của lời gọi bên ngoài.

Đây là mô hình để đọc mã; quy trình hình thức của Java còn xét tính áp dụng của phương thức, các phép chuyển đổi được cho phép và việc chọn overload. Không cần tự triển khai thuật toán suy luận để dùng generic an toàn.

## 3. Suy luận từ kiểu tĩnh của đối số

### Một tham số kiểu, một đối số

Với `echo` ở trên:

```java
String title = echo("Guide");
Integer count = echo(4);
```

Ở dòng đầu, biểu thức đối số có kiểu `String`. Ở dòng sau, giá trị `int` được boxing thành `Integer` trong lời gọi generic; đối số kiểu là một kiểu tham chiếu, không phải `int`.

Kết quả không cần ép kiểu ở bên gọi. Tuy nhiên, suy luận không chuyển dữ liệu sang một loại khác theo mong muốn tùy ý:

```java
// String text = echo(4); // Lỗi biên dịch: Integer không trở thành String.
```

Muốn có chuỗi biểu diễn số, cần thao tác chuyển đổi thật như `String.valueOf(4)`. Kiểu đích không tự thêm phép chuyển đổi nghiệp vụ đó.

### Kiểu thực tế của đối tượng không thay thế kiểu tĩnh

```java
Object input = "Guide";
var result = echo(input);
// int length = result.length(); // Lỗi biên dịch: result có kiểu Object.
```

Biến `input` có kiểu tĩnh `Object`; trình biên dịch không dựa vào việc nó đang giữ một chuỗi để suy luận `T` thành `String` trong lời gọi này. `result` vì vậy có kiểu `Object`.

Chỉ định `<String>` tường minh cũng không bỏ qua điều kiện đó: `Example.<String>echo(input)` không hợp lệ nếu `input` vẫn là biểu thức kiểu `Object`. Cần kiểm tra dữ liệu để có một biểu thức kiểu `String`, hoặc thiết kế lại kiểu của biến nguồn.

## 4. Nhiều đối số cùng tham gia suy luận

```java
static <T> T chooseFirst(T first, T second) {
    return first;
}
```

Phương thức đặt cùng một `T` ở hai tham số và kiểu trả về. Nó không yêu cầu hai đối số phải có cùng lớp thực tế; chúng phải cùng phù hợp với một cách chọn `T` hợp lệ trong ngữ cảnh.

```java
Integer sameKind = chooseFirst(3, 5);
Number mixedNumbers = chooseFirst(3, 5.5);
```

Lời gọi thứ hai hợp lệ: các giá trị được boxing thành `Integer` và `Double`, rồi dùng một kiểu tham chiếu chung phù hợp với ngữ cảnh `Number`. Kiểu chung được suy luận trong những trường hợp phức tạp có thể bao gồm các giao diện chung hoặc kiểu giao (intersection type); không nên khẳng định mọi tổ hợp khác kiểu đều luôn suy luận đúng bằng `Object` hay đúng bằng tên lớp cha mà ta nhìn thấy.

Điều quan trọng về hành vi: phương thức trả lại đối tượng thứ nhất. `mixedNumbers` vẫn giữ một đối tượng `Integer`; suy luận generic không tự đổi số `3` thành đối tượng `Double` chỉ vì đối số thứ hai là `5.5`.

Ngược lại:

```java
// Integer bad = chooseFirst(3, 5.5); // Lỗi biên dịch.
```

Lời gọi không có cách chọn kiểu đồng thời đáp ứng đối số `Double` và yêu cầu kết quả phù hợp với `Integer` theo hợp đồng đã khai báo. Không sửa bằng ép kiểu mù; hãy xem yêu cầu kết quả hoặc chữ ký phương thức có đúng ý định hay không.

## 5. Kiểu đích giúp lời gọi không có dữ kiện từ đối số

Xét một phương thức tạo danh sách rỗng có thể thay đổi:

```java
static <T> java.util.List<T> freshList() {
    return new java.util.ArrayList<>();
}
```

Nó không nhận tham số giá trị, nên không có đối số để cung cấp trực tiếp kiểu phần tử. Nhưng phép gán có thể cung cấp **kiểu đích (target type)**:

```java
java.util.List<String> words = freshList();
words.add("hello");
```

Trong ngữ cảnh này, kết quả cần phù hợp với `List<String>`. Do `List` bất biến theo tham số kiểu, sự tương thích ấy xác định kiểu phần tử phù hợp cho lời gọi là `String`.

Ngữ cảnh cũng có thể đến từ tham số của một phương thức bao ngoài. Ví dụ sau là các phương thức đặt trong cùng một lớp, với import `java.util.List`:

```java
static int countNames(List<String> names) {
    return names.size();
}

static int countEmptyNames() {
    return countNames(freshList());
}
```

Tham số `List<String>` của `countNames` cung cấp ngữ cảnh cho lời gọi `freshList()` bên trong. Không cần tạo một biến tạm chỉ để ghi lại đối số kiểu, dù biến tạm có thể giúp đọc hoặc gỡ lỗi.

Thư viện chuẩn có những lời gọi tương tự như `List<String> empty = java.util.Collections.emptyList()`. Cần tách chuyện suy luận khỏi chuyện khả năng thay đổi: `Collections.emptyList()` không cho thêm phần tử, còn `freshList()` trong bài trả về `ArrayList` nên cho thêm.

## 6. var không cung cấp kiểu đích cho biểu thức khởi tạo

So sánh:

```java
java.util.List<String> explicitTarget = freshList();
var inferredWithoutTarget = freshList();
```

Dòng đầu đặt yêu cầu kết quả là `List<String>`. Trong dòng thứ hai, `var` yêu cầu suy ra kiểu của biến từ biểu thức khởi tạo; nó không cung cấp trước một kiểu phần tử mong muốn. Với phương thức `freshList` không giới hạn trong ví dụ, kết quả được suy luận thành `List<Object>`.

Vì vậy:

```java
inferredWithoutTarget.add("hello");
inferredWithoutTarget.add(7); // Hợp lệ: đây là List<Object>.
```

Điều đó không có nghĩa `var` luôn tạo `Object`. Khi đối số cung cấp thông tin cụ thể, kiểu có thể rất cụ thể:

```java
var word = echo("hello"); // String.
int length = word.length();
```

Nếu một factory không có đối số thể hiện kiểu phần tử, thường nên ghi kiểu biến rõ ràng hoặc chỉ định đối số kiểu tại lời gọi khi đó là ý định của API. Đừng mong trình biên dịch nhìn các lệnh `add` trong tương lai để suy luận lại kiểu của biến đã khai báo.

## 7. null cung cấp ít thông tin kiểu hơn một đối tượng cụ thể

```java
String text = echo(null);
var unknown = echo(null);
```

Dòng đầu có kiểu đích `String`, nhưng giá trị kết quả vẫn là `null`. Dòng sau không có kiểu đích cụ thể và đối số `null` không xác định được một lớp tham chiếu riêng; với khai báo `echo` không giới hạn trong bài, kiểu của `unknown` là `Object`.

Suy luận thành công không chứng minh dữ liệu an toàn để gọi phương thức. `text.length()` sẽ gây `NullPointerException` trong ví dụ đó. Việc chấp nhận `null`, cung cấp giá trị mặc định hoặc từ chối dữ liệu thiếu là hợp đồng cần thiết kế riêng.

Không nên sửa một lỗi `null` bằng cách ép trình biên dịch chọn một kiểu cụ thể. Chọn đối số kiểu chỉ thay đổi kiểm tra kiểu tại lời gọi; nó không tạo ra một đối tượng khác `null`.

## 8. Giới hạn kiểu và các kiểu generic hiện có vẫn được giữ

### Suy luận phải tuân thủ giới hạn khai báo

```java
static <N extends Number> N keepNumber(N value) {
    return value;
}
```

`keepNumber(10)` hợp lệ, nhưng `keepNumber("10")` không hợp lệ vì `String` không đáp ứng giới hạn `Number`. Suy luận không chọn một kiểu bất kỳ chỉ để cho lời gọi vượt qua giới hạn.

### Không tự mở rộng List<String> thành List<Object>

```java
static <T> void append(java.util.List<T> target, T value) {
    target.add(value);
}
```

Với `List<String> names`, kiểu của đối số danh sách ràng buộc `T` theo hợp đồng `List<T>`:

```java
java.util.List<String> names = new java.util.ArrayList<>();
append(names, "Lan");
// append(names, 20); // Lỗi biên dịch.
```

Trình biên dịch không chọn `T = Object` rồi bỏ qua việc `List<String>` không phải `List<Object>`. Nếu làm vậy, một số nguyên có thể bị đưa vào danh sách vốn hứa chỉ chứa chuỗi.

Khi lỗi suy luận xuất hiện, hãy đọc toàn bộ các vị trí chứa cùng tham số kiểu: một đối số generic như `List<T>` có thể đặt ràng buộc mạnh hơn trực giác chỉ nhìn vào `T value`.

Ngay cả lời gọi đúng kiểu cũng không bảo đảm `append` chạy được với mọi đối tượng danh sách. `append(List.of("a"), "b")` phù hợp về kiểu nhưng danh sách không cho thay đổi nên ném `UnsupportedOperationException`.

## 9. Chỉ định đối số kiểu tường minh khi cần

```java
var names = TypeInferenceDemo.<String>freshList();
```

Cú pháp `<String>` nằm sau dấu chấm và trước tên phương thức. Nó chọn đối số kiểu rõ ràng cho lời gọi, nên `names` có kiểu `List<String>` dù dùng `var`.

Cũng có thể viết `TypeInferenceDemo.<Number>chooseFirst(3, 5.5)` nếu muốn chọn chính xác `Number` cho tham số kiểu ở lời gọi đó. Những đối số giá trị vẫn phải phù hợp với `Number`.

Dùng chỉ định tường minh để làm rõ ý định hoặc xử lý ngữ cảnh ít thông tin; không coi nó là công cụ ép một đối số sai kiểu trở thành hợp lệ. `TypeInferenceDemo.<String>echo(3)` vẫn sai. Không dùng kiểu nguyên thủy như `<int>`; dùng lớp bao phù hợp khi cần.

Nếu tên lớp chứa phương thức khác với `TypeInferenceDemo`, thay phần tên lớp theo mã thực tế. Đây là chỉ định kiểu của **phương thức**, khác vị trí với đối số kiểu của lớp trong `new ArrayList<String>()`.

## 10. Chương trình chạy đầy đủ

Lưu thành **`TypeInferenceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class TypeInferenceDemo {
    static <T> T echo(T value) {
        return value;
    }

    static <T> T chooseFirst(T first, T second) {
        return first;
    }

    static <T> List<T> freshList() {
        return new ArrayList<>();
    }

    static <N extends Number> N keepNumber(N value) {
        return value;
    }

    static <T> void append(List<T> target, T value) {
        target.add(value);
    }

    static int countNames(List<String> names) {
        return names.size();
    }

    public static void main(String[] args) {
        var title = echo("Guide");
        Integer quantity = echo(4);
        System.out.println("length=" + title.length());
        System.out.println("quantity=" + quantity);

        Number selected = chooseFirst(3, 5.5);
        System.out.println("selected=" + selected);
        System.out.println("class=" + selected.getClass().getSimpleName());

        List<String> names = freshList();
        append(names, "Lan");
        System.out.println("names=" + names);
        System.out.println("empty count=" + countNames(freshList()));

        var mixed = freshList();
        mixed.add("x");
        mixed.add(7);
        System.out.println("mixed=" + mixed);

        var typed = TypeInferenceDemo.<String>freshList();
        typed.add("y");
        System.out.println("typed=" + typed);
        System.out.println("number=" + keepNumber(9));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all TypeInferenceDemo.java
java TypeInferenceDemo
```

Stdout chính xác:

```text
length=5
quantity=4
selected=3
class=Integer
names=[Lan]
empty count=0
mixed=[x, 7]
typed=[y]
number=9
```

Chương trình cho thấy dữ kiện có thể đến từ đối số, kiểu biến, lời gọi bao ngoài hoặc đối số kiểu được ghi tường minh. Dòng `class=Integer` kiểm chứng rằng suy luận một kiểu chung không chuyển đổi lớp thực tế của đối tượng được trả lại.

## 11. Cách đọc một lỗi suy luận

Khi trình biên dịch thông báo các giới hạn không tương thích, kiểm tra theo thứ tự:

1. Tìm khai báo `<T>`, `<K, V>` hoặc giới hạn `extends` của phương thức đang gọi.
2. Thay mỗi tham số giá trị bằng **kiểu tĩnh** của biểu thức đối số tại nơi gọi; đừng chỉ nhìn lớp của đối tượng khi chạy.
3. Xét kiểu đích từ phép gán hoặc tham số bao ngoài nếu có. Với `var`, không giả định đã có kiểu đích mong muốn.
4. Kiểm tra quan hệ kiểu của collection và các vị trí dùng cùng tham số kiểu; `List<String>` không tự trở thành `List<Object>`.
5. Quyết định sửa dữ liệu, chữ ký hoặc ngữ cảnh kiểu theo đúng ý định. Chỉ thêm đối số kiểu tường minh nếu nó mô tả một lời gọi vốn hợp lệ.

Không dùng ép kiểu không được kiểm tra chỉ để làm biến mất thông báo. Một lỗi suy luận có thể đang chỉ ra rằng các yêu cầu đặt lên cùng một lời gọi mâu thuẫn với nhau.

## 12. Tự thực hành

1. Từ chương trình đầy đủ, khai báo `Object source = "abc"; var result = echo(source);`. Giải thích vì sao không gọi trực tiếp được `result.length()`.
2. So sánh `List<Integer> numbers = freshList()` với `var numbers = freshList()`. Thử thêm một chuỗi vào từng trường hợp và quan sát khác biệt khi biên dịch.
3. Thử `Integer bad = chooseFirst(1, 2.5)` rồi giải thích những yêu cầu nào mâu thuẫn. Khôi phục mã hợp lệ trước khi chạy.
4. Gọi `keepNumber` với `Long`, `Double` và `String`; xác định trường hợp không thỏa giới hạn khai báo.
5. Thử `String value = echo(null)` nhưng không gọi phương thức trên giá trị đó. Phân biệt “có kiểu hợp lệ” với “có đối tượng khác null”.

Suy luận đối số kiểu giúp lời gọi gọn hơn, đồng thời giữ ràng buộc của generic. Để đoán đúng kết quả, cần đọc cả chữ ký, kiểu tĩnh của các đối số và ngữ cảnh dùng kết quả; không dựa riêng vào nội dung dữ liệu hoặc kiểu mong muốn của người viết.

## Tài liệu đối chiếu

- [JLS §18.5.1 — Invocation Applicability Inference](https://docs.oracle.com/javase/specs/jls/se25/html/jls-18.html#jls-18.5.1): suy luận khi kiểm tra khả năng áp dụng phương thức.
- [JLS §18.5.2 — Invocation Type Inference](https://docs.oracle.com/javase/specs/jls/se25/html/jls-18.html#jls-18.5.2): suy luận kiểu của lời gọi và ngữ cảnh đích.
- [JLS §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12): kiểm tra lời gọi ở thời điểm biên dịch và thực thi khi chạy.
