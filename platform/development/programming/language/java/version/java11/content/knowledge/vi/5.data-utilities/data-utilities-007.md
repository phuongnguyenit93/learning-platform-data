# Overload `toArray` và trường hợp gọi `null` bị mơ hồ trong Java 11+

## 1. Vấn đề: vì sao `toArray(null)` có thể không biên dịch?

Khi chuyển một `Collection` (ví dụ `List<String>`) thành mảng, Java cung cấp các cách gọi `toArray` khác nhau. Từ **Java 11**, interface `java.util.Collection` có thêm overload nhận hàm tạo mảng `IntFunction<T[]>`. Hai overload nhận **một đối số** đều có thể nhận biểu thức `null` về mặt kiểu tham chiếu; vì vậy lời gọi `collection.toArray(null)` không xác định được overload nào cần chọn.

Đây là **lỗi mơ hồ khi biên dịch (overload ambiguity)**. Compiler không thể biết `null` đang đại diện cho một mảng `T[]` hay một hàm tạo mảng `IntFunction<T[]>`. Đây không phải lỗi “danh sách có giá trị `null`” và cũng không phải việc runtime chọn sai overload.

Kiến thức này **vẫn áp dụng trên các phiên bản Java hiện đại**. Cách viết an toàn và rõ nghĩa là dùng một mảng cụ thể như `new String[0]`, hoặc method reference `String[]::new` — thay vì truyền `null`.

## 2. Ba dạng `Collection.toArray` hiện hành

| Chữ ký | Đầu vào | Kiểu mảng trả về | Khi nào dùng |
| --- | --- | --- | --- |
| `Object[] toArray()` | Không có đối số | `Object[]` | Khi API sử dụng `Object[]` hoặc không cần mảng có kiểu thành phần cụ thể. |
| `<T> T[] toArray(T[] array)` | Một mảng đã có | Mảng có kiểu runtime đúng với kiểu mảng truyền vào | Khi muốn nhận `String[]`, `Integer[]`... hoặc có mảng đủ chỗ để tái sử dụng. |
| `<T> T[] toArray(IntFunction<T[]> generator)` | Hàm tạo mảng, ví dụ `String[]::new` | Mảng do hàm tạo mảng cung cấp | Cách viết gọn, rõ kiểu mảng cần nhận; overload này có từ Java 11. |

Cả ba phương thức đều thuộc `Collection`; vì `List` mở rộng `Collection`, ta có thể gọi chúng trên `List<String>`. Với `List`, thứ tự phần tử của mảng kết quả đúng với thứ tự trong danh sách.

Lưu ý về `toArray(T[] array)`:

- Nếu mảng truyền vào **đủ lớn**, phương thức có thể điền phần tử và trả về **chính mảng đó**.
- Nếu mảng **không đủ lớn**, phương thức tạo mảng mới cùng kiểu thành phần runtime và trả về mảng mới.
- Nếu mảng lớn hơn số phần tử, ô ngay sau phần tử cuối cùng được đặt thành `null`. Không nên suy ra toàn bộ những ô còn lại đều bị xóa.
- Đối số mảng `null` gây `NullPointerException` **nếu overload này đã được chọn**; nhưng lời gọi không ép kiểu `toArray(null)` có thể bị từ chối ngay ở giai đoạn biên dịch.

Lưu ý về `toArray(IntFunction<T[]> generator)`: đối số là một hàm `int -> T[]` tạo mảng, không phải một `T[]` có sẵn. **Implementation mặc định của `Collection` gọi `generator.apply(0)`**, rồi chuyển mảng nhận được sang `toArray(T[])`. Vì thế, không nên mặc định cho rằng tham số của generator luôn bằng `collection.size()`; hãy dùng constructor reference `String[]::new` hoặc biểu thức `size -> new String[size]` đúng quy tắc.

## 3. Ví dụ Java chạy được: các overload hợp lệ

Lưu chương trình sau vào **`ToArrayOverloadsDemo.java`**:

```java
import java.util.Arrays;
import java.util.List;

public class ToArrayOverloadsDemo {
    public static void main(String[] args) {
        List<String> names = List.of("Lan", "Minh", "An");

        Object[] objects = names.toArray();
        String[] typed = names.toArray(new String[0]);
        String[] viaConstructor = names.toArray(String[]::new);
        String[] viaLambda = names.toArray(size -> new String[size]);

        String[] buffer = new String[5];
        String[] reused = names.toArray(buffer);

        System.out.println("objects=" + Arrays.toString(objects));
        System.out.println("typed=" + Arrays.toString(typed));
        System.out.println("constructor=" + Arrays.toString(viaConstructor));
        System.out.println("lambda=" + Arrays.toString(viaLambda));
        System.out.println("objectComponent=" +
                objects.getClass().getComponentType().getSimpleName());
        System.out.println("typedComponent=" +
                typed.getClass().getComponentType().getSimpleName());
        System.out.println("sameContent=" + Arrays.equals(typed, viaConstructor));
        System.out.println("reused=" + (reused == buffer));
        System.out.println("nextIsNull=" + (reused[3] == null));
    }
}
```

Biên dịch và chạy bằng JDK 17+ (mã cũng tương thích Java 11):

```bash
javac ToArrayOverloadsDemo.java
java ToArrayOverloadsDemo
```

Kết quả chính xác:

```text
objects=[Lan, Minh, An]
typed=[Lan, Minh, An]
constructor=[Lan, Minh, An]
lambda=[Lan, Minh, An]
objectComponent=Object
typedComponent=String
sameContent=true
reused=true
nextIsNull=true
```

Giải thích:

1. `names.toArray()` tạo `Object[]`, trong khi `names.toArray(new String[0])` tạo `String[]`. Kiểu **mảng lúc chạy** khác nhau dù các phần tử nhìn giống nhau.
2. `names.toArray(String[]::new)` chọn overload `IntFunction<T[]>`. Method reference `String[]::new` tương đương về mục đích với `size -> new String[size]`.
3. `Arrays.equals(typed, viaConstructor)` trả về `true` vì hai mảng có cùng phần tử theo đúng thứ tự. Điều đó không có nghĩa chúng là cùng một object.
4. `buffer` có độ dài 5, đủ chứa 3 phần tử, nên `toArray(buffer)` trả lại chính `buffer` (`reused == buffer`). Ô chỉ số 3 nằm ngay sau phần tử cuối và được đặt `null`.

Mọi lệnh gọi trong chương trình trên đều chọn được overload ngay lúc biên dịch, và kết quả `String[]` không cần ép kiểu từ `Object[]`.

## 4. Phân tích chính xác lỗi `toArray(null)`

Giả sử:

```java
List<String> names = List.of("Lan", "Minh");
```

Đoạn sau **cố ý không biên dịch**:

```java
String[] result = names.toArray(null);
// Lỗi biên dịch: reference to toArray is ambiguous.
// Có thể khớp toArray(T[]) hoặc toArray(IntFunction<T[]>).
```

Hai chữ ký ứng viên là:

```java
<T> T[] toArray(T[] array)
<T> T[] toArray(java.util.function.IntFunction<T[]> generator)
```

Trong Java, `null` literal tương thích với kiểu **tham chiếu**. Cả kiểu mảng `T[]` và `IntFunction<T[]>` đều là kiểu tham chiếu, nhưng không kiểu nào là kiểu con thích hợp của kiểu kia để tự quyết định overload cụ thể hơn trong trường hợp này. Do đó Java không thể chọn một lời gọi duy nhất. Kiểu biến nhận kết quả là `String[]` **không giải quyết được** sự mơ hồ giữa hai kiểu tham số.

Mặc dù `Collection.toArray()` không có đối số vẫn tồn tại, overload này **không phải ứng viên** khi lời gọi truyền một đối số `null`.

### Giải pháp nên sử dụng

```java
String[] a = names.toArray(new String[0]);  // Chọn toArray(T[])
String[] b = names.toArray(String[]::new);   // Chọn toArray(IntFunction<T[]>)
```

Cả hai cho `String[]` chứa các tên trong danh sách. Dạng thứ nhất dùng một mảng kiểu `String[]` cụ thể, dạng thứ hai dùng hàm tạo mảng. Nếu thật sự có sẵn mảng muốn tái sử dụng, có thể truyền mảng đó vào overload `T[]`.

### Ép kiểu `null` chỉ làm hết mơ hồ, không làm lời gọi hợp lệ về dữ liệu

Hai đoạn sau **biên dịch được**, vì kiểu ép tường minh đã chỉ rõ overload:

```java
names.toArray((String[]) null);  // Chọn toArray(T[])
names.toArray((java.util.function.IntFunction<String[]>) null);
// Chọn toArray(IntFunction<T[]>)
```

Tuy nhiên, **cả hai đều ném `NullPointerException` lúc chạy** vì overload đầu cần một mảng không null, còn overload thứ hai cần một hàm tạo mảng không null. Vì vậy **không nên ép kiểu `null` như một cách sửa thực tế**. Hãy cấp `new String[0]` hoặc `String[]::new`.

Đặc biệt phân biệt ba tình huống:

| Mã | Kết quả |
| --- | --- |
| `names.toArray(null)` | Lỗi **biên dịch** vì hai overload một tham số mơ hồ. |
| `names.toArray((String[]) null)` | Biên dịch được, **ném NullPointerException** lúc chạy. |
| `names.toArray((IntFunction<String[]>) null)` | Biên dịch được, **ném NullPointerException** lúc chạy. |

Trong dòng thứ ba của bảng, muốn viết ngắn `IntFunction` cần `import java.util.function.IntFunction;`; viết tên đầy đủ `java.util.function.IntFunction` thì không cần import.

## 5. Tại sao một số ví dụ cũ lại chứa `toArray(null)`?

Trước khi `Collection` bổ sung overload nhận `IntFunction<T[]>` ở Java 11, lời gọi có một đối số `null` thường chỉ khớp với overload nhận `T[]` đối với `Collection`. Khi đó, chương trình có thể biên dịch và rồi ném `NullPointerException`.

Sau khi xuất hiện overload thứ hai cùng số lượng đối số, `null` không có kiểu cụ thể trở thành mơ hồ. Vì vậy, mã nguồn dựa vào `collection.toArray(null)` có thể gặp **lỗi tương thích mã nguồn** khi biên dịch với API từ Java 11 trở lên.

Điều này **không đồng nghĩa** với việc mọi mã bytecode đã biên dịch trước Java 11 đều ngừng chạy. Cơ chế chọn overload diễn ra ở thời điểm biên dịch mã nguồn; lời gọi trong bytecode đã được liên kết theo chữ ký phương thức cụ thể. Khi nâng JDK, hãy kiểm tra **mã nguồn được biên dịch lại** và đổi sang đối số không null có kiểu rõ ràng. Đây là quy tắc tương thích vẫn có ý nghĩa thực tế cho mã Java hiện đại.

Không cần duy trì kiểu gọi `toArray(null)`: bản thân việc truyền `null` cũng không phải cách chuyển collection thành mảng hợp lệ để sử dụng.

## 6. Phân biệt với `Stream.toArray`

Không nên nhầm `Collection.toArray` với `Stream.toArray`. Cả hai đều có thể nhận constructor reference tạo mảng, chẳng hạn:

```java
String[] viaCollection = names.toArray(String[]::new);
String[] viaStream = names.stream().toArray(String[]::new);
```

Hai cách đều trả về `String[]` với phần tử từ danh sách trong ví dụ này. Tuy nhiên, chúng thuộc **hai API khác nhau**: `Collection.toArray(IntFunction)` có từ Java 11, còn overload `Stream.toArray(IntFunction)` đã có từ Java 8. Cơ chế phân bổ mảng bên trong cũng không nên coi là giống hệt nhau; đối với stream, hàm tạo mảng có thể được dùng theo cách phụ thuộc cách xử lý stream, kể cả các mảng trung gian.

Khi đã có `Collection` và chỉ muốn tạo mảng, có thể gọi `collection.toArray(String[]::new)` trực tiếp, không bắt buộc chuyển thành stream.

## 7. Những lưu ý khi áp dụng

- **Ưu tiên cách gọi thể hiện kiểu rõ ràng:** `items.toArray(Item[]::new)` hoặc `items.toArray(new Item[0])`. Cả hai là cú pháp hợp lệ, được hỗ trợ hiện nay.
- **Đừng mặc định `toArray()` trả về `String[]`:** overload không đối số trả về `Object[]`; một phép ép trực tiếp `(String[]) names.toArray()` không biến kiểu runtime của mảng thành `String[]` và có thể gây `ClassCastException`.
- **Kiểu generic của collection không phải tự động đảm bảo mọi kiểu mảng truyền vào:** vì `toArray` là phương thức generic riêng, khi truyền một kiểu mảng không chứa được các phần tử thực tế, việc sao chép có thể gây `ArrayStoreException`. Hãy dùng mảng có kiểu thành phần tương thích.
- **Không kết luận hai cách tạo mảng có tốc độ giống nhau hoặc cách nào luôn nhanh hơn:** triển khai JDK và tình huống sử dụng có thể thay đổi. Chọn cách dễ đọc, đo hiệu năng trên ứng dụng thật nếu đó là yêu cầu.
- **Không nhầm `null` làm phần tử với `null` làm đối số:** một collection cho phép phần tử null vẫn có thể được chuyển sang mảng. Lỗi mơ hồ ở đây là do lời gọi `toArray(null)` truyền `null` tại **vị trí đối số phương thức**.
- **Khi tra lỗi overload, nhìn cả kiểu tham số của các overload:** Java chọn overload theo kiểu ở thời điểm biên dịch, không đợi chạy chương trình để biết `null` nên mang nghĩa gì.

## 8. Tự kiểm tra

**Câu 1:** `List<String> words = List.of("A", "B");` thì `words.toArray(null)` có biên dịch được trên Java 17+ không?

**Đáp án:** Không. Cả overload `T[]` và overload `IntFunction<T[]>` đều có thể nhận một đối số kiểu tham chiếu, nên `null` không xác định được phương thức cụ thể.

**Câu 2:** Viết cách chuyển `words` thành `String[]` không bị mơ hồ.

**Đáp án:** `words.toArray(new String[0])` hoặc `words.toArray(String[]::new)`.

**Câu 3:** Vì sao `words.toArray((String[]) null)` không phải lời giải tốt?

**Đáp án:** Ép kiểu giúp compiler chọn overload `T[]`, nhưng tham số mảng vẫn là `null`, nên lời gọi ném `NullPointerException` lúc chạy.

**Câu 4:** Với `List<String> words`, `words.toArray()` trả về `String[]` hay `Object[]`?

**Đáp án:** `Object[]`. Muốn `String[]`, cung cấp kiểu mảng qua `T[]` hoặc `IntFunction<T[]>`.

**Ghi nhớ:** Java 11 thêm `Collection.toArray(IntFunction<T[]>)`. Vì đã có `Collection.toArray(T[])`, lời gọi `toArray(null)` trở thành **mơ hồ tại thời điểm biên dịch**. Truyền đối số có kiểu rõ ràng và không null — thường là `new T[0]` hoặc `T[]::new` — để tránh lỗi và có đúng mảng mong muốn.

*Tham khảo API chính thức:* [Java SE 25 — `Collection.toArray`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collection.html).
