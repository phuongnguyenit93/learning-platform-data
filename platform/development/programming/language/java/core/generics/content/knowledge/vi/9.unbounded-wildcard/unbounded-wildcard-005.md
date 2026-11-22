# Vì sao vẫn có thể `clear()` hoặc `remove()` trên một số `List<?>`?

## Mục tiêu

Sau bài học, bạn có thể giải thích chính xác vì sao khai báo `List<?>` ngăn nhiều thao tác **thêm hoặc thay phần tử** nhưng vẫn cho phép **gọi các phương thức xóa** như `clear()`, `remove(Object)`, `remove(int)` và `removeIf(...)`. Bạn cũng sẽ phân biệt được hai câu hỏi riêng biệt:

1. **Trình biên dịch cho phép gọi phương thức không?** — phụ thuộc vào kiểu tĩnh `List<?>` và chữ ký phương thức.
2. **Đối tượng danh sách thực tế có hỗ trợ thay đổi không?** — phụ thuộc vào implementation, trạng thái và hợp đồng của danh sách tại runtime.

Hai câu hỏi này giải thích từ khóa **“một số”** trong đề bài: cùng một khai báo `List<?>` có thể trỏ đến danh sách sửa được, danh sách kích thước cố định hoặc danh sách không cho thay đổi.

## 1. `List<?>` nghĩa là gì?

`List<?>` là một `List` có **kiểu phần tử cụ thể chưa biết** (unbounded wildcard). Chẳng hạn, cùng một tham số phương thức kiểu `List<?>` có thể nhận `List<String>`, `List<Integer>` hoặc `List<Customer>`. Trình biên dịch không được giả định kiểu phần tử ấy là `String`, `Integer` hay `Object`.

```java
static void inspect(List<?> values) {
    Object element = values.get(0); // hợp lệ nếu danh sách có phần tử
    System.out.println(element);

    // values.add("new");   // lỗi biên dịch
    // values.add(123);     // lỗi biên dịch
    // values.set(0, "new"); // lỗi biên dịch
}
```

Đây là **đoạn phương thức minh họa**, không phải tệp Java độc lập. Với `get(0)`, một phần tử thuộc kiểu chưa biết vẫn có thể được nhìn qua kiểu `Object` vì mọi kiểu tham chiếu Java đều là subtype của `Object`. Ngược lại, để thêm một `String` vào `List<?>`, compiler cần chứng minh `String` tương thích với **kiểu phần tử thực chưa biết**. Nó không thể chứng minh điều đó nếu đối tượng thực tế có thể là `List<Integer>`.

**Không nên hiểu `List<?>` đồng nghĩa với danh sách chỉ đọc (read-only).** Wildcard mô tả giới hạn thông tin kiểu ở compile time; nó không tự biến đối tượng thành immutable.

## 2. Cơ chế: thao tác xóa không cần biết `E` để đưa một giá trị mới vào danh sách

Xem các chữ ký chính của API `List<E>` và `Collection<E>`. Đoạn dưới mô tả **hình dạng chữ ký để học**, không phải bản sao đầy đủ khai báo interface JDK:

```java
// Những phương thức liên quan đến E:
boolean add(E element);
E set(int index, E element);
E get(int index);

// Những phương thức xóa:
void clear();
boolean remove(Object value);
E remove(int index);
boolean removeIf(java.util.function.Predicate<? super E> filter);
```

Các phương thức có thể được khai báo trực tiếp trong `List` hoặc được `List` kế thừa từ `Collection`. Khi biến có kiểu `List<?>`, compiler coi `E` là một **kiểu bắt wildcard chưa biết** (capture type). Điều quan trọng là phương thức sẽ **nhận** hay **trả về** một giá trị kiểu `E`:

- `add(E)` và `set(int, E)`: đưa một phần tử mới vào vị trí có kiểu `E`. Không thể tự ý truyền một đối tượng non-null đã biết như `String` hoặc `Integer` vào `List<?>`.
- `clear()`: **không nhận** phần tử mới. Xóa hết phần tử hiện có không tạo nguy cơ đưa sai kiểu vào danh sách.
- `remove(Object)`: nhận đối số kiểu `Object` để tìm/xóa theo so sánh bằng nhau, **không yêu cầu** tham số thuộc đúng kiểu `E`.
- `remove(int)`: chỉ nhận **chỉ số `int`**. Giá trị bị loại bỏ có kiểu `E` chưa biết, nhưng có thể nhận kết quả đó dưới kiểu `Object`.
- `removeIf(Predicate<? super E>)`: predicate chỉ **kiểm tra** từng phần tử rồi quyết định xóa; không cần chèn phần tử kiểu `E` mới.

Vì thế, tất cả lời gọi xóa trên đều **có thể biên dịch** qua tham chiếu `List<?>`. Cụm từ “có thể biên dịch” không có nghĩa chúng luôn chạy thành công.

### Tại sao `remove(Object)` dùng `Object`?

Chữ ký nhận `Object` cho phép tìm và thử xóa một đối tượng dựa trên `equals`, ngay cả khi kiểu của đối tượng truyền vào không trùng kiểu phần tử của danh sách. Ví dụ, gọi `listOfStrings.remove(123)` **hợp lệ khi biên dịch**; trên một `ArrayList<String>` thông thường, lệnh trả về `false` nếu không có phần tử tương ứng. Một implementation chuyên biệt vẫn có thể áp dụng các ràng buộc hợp đồng riêng; đừng suy ra mọi danh sách phải phản hồi giống nhau cho mọi đối số.

Trong khi đó, `add` nhận `E` vì mục đích của nó là **lưu** đối tượng vào danh sách. Nếu cho phép thêm tùy tiện qua `List<?>` thì lời hứa kiểu của một `List<Integer>` có thể bị phá vỡ.

### Vì sao `remove(int)` hợp lệ dù trả về `E`?

Kiểu trả về có thể là kiểu capture chưa biết mà compiler vẫn gán an toàn cho `Object`:

```java
static Object takeFirst(List<?> list) {
    return list.remove(0); // hợp lệ, danh sách phải có ít nhất một phần tử
}
```

Phương thức không cần tạo hoặc chèn một đối tượng kiểu `E`. Tuy nhiên, nếu danh sách rỗng, `remove(0)` ném `IndexOutOfBoundsException`; nếu implementation không hỗ trợ xóa, nó có thể ném `UnsupportedOperationException`.

## 3. Ví dụ Java 17+ chạy độc lập

Tạo tệp **`WildcardRemovalDemo.java`** với nội dung đầy đủ:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class WildcardRemovalDemo {

    static void removeAndClear(List<?> elements) {
        Object first = elements.remove(0);
        System.out.println("Removed by index: " + first);

        boolean removedByValue = elements.remove("cam");
        System.out.println("Removed by value: " + removedByValue);

        elements.clear();
        System.out.println("After clear: " + elements);
    }

    public static void main(String[] args) {
        List<String> fruits =
                new ArrayList<>(List.of("tao", "cam", "le"));

        List<?> view = fruits;
        System.out.println("First: " + view.get(0));
        removeAndClear(view);
        System.out.println("Original: " + fruits);

        List<?> numbers = new ArrayList<>(List.of(1, 2, 3, 4));
        boolean changed = numbers.removeIf(
                e -> e instanceof Integer i && i % 2 == 0);
        System.out.println("Remove evens: " + changed + " -> " + numbers);

        List<?> fixedSize = Arrays.asList("a", "b");
        try {
            fixedSize.clear();
        } catch (UnsupportedOperationException e) {
            System.out.println("Arrays.asList: clear unsupported");
        }

        List<?> immutable = List.of("a", "b");
        try {
            immutable.remove(0);
        } catch (UnsupportedOperationException e) {
            System.out.println("List.of: remove unsupported");
        }
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên từ thư mục chứa tệp:

```bash
javac WildcardRemovalDemo.java
java WildcardRemovalDemo
```

Stdout:

```text
First: tao
Removed by index: tao
Removed by value: true
After clear: []
Original: []
Remove evens: true -> [1, 3]
Arrays.asList: clear unsupported
List.of: remove unsupported
```

Giải thích trình tự:

1. `fruits` có kiểu `List<String>`, nhưng `view` có kiểu `List<?>`; **cả hai trỏ tới cùng một `ArrayList`**. `view.get(0)` đọc được phần tử đầu.
2. `elements.remove(0)` xóa `"tao"` và trả về phần tử dưới kiểu `Object`. `elements.remove("cam")` xóa chuỗi `"cam"` vì nó tồn tại, nên trả về `true`.
3. `elements.clear()` xóa nốt `"le"`. In lại `fruits` thấy `[]`, chứng minh wildcard không tạo bản sao và không đóng băng đối tượng.
4. `removeIf` duyệt các giá trị và xóa hai số chẵn khỏi `ArrayList`. Predicate ở đây kiểm tra kiểu bằng `instanceof` rồi xét phần dư; cú pháp pattern matching này hợp lệ từ Java 16.
5. Hai lời gọi cuối đều **qua `List<?>` và hợp lệ khi biên dịch**, nhưng thất bại tại runtime vì danh sách nền không hỗ trợ xóa.

Chương trình cố ý dùng `new ArrayList<>(List.of(...))` cho phần cần xóa: `List.of(...)` tự nó không hỗ trợ các thao tác thay đổi. Hàm `removeAndClear` giả định danh sách đầu vào **không rỗng và sửa được**; không nên gọi nó với bất kỳ `List<?>` nào khi chưa biết hợp đồng của đối tượng.

## 4. “Một số” danh sách: khác nhau ở mutability, không ở wildcard

| Cách tạo danh sách | Có thể gọi `clear/remove` từ `List<?>`? | Khi danh sách có phần tử, có hỗ trợ xóa thực tế? |
| --- | --- | --- |
| `new ArrayList<>(...)` | Có | Có; danh sách thay đổi kích thước được |
| `new LinkedList<>(...)` | Có | Có; danh sách thay đổi kích thước được |
| `Arrays.asList("a", "b")` | Có | Không; danh sách kích thước cố định, thường cho phép `set` nhưng không cho thêm/xóa |
| `List.of("a", "b")` | Có | Không; danh sách không thể thay đổi |
| `List.copyOf(source)` | Có | Không; tạo danh sách không thể thay đổi |
| `Collections.unmodifiableList(source)` | Có | Không qua wrapper; thao tác thay đổi bị từ chối |
| `new CopyOnWriteArrayList<>(...)` | Có | Các phương thức `remove/clear` trực tiếp được hỗ trợ; `Iterator.remove()` không được hỗ trợ |

Bảng phân biệt **lời gọi hợp lệ theo kiểu tĩnh** với **hành vi runtime của các implementation tiêu biểu**. Trong JDK, nhiều thao tác sửa đổi collection được coi là *optional operations*; khi không được hỗ trợ, implementation có thể ném `UnsupportedOperationException`. Điều này đúng cả với biến `List<String>` hay `List<Integer>`, không phải do riêng dấu `?`.

Đặc biệt, **kích thước cố định** không có nghĩa là bất biến hoàn toàn: danh sách do `Arrays.asList(...)` tạo cho phép thay giá trị tại chỉ số hiện có bằng `set` khi gọi qua tham chiếu có kiểu phần tử thích hợp, nhưng không cho đổi số phần tử. Ngược lại, `List.of(...)` không cho thay giá trị lẫn thay kích thước.

Với `Collections.unmodifiableList(source)`, wrapper không cho sửa qua nó; nếu mã khác còn giữ `source` và sửa được `source`, nội dung nhìn qua wrapper có thể thay đổi. Vì vậy “unmodifiable view” cũng khác “immutable snapshot”.

## 5. Hai overload `remove`: xóa theo chỉ số và theo giá trị

Java có cả `remove(int index)` và `remove(Object value)`. Cả hai gọi được trên `List<?>`, nhưng chúng chọn mục tiêu khác nhau.

```java
List<?> values = new ArrayList<>(List.of(10, 20, 30));
values.remove(1);                 // xóa chỉ số 1: xóa 20
values.remove(Integer.valueOf(30)); // xóa giá trị 30
System.out.println(values);       // [10]
```

Đây là **đoạn minh họa**, có thể đặt bên trong phương thức của một lớp Java đã import `java.util.ArrayList` và `java.util.List`.

- Đối số kiểu nguyên thủy `int` như `1` chọn `remove(int)`.
- Đối số `Integer.valueOf(30)` chọn `remove(Object)` theo quy tắc chọn overload, nên tìm phần tử bằng giá trị.
- Nếu bạn muốn xóa số nguyên theo giá trị mà không gây nhầm với chỉ số, dùng `Integer.valueOf(value)` hoặc ép đối số sang `Object`.
- `remove(int)` trả về phần tử bị xóa, và có thể ném `IndexOutOfBoundsException` nếu chỉ số không hợp lệ. `remove(Object)` trả về `boolean` cho biết việc xóa theo giá trị có xảy ra hay không trên các danh sách hỗ trợ phép xóa.

Nhầm overload có thể dẫn tới xóa nhầm phần tử hoặc lỗi chỉ số ngay cả khi wildcard và implementation hoàn toàn cho phép xóa.

## 6. Xóa bằng iterator và các phương thức collection khác

Wildcard cũng không tự cấm xóa qua iterator, vì `Iterator.remove()` không yêu cầu cung cấp phần tử kiểu `E`:

```java
static void removeFirstWithIterator(List<?> values) {
    var iterator = values.iterator();
    if (iterator.hasNext()) {
        iterator.next();
        iterator.remove();
    }
}
```

Đây là **đoạn phương thức minh họa**. Với iterator của `ArrayList`, lời gọi `remove()` sau `next()` xóa phần tử vừa duyệt. Nhưng `Iterator.remove()` cũng là thao tác tùy chọn: iterator của `CopyOnWriteArrayList` không hỗ trợ nó, dù `CopyOnWriteArrayList.remove(Object)` gọi trực tiếp vẫn có thể hoạt động. Gọi `remove()` khi chưa có `next()` thích hợp cũng có thể ném `IllegalStateException`.

Các phương thức kế thừa từ `Collection` như `removeIf(Predicate<? super E>)`, `removeAll(Collection<?>)` và `retainAll(Collection<?>)` cũng có thể được gọi qua `List<?>`. Chúng chọn hoặc giữ lại phần tử **đang có**, chứ không cần chèn một phần tử tùy tiện vào kiểu `E` chưa biết. Chúng vẫn có thể không được implementation hỗ trợ.

Trong các phép duyệt/xóa, tránh sửa `ArrayList` trực tiếp bằng `list.remove(...)` bên trong vòng lặp foreach đang sử dụng iterator của chính nó; điều đó có thể gây `ConcurrentModificationException`. Nếu cần lọc để xóa, ưu tiên `removeIf` hoặc `Iterator.remove` đúng hợp đồng của implementation.

## 7. Trường hợp đặc biệt của `null`

Dù `add("abc")` không biên dịch khi receiver là `List<?>`, **`list.add(null)` có thể biên dịch**: `null` chuyển được sang bất kỳ kiểu tham chiếu nào, kể cả capture type chưa biết. Tương tự, `list.set(0, null)` vượt qua kiểm tra kiểu tĩnh.

Điều đó **không bảo đảm thành công ở runtime**. Ví dụ `List.of(...)` không hỗ trợ thêm/thay phần tử, và một số collection không chấp nhận `null`. Không nên xem khả năng truyền `null` là giải pháp để ghi phần tử kiểu tùy ý vào `List<?>`.

`remove(null)` cũng biên dịch vì overload `remove(Object)` chấp nhận tham chiếu `null`. Kết quả còn tùy đối tượng nền: danh sách có cho phép phần tử null không, có hỗ trợ xóa không, và quy định kiểm tra đối số là gì.

## 8. Thiết kế API an toàn

Nếu một phương thức chỉ cần xóa một phần tử theo đối tượng hay làm rỗng danh sách, khai báo `List<?>` diễn đạt đúng rằng **logic không phụ thuộc kiểu phần tử**:

```java
static void reset(List<?> items) {
    items.clear(); // gọi được nếu runtime list hỗ trợ clear()
}
```

Nếu mã cần **thêm hoặc thay các phần tử `String` mới**, hãy khai báo tham số `List<String>` hoặc một kiểu generic phù hợp. Nếu mã cần đọc rồi giữ quan hệ kiểu của phần tử qua nhiều thao tác, có thể dùng generic method thay vì ép kiểu không an toàn:

```java
static <T> void replaceFirstWithSameValue(List<T> items) {
    if (!items.isEmpty()) {
        T first = items.get(0);
        items.set(0, first);
    }
}
```

Đây là **đoạn phương thức minh họa**. Mối liên hệ giữa `T` của kết quả `get` và đối số của `set` được compiler giữ lại; phương thức vẫn yêu cầu implementation hỗ trợ `set`.

Không nên chuyển `List<?>` thành raw `List` hoặc cast tùy tiện sang `List<Object>` chỉ để gọi `add`. Cast không làm kiểu phần tử thực thay đổi và có thể phá an toàn kiểu, dẫn tới lỗi ở vị trí sử dụng khác. Tên `List<?>` cũng không đồng nghĩa `List<Object>`: `List<?>` chấp nhận nhiều loại danh sách, còn `List<Object>` có thể nhận bất kỳ `Object` được phép thêm.

## 9. Kiểm tra nhanh

**Câu 1.** Nếu `List<?> a = new ArrayList<String>();`, `a.clear()` có biên dịch và chạy được không?

**Trả lời:** Có. `clear` không cần đối số kiểu `String`, và `ArrayList` hỗ trợ thao tác xóa.

**Câu 2.** Nếu `List<?> b = List.of("x");`, `b.remove(0)` có lỗi biên dịch không?

**Trả lời:** Không. Lời gọi hợp lệ khi biên dịch; lúc chạy nó ném `UnsupportedOperationException` vì danh sách từ `List.of` không cho thay đổi.

**Câu 3.** Vì sao `a.remove("x")` được phép nhưng `a.add("x")` bị compiler chặn?

**Trả lời:** `remove` nhận `Object` và chỉ tìm/xóa phần tử cũ; `add` nhận `E` và cần chắc chắn phần tử mới đúng với kiểu chưa biết mà wildcard biểu diễn.

**Câu 4.** Có phải `List<?>` lúc nào cũng cho phép xóa bằng iterator?

**Trả lời:** Không. Về mặt kiểu tĩnh, lời gọi `iterator.remove()` hợp lệ; về runtime, một số iterator từ chối thao tác này.

## Kết luận

**`List<?>` giới hạn việc đưa một giá trị non-null bất kỳ vào danh sách vì kiểu phần tử chưa được biết; nó không tự cấm việc xóa các phần tử đã có.** Các phương thức `clear()`, `remove(Object)` và `remove(int)` không đòi bạn cung cấp phần tử mới có kiểu `E`, nên chúng có thể vượt qua kiểm tra kiểu của compiler. Việc xóa **thực sự thực hiện được hay không** là trách nhiệm của implementation và hợp đồng runtime của danh sách, không phải dấu `?`.
