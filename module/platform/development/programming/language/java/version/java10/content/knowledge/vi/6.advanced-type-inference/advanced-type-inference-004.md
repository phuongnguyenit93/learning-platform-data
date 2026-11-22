# Wildcard capture trong suy luận kiểu cục bộ với `var` (Java 10+)

## 1. Tại sao wildcard capture liên quan đến `var`?

Trong Java, generic cho phép dùng **wildcard** `?` để nói rằng một kiểu tham số là chưa biết, có thể đi kèm giới hạn trên hoặc dưới:

```java
List<?> unknown;                   // không biết kiểu phần tử
List<? extends Number> producer;   // kiểu phần tử là một kiểu con nào đó của Number
List<? super Integer> consumer;    // kiểu phần tử là một kiểu cha nào đó của Integer
```

Đoạn trên chỉ minh họa **kiểu khai báo**, cần `import java.util.List;` và khởi tạo các biến trước khi sử dụng. Dấu `?` không có nghĩa là kiểu động: trình biên dịch vẫn kiểm tra được phép đọc, ghi và truyền giá trị nào là an toàn.

**Wildcard capture** là bước trình biên dịch tạm thời gắn một **biến kiểu nội bộ mới** cho wildcard khi cần kiểm tra một biểu thức. Ví dụ, trong một lời gọi phương thức generic nhận `List<T>`, đối số `List<? extends Number>` có thể được xem là `List<CAP#1>` với `CAP#1` là một kiểu chưa biết nhưng có giới hạn trên `Number`. Tên như `CAP#1` chỉ là cách trình biên dịch mô tả kiểu trong chẩn đoán; người lập trình không khai báo tên này.

`var` suy luận kiểu **tĩnh của biến cục bộ** từ biểu thức khởi tạo. Khi quá trình suy luận biểu thức tạo ra một kiểu chứa **capture variable**, Java áp dụng **upward projection** để chọn một kiểu phù hợp cho biến mà **không để capture variable nội bộ rò rỉ qua câu lệnh khai báo**. Đây là quy tắc trong Java Language Specification (JLS) `14.4.1 và `4.10.5.

Điều này tạo ra hai hệ quả:

1. `var` vẫn có thể cho kiểu như `List<? extends Number>`, `List<? super Integer>` hoặc `List<?>`. Wildcard là một phần của kiểu được sử dụng; `var` không tự động xóa mọi wildcard.
2. Những biến capture tạm thời do compiler sinh ra trong biểu thức được chuyển thành dạng kiểu có thể tồn tại an toàn trong phạm vi biến cục bộ. Với trường hợp thường gặp, kiểu suy luận sẽ giữ **giới hạn wildcard** thay vì “giả vờ” biết chính xác kiểu phần tử.

## 2. Phân biệt wildcard, capture và upward projection

Xét phương thức generic:

```java
static <T> List<T> forward(List<T> input) {
    return input;
}
```

Đây là một phương thức `static` minh họa, nằm trong một lớp có `import java.util.List;`.

Giả sử trong một phương thức khác có đoạn:

```java
List<? extends Number> source = List.of(1, 2, 3);
var result = forward(source); // kiểu của result: List<? extends Number>
```

**Luồng giải thích về mặt kiểu:**

1. `source` khai báo kiểu `List<? extends Number>`. Ta không biết chính xác phần tử là `Integer`, `Double` hay một subtype nào khác của `Number` chỉ bằng kiểu khai báo này.
2. Khi đối chiếu đối số với tham số `List<T>`, trình biên dịch có thể **capture** wildcard thành biến kiểu nội bộ, ví dụ `CAP#1 extends Number`. Nhờ vậy lời gọi generic có thể xử lý một kiểu nhất quán trong phạm vi kiểm tra biểu thức.
3. Kết quả biểu thức `forward(source)` có thể liên quan đến `List<CAP#1>` trong quá trình suy luận.
4. Khi khai báo `var result = ...`, **upward projection** loại bỏ tham chiếu capture nội bộ khỏi kiểu biến. Với ví dụ này, kiểu dùng cho `result` là `List<? extends Number>`.

Mục tiêu không phải là “làm mất” giới hạn kiểu. `result.get(0)` vẫn đọc được dưới dạng `Number`; `result.add(123)` vẫn bị từ chối vì không biết chính xác subtype được capture. Nếu dùng `List<Number>` thay thế, ta có thể cho phép chèn `Double` vào danh sách thực tế chỉ chấp nhận `Integer`, gây mất an toàn kiểu.

Bảng tóm tắt:

| Khái niệm | Ý nghĩa | Mức tồn tại |
| --- | --- | --- |
| `? extends Number` | Một kiểu phần tử chưa biết, được giới hạn trên bởi `Number` | Kiểu wildcard có thể viết trong mã |
| `CAP#1 extends Number` | Biến kiểu tạm do compiler tạo khi capture wildcard | Nội bộ bước kiểm tra biểu thức |
| `List<? extends Number>` của `result` | Kiểu tĩnh sau suy luận/projection | Có thể dùng ở các câu lệnh tiếp theo |
| `Number` từ `result.get(0)` | Kiểu an toàn khi đọc phần tử | Kiểu tĩnh của biến nhận kết quả |

Lưu ý: Đây là mô hình giải thích những trường hợp điển hình, không phải mô phỏng từng bước của thuật toán suy luận trong mọi biểu thức. JLS quy định chính xác capture conversion, type inference và type projection; kết quả còn phụ thuộc vào chữ ký phương thức, type bounds và ngữ cảnh.

## 3. Ba dạng wildcard và kiểu mà `var` nhận

### `? extends T`: đọc giá trị dưới dạng `T`, không tự ý chèn một `T`

```java
List<? extends Number> numbers = new ArrayList<Integer>(List.of(1, 2));
var sameNumbers = forward(numbers); // List<? extends Number>
var first = sameNumbers.get(0);     // Number

Number value = sameNumbers.get(0);  // hợp lệ
// sameNumbers.add(3);             // lỗi biên dịch
// sameNumbers.add(3.5);           // lỗi biên dịch
```

Mảng/danh sách thực tế có thể chứa `Integer`; dù `Number` là kiểu cha an toàn để **đọc**, ta không được chèn một số `Double` hoặc `Integer` tùy ý vì wildcard có thể đại diện cho một subtype khác. `sameNumbers.add(null)` hợp lệ về kiểm tra kiểu của lời gọi `List.add`, nhưng không phải cách thêm phần tử có ý nghĩa; danh sách cũng cần cho phép sửa ở runtime.

### `? super T`: có thể ghi `T`, đọc dưới dạng `Object`

```java
List<? super Integer> sink = new ArrayList<Number>();
var sameSink = forward(sink); // List<? super Integer>
sameSink.add(10);            // hợp lệ
sameSink.add(20);            // hợp lệ
Object first = sameSink.get(0); // Object
// Integer exact = sameSink.get(0); // lỗi biên dịch: chỉ chắc chắn là Object
```

Trình biên dịch không biết chính xác `sink` là `List<Integer>`, `List<Number>` hay `List<Object>`. Chèn `Integer` là an toàn; đọc thẳng thành `Integer` thì không thể bảo đảm.

### `?`: không biết giới hạn phần tử cụ thể

```java
List<?> source = new ArrayList<String>(List.of("A", "B"));
var sameSource = forward(source); // List<?>
Object item = sameSource.get(0);  // hợp lệ
// sameSource.add("C");           // lỗi biên dịch
```

Có thể hiểu `?` như `? extends Object` ở mức kiểu. Dù đối tượng runtime đang là `ArrayList<String>`, `var` không “nhìn vào dữ liệu” để biến nó thành `List<String>`.

**Quy tắc PECS** vẫn hữu ích: *Producer Extends, Consumer Super*. `var` không làm thay đổi những quyền đọc/ghi do wildcard quy định.

## 4. Một trường hợp quan trọng: `new ArrayList<>(source)` vẫn giữ wildcard

Đây là tình huống rất dễ suy luận sai:

```java
List<? extends Number> source = new ArrayList<Integer>(List.of(1, 2));

var copy = new ArrayList<>(source);
// kiểu của copy được suy luận: ArrayList<? extends Number>

// copy.add(3); // lỗi biên dịch: kiểu phần tử của copy chưa được biết chính xác
```

`copy` là một `ArrayList` mới, nhưng **kiểu tĩnh của nó vẫn có wildcard**. Diamond ở constructor dùng các ràng buộc từ `source` và từ đó có thể sinh ra kiểu chứa capture. Sau quy tắc projection, trong trường hợp này biến nhận kiểu `ArrayList<? extends Number>`. Đừng suy ra rằng hễ đối tượng mới là collection mutable thì kiểu tĩnh của biến cho phép chèn một `Number` bất kỳ.

Nếu cần một **bản sao có kiểu phần tử rõ ràng và được phép bổ sung Number**, cung cấp type argument tường minh hoặc kiểu đích:

```java
var writableCopy = new ArrayList<Number>(source); // ArrayList<Number>
writableCopy.add(3.5);                            // hợp lệ

List<Number> anotherCopy = new ArrayList<>(source);
anotherCopy.add(4.5);                             // hợp lệ
```

Điều này an toàn: mọi phần tử lấy từ `source` đều là subtype của `Number`, nên có thể sao chép vào danh sách mới có kiểu `Number`. Phép sao chép không biến `source` thành `List<Number>`; bản gốc vẫn là `List<? extends Number>` và không cho phép thêm `Number` tùy ý.

| Biểu thức khai báo | Kiểu tĩnh | Có thể gọi `add(3.5)`? |
| --- | --- | --- |
| `var a = forward(source);` | `List<? extends Number>` | Không |
| `var b = new ArrayList<>(source);` | `ArrayList<? extends Number>` | Không |
| `var c = new ArrayList<Number>(source);` | `ArrayList<Number>` | Có |
| `List<Number> d = new ArrayList<>(source);` | `List<Number>` | Có |

Bảng trên giả định `source` là `List<? extends Number>` và các lệnh nằm trong phạm vi phương thức cho phép tạo/gán biến cục bộ.

## 5. Capture trong phương thức generic: giải quyết lỗi `capture of ?`

Một tình huống thường gặp không do riêng `var` tạo ra là đọc rồi gán lại chính phần tử trong một `List<?>`:

```java
static void writeBack(List<?> list) {
    // list.set(0, list.get(0)); // lỗi biên dịch liên quan đến capture of ?
}
```

Lý do: khi kiểm tra lời gọi `set`, compiler cần một đối số có **đúng kiểu phần tử chưa biết** của danh sách. Biểu thức `get(0)` ở ngoài ngữ cảnh ràng buộc thường được xét với một capture riêng; vì thế Java không tự kết luận hai bước độc lập là cùng một type variable đủ để gọi `set` an toàn.

Cách giải quyết đúng là chuyển cả hai thao tác vào **một generic helper** có tham số kiểu `T` chung:

```java
static void writeBack(List<?> list) {
    writeBackCaptured(list);
}

private static <T> void writeBackCaptured(List<T> list) {
    list.set(0, list.get(0)); // cả get và set dùng cùng T
}
```

Đây là hai phương thức **minh họa, chưa phải chương trình chạy độc lập**. Khi gọi `writeBackCaptured(list)`, capture conversion giúp suy luận `T` đại diện cho đúng kiểu phần tử chưa biết của **danh sách được truyền vào**. Trong thân helper, `T` trở thành một quan hệ kiểu rõ ràng được sử dụng thống nhất bởi `get` và `set`.

Một phiên bản dùng `var` ở phía gọi:

```java
List<? extends Number> source = new ArrayList<Integer>(List.of(1, 2));
var result = forward(source); // List<? extends Number>
writeBackCaptured(result);    // hợp lệ: capture ở lời gọi phương thức
```

`var` không làm mất capture conversion khi **gọi phương thức**. Nó chỉ không cho biến capture tạm của **biểu thức khởi tạo** tồn tại trực tiếp làm kiểu khai báo qua các câu lệnh sau. Những câu lệnh mới vẫn có thể tạo capture tạm khi cần kiểm tra các phương thức generic.

**Lưu ý runtime:** `set` vẫn có thể ném `UnsupportedOperationException` nếu list thực tế không hỗ trợ sửa phần tử, hoặc `IndexOutOfBoundsException` nếu list rỗng. Ví dụ runnable bên dưới dùng `ArrayList` có phần tử nên không gặp hai lỗi này.

## 6. Vì sao không thể gán trực tiếp giữa các biến wildcard?

Capture conversion không làm các kiểu generic trở thành kiểu hiệp biến. Trong Java, `List<Integer>` **không phải** subtype của `List<Number>`, và hai wildcard chưa biết có thể biểu thị hai kiểu hoàn toàn khác nhau.

```java
List<? extends Number> ints = List.of(1, 2);
List<? extends Number> doubles = List.of(1.5, 2.5);

// ints.addAll(doubles); // lỗi biên dịch: không thể đảm bảo kiểu phần tử khớp
// List<Number> exact = ints; // lỗi: List<? extends Number> không phải List<Number>
```

Dù cả `ints` và `doubles` có thể đọc được như `Number`, không thể coi chúng có cùng kiểu phần tử chính xác. Tên capture kiểu `CAP#1` và `CAP#2` trong thông báo lỗi thể hiện các kiểu chưa biết, không phải các lớp Java được sinh ra ở runtime.

Khi cần ghép các giá trị dưới dạng `Number`, tạo collection đích phù hợp rồi sao chép các phần tử:

```java
List<Number> merged = new ArrayList<>();
merged.addAll(ints);
merged.addAll(doubles); // hợp lệ: đích có kiểu Number
```

Giải pháp dựa trên **kiểu đích đủ rộng** và quyền đọc từ nguồn, không ép kiểu không an toàn hoặc dùng raw type.

## 7. `var` không gây mất kiểu tĩnh, cũng không xác định kiểu từ runtime

Xét:

```java
List<? extends Number> numbers = new ArrayList<Integer>(List.of(1, 2));
var selected = numbers.get(0);       // kiểu tĩnh Number
var forwarded = forward(numbers);   // kiểu tĩnh List<? extends Number>
```

- `selected` có kiểu `Number` vì kết quả `get(0)` ở mức biểu thức chỉ có thể đảm bảo là một subtype của `Number`. Việc projection loại bỏ capture nội bộ có thể được hình dung là chọn **giới hạn trên**.
- `forwarded` giữ ràng buộc wildcard ở kiểu generic `List<? extends Number>`; không bị thay thành `List<Number>` hoặc raw `List`.
- Nếu `selected.getClass().getSimpleName()` trả về `Integer` thì đó là **lớp runtime** của đối tượng, không phải bằng chứng rằng kiểu tĩnh của `selected` là `Integer`.
- Sau khi khai báo, kiểu tĩnh của biến `var` được cố định. Lời gọi `get` hoặc `add` trong các câu lệnh tiếp theo không khiến Java suy luận lại biến.

Đặc tả JLS nêu một ví dụ khác:

```java
var clazz = "x".getClass(); // kiểu tĩnh: Class<? extends String>
```

Lời gọi `Object.getClass()` có kiểu kết quả liên quan đến capture/type parameter trong cách đặc tả nó; kiểu khai báo của `clazz` được projection thành `Class<? extends String>`. Điều này cho thấy projection có thể xuất hiện ngay cả khi người viết mã **không gõ dấu `?`** trong biểu thức.

## 8. Ví dụ đầy đủ có thể chạy trên Java 17+

Lưu tệp `WildcardCaptureVarDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class WildcardCaptureVarDemo {

    static <T> List<T> forward(List<T> values) {
        return values;
    }

    static <T> void writeFirstBack(List<T> values) {
        values.set(0, values.get(0));
    }

    public static void main(String[] args) {
        List<? extends Number> producer =
                new ArrayList<Integer>(List.of(1, 2, 3));

        var projectedProducer = forward(producer); // List<? extends Number>
        var first = projectedProducer.get(0);     // Number

        var projectedCopy = new ArrayList<>(producer);
        // projectedCopy có kiểu ArrayList<? extends Number>
        // projectedCopy.add(4); // lỗi biên dịch

        var writableCopy = new ArrayList<Number>(producer);
        writableCopy.add(4.5); // hợp lệ

        List<? super Integer> consumer = new ArrayList<Number>();
        var projectedConsumer = forward(consumer); // List<? super Integer>
        projectedConsumer.add(10);
        projectedConsumer.add(20);
        Object consumerFirst = projectedConsumer.get(0);

        List<?> unknown = new ArrayList<String>(List.of("A", "B"));
        var projectedUnknown = forward(unknown); // List<?>
        Object unknownFirst = projectedUnknown.get(0);

        writeFirstBack(projectedProducer);
        writeFirstBack(projectedUnknown);

        var stringClass = "Java".getClass(); // Class<? extends String>

        System.out.println("producer=" + producer);
        System.out.println("first=" + first
                + ", runtime=" + first.getClass().getSimpleName());
        System.out.println("projectedCopy=" + projectedCopy);
        System.out.println("writableCopy=" + writableCopy);
        System.out.println("consumer=" + consumer + ", read=" + consumerFirst);
        System.out.println("unknown=" + unknown + ", read=" + unknownFirst);
        System.out.println("class=" + stringClass.getSimpleName());
    }
}
```

Biên dịch và chạy:

```bash
javac WildcardCaptureVarDemo.java
java WildcardCaptureVarDemo
```

Kết quả:

```text
producer=[1, 2, 3]
first=1, runtime=Integer
projectedCopy=[1, 2, 3]
writableCopy=[1, 2, 3, 4.5]
consumer=[10, 20], read=10
unknown=[A, B], read=A
class=String
```

Những điểm cần hiểu khi đối chiếu kết quả:

- `projectedProducer` và `projectedCopy` còn wildcard giới hạn trên: chúng cho phép đọc `Number` nhưng không cho thêm một `Number` cụ thể tùy ý.
- `writableCopy` được tạo bằng `ArrayList<Number>` nên có thể thêm `4.5`. Điều này không thay đổi `producer`.
- `projectedConsumer` có wildcard giới hạn dưới: thêm `Integer` được, nhưng giá trị đọc ra chỉ chắc chắn kiểu `Object`.
- `projectedUnknown` có kiểu `List<?>`; phương thức `writeFirstBack` được truyền qua generic helper để gán lại phần tử thuộc cùng kiểu capture.
- `runtime=Integer` mô tả đối tượng runtime; nó không thay đổi kiểu tĩnh `Number` của `first`.

## 9. Lỗi thường gặp và hướng xử lý

| Lỗi hoặc hiểu nhầm | Nguyên nhân chính | Hướng xử lý |
| --- | --- | --- |
| Nghĩ `var x = forward(list)` sẽ suy ra `List<Integer>` khi `list` là `List<? extends Number>` | Kiểu tĩnh chỉ biết wildcard, không biết subtype cụ thể | Giữ `List<? extends Number>`, đọc thành `Number` hoặc thay đổi chữ ký API khi có đủ thông tin |
| Nghĩ `new ArrayList<>(source)` luôn tạo `ArrayList<Number>` | Diamond có thể suy luận kiểu chứa wildcard/capture từ nguồn | Dùng `new ArrayList<Number>(source)` khi cần đích thêm được các `Number` |
| Gọi `list.set(0, list.get(0))` trên `List<?>` | Hai phép kiểm tra cần một kiểu phần tử thống nhất | Truyền list vào helper `<T> void helper(List<T>)` |
| Gán `List<Integer>` trực tiếp vào `List<Number>` | Generic invariance | Dùng wildcard cho API đọc hoặc tạo collection `List<Number>` mới |
| Dùng cast cưỡng ép `(List<Number>) someWildcardList` | Có nguy cơ không an toàn kiểu, che giấu quan hệ generic thật | Giữ wildcard và dùng helper có ràng buộc; tránh unchecked cast |
| Dùng raw `List` để né lỗi `capture of ?` | Mất kiểm tra kiểu generic | Giữ kiểu generic, sửa quan hệ type parameter hoặc thiết kế API |
| Tưởng `getClass()` tiết lộ kiểu đối số generic | Type erasure và kiểu runtime khác với kiểu tĩnh | Kiểm tra kiểu từ chữ ký API và biểu thức ở compile time |

Trong các API thực tế, wildcard thường xuất hiện ở tham số kiểu nguồn/đích. **Thiết kế phương thức generic có type parameter `T`** khi cần bảo toàn quan hệ giữa các giá trị cùng một kiểu chưa biết; dùng wildcard khi chỉ cần ràng buộc đọc hoặc ghi. `var` có thể giảm độ dài khai báo nhưng không thể thay thế việc thiết kế ràng buộc kiểu đúng.

## 10. Bài tập tự kiểm tra

Cho phương thức `forward` trong phần 2 và đoạn sau:

```java
List<? extends Number> a = List.of(1, 2);
List<? super Integer> b = new ArrayList<Number>();
List<?> c = List.of("x");

var x = forward(a);
var y = forward(b);
var z = forward(c);

var valueX = x.get(0);
var valueY = y.get(0);
var valueZ = z.get(0);
// x.add(9);
// y.add(9);
```

Hãy xác định kiểu của `x`, `y`, `z`, `valueX`, `valueY`, `valueZ` và hai câu lệnh `add`.

**Đáp án:**

1. `x`: `List<? extends Number>`; `valueX`: `Number`.
2. `y`: `List<? super Integer>`; `valueY`: `Object`.
3. `z`: `List<?>`; `valueZ`: `Object`.
4. `x.add(9)` **không hợp lệ** vì chưa biết subtype của `Number` mà `x` chấp nhận; `y.add(9)` **hợp lệ** vì wildcard `? super Integer` cho phép thêm `Integer` (số `9` được boxing).

Tất cả các kết luận trên dựa vào **kiểu tĩnh**, không dựa vào nội dung danh sách tại runtime.

**Ghi nhớ:** Java capture wildcard như một biến kiểu tạm trong quá trình kiểm tra generic. Với biến cục bộ `var`, JLS yêu cầu **upward projection** loại bỏ capture variable nội bộ khỏi kiểu được giữ lại. Kết quả có thể vẫn là một **kiểu chứa wildcard**, để bảo toàn những ràng buộc đọc/ghi và tính an toàn của generic.

## Tài liệu tham khảo chính thức

- [Java Language Specification, Java SE 26, `14.4.1 — Local Variable Declarators and Types](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-14.html#jls-14.4.1): kiểu của biến `var` là upward projection của kiểu biểu thức khởi tạo.
- [Java Language Specification, Java SE 26, `4.10.5 — Type Projections](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-4.html#jls-4.10.5): các quy tắc loại bỏ tham chiếu synthetic type variables.
- [Java Language Specification, Java SE 26, `5.1.10 — Capture Conversion](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-5.html#jls-5.1.10): capture của wildcard.
- [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): thiết kế của `var` được giới thiệu ở Java 10.
