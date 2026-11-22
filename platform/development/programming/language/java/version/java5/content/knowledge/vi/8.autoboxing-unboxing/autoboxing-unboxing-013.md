# Phân biệt remove(int) và remove(Object) của List<Integer>

## 1. Một tên phương thức, hai yêu cầu xóa khác nhau

`List` cung cấp hai overload cùng tên `remove`:

```java
// Chữ ký API, không phải phần thân phương thức để chép vào lớp:
// E remove(int index)
// boolean remove(Object value)
```

Khi tham chiếu có kiểu `List<Integer>`, `E` là `Integer`:

| Overload | Ý nghĩa | Giá trị trả về |
| --- | --- | --- |
| `Integer remove(int index)` | Xóa phần tử tại chỉ số, tính từ 0 | Phần tử vừa bị xóa |
| `boolean remove(Object value)` | Xóa lần xuất hiện đầu tiên bằng giá trị cần tìm | `true` nếu danh sách thay đổi do xóa được phần tử |

Hai thao tác khác nhau dù đối số nhìn giống một con số. Với danh sách số nguyên, phải phân biệt **số dùng làm vị trí** với **số dùng làm giá trị cần xóa**.

Các ví dụ trong bài dùng API hiện hành và chạy bằng Java 17 trở lên. Những danh sách cần sửa đều được tạo bằng `ArrayList`, không dùng danh sách không cho thay đổi làm nguồn thí nghiệm xóa.

## 2. Truyền int: xóa theo chỉ số

Đặt các câu lệnh sau trong một phương thức, với import `java.util.List` và `java.util.ArrayList`:

```java
List<Integer> numbers = new ArrayList<>(List.of(10, 20, 10, 30));
Integer removed = numbers.remove(1);
System.out.println(removed); // 20
System.out.println(numbers); // [10, 10, 30]
```

Literal `1` có kiểu `int`. Overload `remove(int)` phù hợp trực tiếp, nên phần tử ở chỉ số 1 — phần tử thứ hai — bị xóa. Java không tự hiểu `1` là “hãy tìm giá trị số 1” chỉ vì danh sách chứa `Integer`.

Các phần tử đứng sau vị trí bị xóa dịch về chỉ số nhỏ hơn. Chỉ số dùng cho lời gọi tiếp theo phải được đọc theo trạng thái danh sách mới, không phải theo vị trí trước khi xóa.

Nếu chỉ số âm hoặc không nhỏ hơn kích thước hiện tại, `remove(int)` ném `IndexOutOfBoundsException`. Nó không trả về `false` khi chỉ số không hợp lệ.

## 3. Truyền Integer: xóa theo giá trị

```java
List<Integer> numbers = new ArrayList<>(List.of(10, 20, 10, 30));
boolean changed = numbers.remove(Integer.valueOf(10));
System.out.println(changed); // true
System.out.println(numbers); // [20, 10, 30]
```

Đối số có kiểu `Integer`. Nó có thể được mở rộng thành `Object` mà không cần unboxing, nên overload `remove(Object)` được chọn. Overload `remove(int)` sẽ cần unbox, nhưng không thắng phương thức đã áp dụng được ở giai đoạn phù hợp trước đó của quá trình chọn overload.

`remove(Object)` chỉ xóa **lần xuất hiện đầu tiên** bằng giá trị cần tìm. Vì thế, số `10` thứ hai vẫn còn trong danh sách.

Phép tìm dựa trên quan hệ bằng nhau theo hợp đồng của API, không dựa vào việc hai wrapper có dùng chung đối tượng cache hay không. Với `Integer`, `equals` so sánh giá trị giữa các đối tượng cùng lớp `Integer`.

Nếu không tìm được giá trị, phương thức trả về `false` và không xóa phần tử nào, giả sử đối tượng hỗ trợ thao tác đó và không có điều kiện từ chối riêng của implementation.

## 4. Kiểu của biến đối số thay đổi ý nghĩa lời gọi

```java
List<Integer> numbers = new ArrayList<>(List.of(10, 20, 10, 30));
Integer selection = 1;
boolean changed = numbers.remove(selection);
```

Dòng cuối xóa **giá trị 1**, không xóa phần tử ở chỉ số 1. Vì nguồn không có số 1, kết quả là `false` và danh sách giữ nguyên.

Nếu `selection` thực sự mang ý nghĩa chỉ số, hãy chuyển sang primitive có chủ đích sau khi kiểm tra điều kiện dữ liệu:

```java
int index = selection.intValue();
Integer removed = numbers.remove(index);
```

Nếu biến có ý nghĩa giá trị cần xóa và đang là primitive, tạo đối số wrapper rõ ràng:

```java
int valueToRemove = 10;
boolean changed = numbers.remove(Integer.valueOf(valueToRemove));
```

Cast sang `Object` cũng chọn được overload giá trị, nhưng `Integer.valueOf` thường diễn đạt rõ rằng ta muốn tìm một phần tử số nguyên. Không dùng constructor wrapper deprecated để phân biệt hai overload.

### Bảng chọn overload thường gặp

Giả sử biến nhận phương thức có kiểu `List<Integer>`:

| Đối số | Overload được chọn | Ý nghĩa |
| --- | --- | --- |
| `1` hoặc biến `int` | `remove(int)` | Xóa vị trí 1 |
| `Integer.valueOf(1)` hoặc biến `Integer` | `remove(Object)` | Tìm và xóa giá trị 1 |
| `(Object) 1` | `remove(Object)` | Boxing số 1 rồi tìm giá trị `Integer` 1 |
| `null` | `remove(Object)` | Tìm phần tử null, nếu được implementation hỗ trợ |
| `1L` hoặc biến `long` | `remove(Object)` | Boxing thành `Long`; không phải xóa vị trí 1 |

Dòng `long` dễ gây ngạc nhiên: Java không tự thu hẹp `long` thành `int` để dùng làm chỉ số. Nó có thể boxing thành `Long` rồi dùng overload nhận `Object`.

## 5. Giá trị tìm sai lớp wrapper vẫn có thể biên dịch

```java
List<Integer> numbers = new ArrayList<>(List.of(10, 20));
boolean changed = numbers.remove(10L);
System.out.println(changed); // false
```

`10L` trở thành đối tượng `Long` cho lời gọi `remove(Object)`. Một `Long` mang giá trị 10 không bằng một `Integer` mang giá trị 10 theo hợp đồng `equals` của các wrapper này.

Tương tự, `numbers.remove("10")` có thể biên dịch vì tham số của overload là `Object`, nhưng một chuỗi không bằng phần tử `Integer` 10.

Điều đó không phải generic mất hiệu lực. API đang nhận một đối tượng để **truy vấn và xóa nếu khớp**, không nhận một giá trị mới để thêm vào danh sách. Chính chữ ký `remove(Object)` cho phép các truy vấn ấy.

Nếu chương trình có quy tắc đầu vào chặt hơn, hãy xác minh kiểu/miền giá trị tại nơi nhận dữ liệu. Đừng coi việc phương thức trả `false` là bằng chứng chắc chắn rằng người dùng chỉ gõ một giá trị không tồn tại; có thể mã đã truyền sai kiểu đối số.

## 6. Kiểu trả về không dùng để ép chọn overload

```java
List<Integer> numbers = new ArrayList<>(List.of(10, 20));
// boolean changed = numbers.remove(1); // Lỗi biên dịch.
```

Đối số `1` đã dẫn tới `remove(int)`, trả `Integer`. Việc bên trái muốn `boolean` không làm compiler quay lại đổi lời gọi thành `remove(Object)` để tìm giá trị 1.

Cách viết đúng cho mục đích xóa theo giá trị:

```java
boolean changed = numbers.remove(Integer.valueOf(1));
```

Nếu dùng `var`, kiểu kết quả cũng phụ thuộc overload đã chọn:

```java
var removedItem = numbers.remove(0); // Kiểu Integer.
var removedValue = numbers.remove(Integer.valueOf(20)); // Kiểu boolean.
```

Cần xem trạng thái danh sách ở thời điểm mỗi lời gọi diễn ra. Ví dụ hai dòng dùng `var` ở trên minh họa kiểu kết quả, không đảm bảo rằng số 20 vẫn còn trong mọi trạng thái nguồn khác.

## 7. Kiểu tham chiếu nhận phương thức cũng quan trọng

Xét cùng một đối tượng được nhìn qua `Collection<Integer>`:

```java
List<Integer> numbers = new ArrayList<>(List.of(10, 20, 10, 30));
java.util.Collection<Integer> collection = numbers;
boolean changed = collection.remove(10);
```

`Collection` có `remove(Object)` nhưng không có overload `remove(int index)` của `List`. Vì vậy, số nguyên primitive được boxing cho lời gọi xóa theo giá trị. Phần tử `Integer` 10 đầu tiên bị xóa.

Đối tượng thực tế vẫn là `ArrayList`, nhưng tập overload để chọn ở nơi gọi dựa trên kiểu tĩnh của biểu thức nhận phương thức. Không suy ra ý nghĩa của `remove(10)` chỉ bằng tên lớp của đối tượng lúc chạy.

Trong API của riêng mình, tên thao tác rõ như `removeAt(index)` và `removeValue(value)` có thể giúp giảm nhầm lẫn nếu hai khái niệm thường bị trộn lẫn. Với `List` chuẩn, chọn kiểu đối số rõ ràng ở nơi gọi là cách trực tiếp nhất.

## 8. null có hai vị trí gây hành vi khác nhau

### null làm đối số xóa theo giá trị

```java
List<Integer> numbers = new ArrayList<>(java.util.Arrays.asList(1, null, 2));
Integer value = null;
boolean changed = numbers.remove(value);
```

Vì `value` có kiểu `Integer`, overload nhận `Object` được chọn; không cần unbox đối số. Với `ArrayList` có chứa null như trên, thao tác xóa phần tử null và trả về `true`.

Nếu viết `numbers.remove(value.intValue())`, việc gọi `intValue()` trên null gây `NullPointerException` trước khi phương thức xóa được gọi. Hai cách viết không tương đương.

### Phần tử được xóa là null rồi kết quả bị unbox

```java
List<Integer> numbers = new ArrayList<>(java.util.Arrays.asList(null, 2));
// int removed = numbers.remove(0);
```

Nếu chạy dòng đang chú thích, `remove(int)` xóa thành công phần tử null ở vị trí 0 và trả về `Integer null`. Sau đó phép gán sang primitive `int` cần unbox kết quả và gây `NullPointerException`.

Lúc lỗi xuất hiện, danh sách **đã thay đổi**. Không coi một ngoại lệ ở toàn biểu thức là bảo đảm rằng phương thức xóa chưa thực hiện tác động phụ.

Nếu cần giữ khả năng null của phần tử trả về, nhận kết quả bằng `Integer` và xử lý theo hợp đồng dữ liệu. Nếu ứng dụng cấm phần tử null, xác minh điều kiện ấy trước khi dùng primitive như một bảo đảm có sẵn.

## 9. Chương trình chạy đầy đủ

Lưu thành **`IntegerListRemoveDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;

public class IntegerListRemoveDemo {
    static List<Integer> sample() {
        return new ArrayList<>(List.of(10, 20, 10, 30));
    }

    public static void main(String[] args) {
        List<Integer> byIndex = sample();
        Integer removed = byIndex.remove(1);
        System.out.println("index removed=" + removed + ", list=" + byIndex);

        List<Integer> byValue = sample();
        boolean changed = byValue.remove(Integer.valueOf(10));
        System.out.println("value removed=" + changed + ", list=" + byValue);

        List<Integer> byBoxed = sample();
        Integer selection = 1;
        boolean boxedChanged = byBoxed.remove(selection);
        System.out.println("boxed 1 removed=" + boxedChanged + ", list=" + byBoxed);

        List<Integer> byCollection = sample();
        Collection<Integer> collection = byCollection;
        boolean collectionChanged = collection.remove(10);
        System.out.println("collection removed=" + collectionChanged
                + ", list=" + byCollection);

        List<Integer> byLong = sample();
        boolean longChanged = byLong.remove(10L);
        System.out.println("long removed=" + longChanged + ", list=" + byLong);

        List<Integer> nullable = new ArrayList<>(Arrays.asList(1, null, 2, null));
        Integer nullValue = null;
        boolean nullChanged = nullable.remove(nullValue);
        System.out.println("null removed=" + nullChanged + ", list=" + nullable);

        try {
            nullable.remove(nullValue.intValue());
        } catch (NullPointerException ex) {
            System.out.println("null index rejected");
        }

        List<Integer> nullResult = new ArrayList<>(Arrays.asList(null, 2));
        try {
            int value = nullResult.remove(0);
            System.out.println(value);
        } catch (NullPointerException ex) {
            System.out.println("return unboxing failed, list=" + nullResult);
        }

        try {
            byIndex.remove(99);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("invalid index rejected");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all IntegerListRemoveDemo.java
java IntegerListRemoveDemo
```

Stdout chính xác:

```text
index removed=20, list=[10, 10, 30]
value removed=true, list=[20, 10, 30]
boxed 1 removed=false, list=[10, 20, 10, 30]
collection removed=true, list=[20, 10, 30]
long removed=false, list=[10, 20, 10, 30]
null removed=true, list=[1, 2, null]
null index rejected
return unboxing failed, list=[2]
invalid index rejected
```

Mỗi trường hợp chính dùng một danh sách mới để kết quả không bị trộn với tác động của lần xóa trước. Trường hợp `return unboxing failed` kiểm chứng danh sách đã bỏ phần tử trước khi phép gán primitive thất bại.

## 10. Xóa tất cả giá trị và thay đổi trong lúc duyệt

`remove(Object)` chỉ xóa một lần xuất hiện đầu tiên. Nếu yêu cầu là xóa mọi số 10 khỏi một danh sách có thể thay đổi, diễn đạt bằng thao tác phù hợp, ví dụ:

```java
List<Integer> numbers = new ArrayList<>(List.of(10, 20, 10, 30));
boolean changed = numbers.removeIf(value -> Integer.valueOf(10).equals(value));
System.out.println(numbers); // [20, 30]
```

Predicate trên xử lý được phần tử null theo ý nghĩa “null không bằng Integer 10”. `removeIf` hiện hành giải quyết một yêu cầu khác với hai overload đã phân tích; nó không đổi nghĩa của `remove(10)`.

Không xóa trực tiếp bằng `numbers.remove(...)` trong một vòng for-each thông thường rồi mong `continue` sẽ làm việc đó an toàn. Nếu vừa duyệt vừa xóa, dùng `Iterator.remove`, `removeIf` hoặc một chiến lược phù hợp với collection và yêu cầu cụ thể.

Ngoài ra, overload đúng không bảo đảm đối tượng hỗ trợ xóa. Các danh sách không cho thay đổi như danh sách tạo bằng `List.of` có thể ném `UnsupportedOperationException` khi gọi thao tác xóa. Tách vấn đề “chọn phương thức nào” khỏi vấn đề “đối tượng có cho phép thực hiện thao tác ấy không”.

## 11. Cách kiểm tra nhanh một lời gọi remove

1. Xác định kiểu tĩnh của biểu thức nhận lời gọi: `List<Integer>`, `Collection<Integer>` hay một API khác.
2. Xác định kiểu tĩnh của đối số: `int`, `Integer`, `long`, `Object` hay null literal.
3. Nêu rõ ý định: xóa vị trí hay xóa một giá trị. Viết đối số sao cho ý định đó hiện ra trong mã.
4. Xét giá trị trả về theo overload đã chọn; đừng dùng kiểu biến nhận để đoán ngược phương thức.
5. Kiểm tra chỉ số, null và quyền thay đổi của danh sách trước khi kết luận về hành vi khi chạy.

## 12. Tự thực hành

1. Với nguồn `[5, 1, 5, 9]`, dự đoán rồi chạy riêng `remove(1)` và `remove(Integer.valueOf(1))`. Lưu ý ở dữ liệu này hai thao tác có thể tình cờ cùng bỏ số 1; đổi nguồn để thấy khác biệt rõ hơn.
2. Truyền một biến `Integer index = 2` vào `remove` trên `List<Integer>`. Giải thích vì sao tên biến “index” không quyết định overload.
3. Gọi `remove(5L)` trên danh sách có `Integer 5`. Giải thích kết quả bằng kiểu wrapper và `equals`.
4. Dùng cùng một `ArrayList<Integer>` qua biến `List<Integer>` và biến `Collection<Integer>`. So sánh `remove(1)` ở hai nơi gọi mà không bỏ thông tin generic.
5. Tạo danh sách có null ở vị trí 0, nhận kết quả `remove(0)` bằng `Integer` rồi bằng `int` trong hai lần thí nghiệm độc lập. Phân biệt thời điểm xóa với thời điểm unboxing kết quả.

Với `List<Integer>`, sự khác nhau giữa chỉ số nguyên thủy và giá trị wrapper là một phần trực tiếp của hợp đồng lời gọi. Đọc đúng kiểu tham chiếu, kiểu đối số và kiểu trả về giúp tránh xóa nhầm phần tử hoặc hiểu sai một ngoại lệ sau khi dữ liệu đã thay đổi.

## Tài liệu đối chiếu

- [List.remove(int)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html#remove(int)): xóa theo chỉ số và trả phần tử bị xóa.
- [List.remove(Object)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html#remove(java.lang.Object)): xóa lần xuất hiện đầu tiên theo giá trị.
- [JLS §15.12.2 — Determine Method Signature](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12.2): các giai đoạn lựa chọn phương thức overload.
- [Integer.equals(Object)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Integer.html#equals(java.lang.Object)): quan hệ bằng nhau của wrapper số nguyên.
