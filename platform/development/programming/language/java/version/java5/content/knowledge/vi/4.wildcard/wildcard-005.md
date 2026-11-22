# Quy tắc đọc và thêm phần tử đối với từng loại wildcard

## 1. Kiểm tra hai hướng sử dụng của một danh sách

Với một danh sách, đọc và thêm đi theo hai hướng ngược nhau: `get(index)` đưa một giá trị **từ danh sách ra ngoài**, còn `add(value)` đưa một giá trị **từ bên ngoài vào danh sách**.

Wildcard giữ lại một phần thông tin về kiểu phần tử. Ta cần hỏi riêng cho từng hướng: đọc ra thì được bảo đảm kiểu gì, và giá trị muốn đưa vào có chắc phù hợp với kiểu phần tử chưa biết hay không?

Ba dạng thường gặp là:

- `List<?>`: chưa nêu kiểu phần tử cụ thể.
- `List<? extends T>`: kiểu phần tử chưa biết nhưng không vượt quá giới hạn trên `T`.
- `List<? super T>`: kiểu phần tử chưa biết nhưng là `T` hoặc một kiểu cha phù hợp của `T`.

Những quy tắc này được kiểm tra khi biên dịch và vẫn áp dụng trong Java hiện hành. Chương trình trong bài dùng JDK 17 trở lên.

## 2. Bảng đọc và thêm trực tiếp

Bảng dưới nói về **đưa một giá trị từ bên ngoài vào qua chính biến có kiểu đang xét**. Nó chưa mô tả trường hợp một phương thức trợ giúp nắm bắt được kiểu phần tử chưa biết.

| Kiểu tĩnh của biến | Kiểu được bảo đảm khi đọc `get` | Giá trị có thể thêm trực tiếp về mặt kiểu |
| --- | --- | --- |
| `List<T>` với `T` đã được xác định trong phạm vi | `T` | Một giá trị tương thích với `T` |
| `List<?>` | `Object` | Không thêm tùy ý một giá trị khác `null` |
| `List<? extends T>` | `T` | Không thêm tùy ý một giá trị khác `null` chỉ dựa vào việc nó có kiểu `T` |
| `List<? super T>` | `Object` | Một giá trị kiểu `T` hoặc kiểu con phù hợp của `T` |

Các dòng `List` trong bảng dùng khai báo phần tử thông thường của `java.util.List`. Mọi dạng trên đều có thể cho phép truyền `null` về mặt tương thích kiểu tham chiếu. Tuy nhiên, đối tượng danh sách thực tế có thể từ chối sửa đổi hoặc không chấp nhận `null`.

Đọc được dưới kiểu `Object` không có nghĩa giá trị đã biến thành một đối tượng `Object` mới. Đó là mức thông tin kiểu được bảo đảm tại nơi dùng biến; đối tượng thực tế vẫn có lớp của nó.

Đối chiếu các giới hạn wildcard tại [JLS §4.5.1](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.5.1).

## 3. List<?>: đọc được Object, chưa biết phải nhận phần tử nào

```java
List<Integer> numbers = new ArrayList<>();
numbers.add(10);
List<?> unknown = numbers;

Object value = unknown.get(0);
// unknown.add(20); // Lỗi biên dịch nếu bỏ chú thích
```

Đây là đoạn lệnh trong một phương thức, cần các import `List` và `ArrayList`. `unknown` có thể đại diện danh sách số, danh sách chuỗi hoặc một kiểu danh sách khác. Vì thế một giá trị đọc ra chỉ được bảo đảm dùng như `Object`.

Không thể thêm số `20` qua hợp đồng đó: một biến `List<?>` khác hoàn toàn có thể đang tham chiếu tới `List<String>`. Tên biến hoặc hiểu biết riêng rằng lần này nó xuất phát từ `List<Integer>` không thay thế kiểu tĩnh được dùng để kiểm tra thao tác.

`List<?>` không tương đương `List<Object>`. Với một `List<Object>`, hợp đồng phần tử đã được xác định là `Object`, nên có thể thêm chuỗi, số hoặc đối tượng khác. Với `List<?>`, hợp đồng có một kiểu phần tử cụ thể chưa được nêu tên; không được mặc định rằng kiểu ấy là `Object`.

## 4. List<? extends T>: đọc theo T, không biết đủ để nhận một T bất kỳ

```java
List<Integer> counts = new ArrayList<>();
counts.add(10);
List<? extends Number> source = counts;

Number number = source.get(0);
double converted = number.doubleValue();
// source.add(Integer.valueOf(20)); // Lỗi biên dịch
// source.add(Double.valueOf(2.5)); // Lỗi biên dịch
```

Có thể hình dung kiểu phần tử là một `X` chưa biết, với `X` là kiểu con của hoặc chính `Number`. Mọi giá trị `X` có thể dùng như `Number`, nên hướng đọc an toàn theo `Number`.

Nhưng để thêm, ta cần một giá trị chắc chắn dùng được như đúng `X`. Một `Integer` không phù hợp nếu `X` là `Double`; một `Double` không phù hợp nếu `X` là `Integer`. Giới hạn trên không cung cấp đủ thông tin cho phép thêm những giá trị ấy.

Không được mặc định đọc ra `Integer`: kiểu `List<? extends Number>` cũng chấp nhận danh sách có kiểu phần tử `Double` hoặc `Number`. Nếu cần kết quả cụ thể là `Integer`, hãy giữ hợp đồng `List<Integer>` ở nơi phù hợp hoặc thiết kế quan hệ kiểu có tên.

Quy tắc thêm này áp dụng tương tự cho `set(index, value)`, vì thay phần tử cũng cần đưa một giá trị vào vị trí của kiểu phần tử chưa biết.

## 5. List<? super T>: nhận được T, đọc chỉ chắc Object

```java
List<Object> values = new ArrayList<>();
values.add("note");
List<? super Integer> destination = values;

destination.add(10);
Object first = destination.get(0);
// Integer invalid = destination.get(0); // Lỗi biên dịch
// destination.add(2.5); // Lỗi biên dịch
```

Có thể hình dung kiểu phần tử là `X`, trong đó `Integer` là kiểu con của hoặc chính `X`. Vì một `Integer` dùng được như `X`, thêm `Integer` là an toàn về kiểu.

Tuy nhiên, `X` có thể là `Object`. Danh sách ấy có thể đã chứa chuỗi như `"note"` trước khi được dùng qua biến wildcard. Vì vậy đọc một phần tử bất kỳ chỉ được bảo đảm là `Object`, không phải `Integer`.

Giới hạn dưới không có nghĩa “mọi phần tử hiện tại là T hoặc lớp cha của T”. Nó là ràng buộc trên **đối số kiểu của danh sách**, không phải một bộ lọc kiểm tra từng đối tượng. Một danh sách `Object` vẫn có thể chứa chuỗi, số và những đối tượng khác.

Với `List<? super Number>`, có thể thêm các giá trị `Number` và các kiểu con như `Integer`, `Double`. Nhưng không được thêm một `Object` bất kỳ hoặc một chuỗi chỉ vì danh sách thực tế trong một lần chạy có thể là `List<Object>`.

`? super Integer` không nhận trực tiếp một danh sách có kiểu phần tử `Double`: `Double` không phải kiểu cha của `Integer`. Các quan hệ kế thừa phải được kiểm tra đúng hướng.

## 6. Kết hợp nguồn đọc và đích nhận

Một thuật toán đọc phần tử từ nguồn và thêm sang đích thường có dạng:

```java
static <T> void appendAll(
        List<? extends T> source, List<? super T> destination) {
    for (T item : source) {
        destination.add(item);
    }
}
```

Nguồn cung cấp giá trị đọc được như `T`; đích có thể nhận `T`. Nhờ vậy có thể chuyển từ `List<Integer>` sang một `List<Number>` hoặc `List<Object>`.

Đây là ý nghĩa thực hành của quy tắc PECS: **Producer Extends, Consumer Super**. “Nguồn” và “đích” là vai trò trong thao tác hiện tại, không phải thuộc tính vĩnh viễn của đối tượng danh sách.

Phương thức minh họa này thêm vào cuối đích bằng `add`, không thay phần tử theo chỉ số. Trong các ví dụ chạy, nguồn và đích là những danh sách riêng, và đích là `ArrayList` hỗ trợ thêm. Wildcard không tự bảo đảm một đối tượng đích bất kỳ cho phép sửa đổi.

Khi cùng một cấu trúc phải được dùng để nhận và trả lại đúng một kiểu có tên trong thuật toán, `List<T>` có thể rõ hơn wildcard. Không nên chọn wildcard chỉ bằng việc thấy phương thức có một lệnh đọc hoặc một lệnh ghi; cần xem toàn bộ quan hệ kiểu của API.

## 7. Wildcard không quyết định tính bất biến hoặc quyền sửa đổi

`List<?>` và `List<? extends T>` có thể gọi những thao tác như `remove(index)` hoặc `clear()` về mặt kiểu. Chúng không cần truyền vào một giá trị có kiểu phần tử chưa biết.

Vì vậy không thể kết luận hai dạng này là các danh sách không bao giờ thay đổi. Phép gán một biến wildcard cũng không sao chép dữ liệu: sửa qua một tham chiếu hợp lệ có thể được quan sát qua tham chiếu khác tới cùng danh sách.

Ngược lại, dù `List<? super T>` cho phép một lệnh `add` về mặt kiểu, danh sách thực tế có thể không cho thêm và ném `UnsupportedOperationException`. Nếu đối tượng không nhận `null`, một thao tác thêm `null` được biên dịch vẫn có thể thất bại theo hợp đồng API.

Tách ba câu hỏi:

1. Giá trị truyền vào có tương thích với kiểu tĩnh không?
2. Đối tượng danh sách có hỗ trợ thao tác thêm/thay/xóa đó không?
3. Dữ liệu có đáp ứng điều kiện riêng như không `null`, đúng chỉ số hoặc đúng quy tắc nghiệp vụ không?

Chỉ câu hỏi đầu được giải quyết trực tiếp bằng các quy tắc wildcard trong bài. Hợp đồng thao tác sửa đổi của danh sách nằm trong tài liệu [List](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html).

## 8. Trường hợp nắm bắt kiểu: thêm lại một phần tử đã có

Câu “không thêm được giá trị khác null vào List<?>” chỉ là cách nói rút gọn về thao tác trực tiếp với một giá trị từ bên ngoài. Một phương thức generic có thể nắm bắt kiểu phần tử chưa biết và giữ đúng quan hệ giữa đọc và thêm:

```java
static void duplicateFirst(List<?> values) {
    duplicateCaptured(values);
}

private static <E> void duplicateCaptured(List<E> values) {
    if (!values.isEmpty()) {
        values.add(values.get(0));
    }
}
```

`duplicateCaptured` không đoán kiểu phần tử là `Object`, `String` hay `Integer`. Nó đặt tên `E` cho đúng kiểu được nắm bắt trong lần gọi, đọc ra một `E` rồi thêm lại một `E` vào cùng danh sách.

Đây là thao tác an toàn kiểu nếu danh sách hỗ trợ thêm. Nó tạo thêm một tham chiếu tới phần tử đang có, không sao chép sâu đối tượng phần tử. Cơ chế này không cho phép tùy ý đưa một giá trị ngoài kiểu `Object` vào danh sách.

Phần nắm bắt wildcard được quy định tại [JLS §5.1.10](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.10).

## 9. Chương trình chạy đầy đủ

Lưu thành `WildcardReadWriteDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class WildcardReadWriteDemo {
    static <T> void appendAll(
            List<? extends T> source, List<? super T> destination) {
        for (T item : source) {
            destination.add(item);
        }
    }

    static void duplicateFirst(List<?> values) {
        duplicateCaptured(values);
    }

    private static <E> void duplicateCaptured(List<E> values) {
        if (!values.isEmpty()) {
            values.add(values.get(0));
        }
    }

    public static void main(String[] args) {
        List<Integer> original = new ArrayList<>(List.of(10, 20));
        List<?> unknown = original;
        List<? extends Number> upper = original;

        Object unknownValue = unknown.get(0);
        Number upperValue = upper.get(1);
        System.out.println("unknown read=" + unknownValue);
        System.out.println("upper read=" + upperValue);

        List<Number> numericDestination = new ArrayList<>();
        List<Object> broadDestination = new ArrayList<>();
        broadDestination.add("note");
        appendAll(original, numericDestination);
        appendAll(original, broadDestination);

        List<? super Integer> lower = broadDestination;
        lower.add(30);
        Object lowerValue = lower.get(0);
        System.out.println("numeric destination=" + numericDestination);
        System.out.println("broad destination=" + broadDestination);
        System.out.println("lower read=" + lowerValue);

        unknown.remove(0);
        unknown.add(null);
        System.out.println("original after changes=" + original);

        List<String> words = new ArrayList<>(List.of("A"));
        List<?> anonymous = words;
        duplicateFirst(anonymous);
        System.out.println("captured duplicate=" + words);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 -Xlint:all -Werror WildcardReadWriteDemo.java
java WildcardReadWriteDemo
```

Stdout:

```text
unknown read=10
upper read=20
numeric destination=[10, 20]
broad destination=[note, 10, 20, 30]
lower read=note
original after changes=[20, null]
captured duplicate=[A, A]
```

`lower` nhận thêm `Integer` an toàn, nhưng phần tử đầu đọc ra lại là chuỗi đã có trong danh sách `Object`. Điều đó giải thích vì sao kiểu đọc bảo đảm chỉ là `Object`.

`unknown.remove(0)` và `unknown.add(null)` thay đổi chính danh sách `original`, minh họa việc wildcard không tạo bản sao hay cấm mọi thao tác sửa. Phương thức trợ giúp sau đó thêm lại một phần tử của danh sách chuỗi mà không ép kiểu hoặc che cảnh báo.

## 10. Những suy luận sai thường gặp

### “Tôi biết đối tượng thực tế nên có thể bỏ qua kiểu biến”

Trình biên dịch kiểm tra lời gọi qua kiểu tĩnh của biểu thức. Nếu cần thao tác qua hợp đồng `List<Integer>`, hãy giữ một tham chiếu có kiểu đó tại nơi thiết kế cho phép; đừng ép một wildcard về kiểu cụ thể chỉ vì dữ liệu thử nghiệm hiện đang phù hợp.

### “Đọc được Number thì chắc thêm lại Number được”

Không. `Number` đọc từ một `List<? extends Number>` đã mất tên kiểu phần tử chính xác trong biến nhận. Một `Number` từ nguồn này cũng không chắc phù hợp với kiểu phần tử chưa biết của nguồn khác.

Hai wildcard trông giống nhau không tự có cùng kiểu được nắm bắt. Muốn truyền giá trị giữa hai nguồn/đích phải có quan hệ kiểu chung phù hợp, như chữ ký `appendAll`.

### “? super T đọc được T vì đã thêm T vào”

Một lệnh thêm không chứng minh mọi vị trí trong danh sách đều là `T`, và kiểu tĩnh của biến không tự thu hẹp sau lệnh thêm. Danh sách có thể đã chứa dữ liệu khác phù hợp với đối số kiểu rộng hơn của nó.

### “Thêm null biên dịch được thì chắc chạy được”

Không. Tính tương thích kiểu, khả năng sửa đổi và chính sách `null` là những điều kiện riêng. Hãy đọc hợp đồng của đối tượng thực thi, đặc biệt khi danh sách được tạo từ một API không cho sửa.

## 11. Tự kiểm tra

1. `List<?>` và `List<Object>` có cho phép cùng các lệnh thêm không?
2. Với `List<? extends Number>`, có thể đọc trực tiếp vào biến `Integer` không?
3. Với `List<? super Integer>`, có thể thêm `Integer` và đọc trực tiếp ra `Integer` không?
4. Vì sao nguồn `List<Integer>` có thể chuyển phần tử sang đích `List<Number>` qua `appendAll`?
5. Một phương thức generic có thể thêm lại phần tử sẵn có của `List<?>` mà không ép kiểu không?

Đáp án:

1. Không. `List<Object>` cho phép thêm các giá trị tham chiếu phù hợp với `Object`; `List<?>` chưa biết kiểu phần tử cụ thể nên không cho tùy ý thêm chúng.
2. Không chỉ dựa vào kiểu đó; mức bảo đảm là `Number`.
3. Thêm được về mặt kiểu, nhưng đọc một vị trí bất kỳ chỉ chắc là `Object`.
4. Chọn một `T` phù hợp để nguồn cung cấp giá trị như `T` và đích nhận được `T`; quan hệ `extends`/`super` mô tả đúng hai hướng.
5. Có, bằng cách nắm bắt kiểu phần tử thành `E`, đọc một `E` và thêm lại cùng kiểu đó, với điều kiện đối tượng hỗ trợ thao tác.

Để quyết định một lệnh đọc hay thêm có hợp lệ, hãy theo dõi hướng đi của giá trị và phần thông tin kiểu còn được giữ lại. Sau kiểm tra kiểu, vẫn cần kiểm tra riêng khả năng sửa đổi và điều kiện dữ liệu của danh sách.
