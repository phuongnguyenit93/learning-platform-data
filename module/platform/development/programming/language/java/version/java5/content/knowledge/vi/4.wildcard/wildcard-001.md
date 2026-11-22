# Wildcard không giới hạn với dấu ?

## 1. Diễn đạt “có một kiểu phần tử, nhưng chưa biết kiểu nào”

Khi một phương thức chỉ cần xem kích thước hoặc duyệt các phần tử của danh sách, nó không nhất thiết phải biết danh sách chứa chuỗi, số hay một kiểu đối tượng khác. **Wildcard không giới hạn (unbounded wildcard)** dùng dấu `?` để diễn đạt điều đó:

```java
static void printAll(java.util.List<?> items) {
    for (Object item : items) {
        System.out.println(item);
    }
}
```

Đây là phương thức minh họa đặt trong một lớp. Nó nhận được các danh sách như `List<String>`, `List<Integer>` hoặc `List<Object>` mà không cần ép kiểu.

Đọc `List<?>` là **một danh sách có kiểu phần tử chưa biết**. Không đọc nó thành “danh sách mà tôi được quyền thêm mọi kiểu phần tử”. Kiểu cụ thể vẫn tồn tại trong hợp đồng của đối tượng nguồn; tham chiếu wildcard chỉ không tiết lộ kiểu ấy cho mã đang sử dụng.

Bài này trình bày kiến thức còn áp dụng trong Java hiện hành. Chương trình đầy đủ chạy bằng Java 17 trở lên, không cần thư viện ngoài.

## 2. Khai báo tham chiếu wildcard

Các câu lệnh minh họa sau cần import `java.util.List` và `java.util.ArrayList`, được đặt trong một phương thức:

```java
List<String> labels = new ArrayList<>(List.of("small", "large"));
List<Integer> levels = new ArrayList<>(List.of(1, 2));

List<?> firstView = labels;
List<?> secondView = levels;
```

`firstView` và `labels` cùng trỏ đến một danh sách. Phép gán không tạo bản sao, không chuyển đổi phần tử và không làm đối tượng nguồn đổi kiểu phần tử thành `Object`.

`secondView` độc lập với `firstView`: hai dấu `?` không hứa rằng hai danh sách có cùng kiểu phần tử. Một danh sách có thể chứa chuỗi, danh sách còn lại chứa số.

Với `List`, `List<?>` có cùng ý nghĩa giới hạn trên như `List<? extends Object>`. Dạng ngắn thường được dùng khi không cần một giới hạn cụ thể hơn.

## 3. Đọc phần tử dưới kiểu Object

```java
Object first = firstView.get(0);
// String text = firstView.get(0); // Lỗi biên dịch.
```

Vì chưa biết kiểu phần tử, kết quả của `get` được dùng dưới kiểu `Object`. Những thao tác không cần biết kiểu cụ thể vẫn dùng được:

```java
int count = firstView.size();
boolean empty = firstView.isEmpty();
boolean hasSmall = firstView.contains("small");
```

`contains` nhận đối số kiểu `Object`, nên có thể hỏi danh sách có chứa một giá trị hay không mà không cần thêm giá trị đó vào danh sách. Việc câu lệnh kiểm tra sự có mặt là hợp lệ không có nghĩa phép thêm cùng giá trị ấy cũng hợp lệ.

Nếu cần xử lý riêng một loại dữ liệu, phải có cơ sở kiểm tra kiểu:

```java
Object item = firstView.get(0);
if (item instanceof String text) {
    System.out.println(text.length());
}
```

Kiểm tra này không chứng minh mọi phần tử khác đều là chuỗi. Nó chỉ thu hẹp kiểu cho một giá trị trong nhánh tương ứng. Nếu `item` là `null`, nhánh không chạy.

Wildcard cũng không bảo đảm danh sách khác `null` hay chỉ số hợp lệ. `get(0)` vẫn có thể gây `IndexOutOfBoundsException` khi danh sách rỗng; gọi phương thức trên một tham chiếu danh sách `null` vẫn gây `NullPointerException`.

## 4. Vì sao không thêm được một giá trị bất kỳ?

```java
List<?> unknown = labels;
// unknown.add("medium"); // Lỗi biên dịch.
// unknown.add(3);        // Lỗi biên dịch.
// unknown.add(new Object()); // Lỗi biên dịch.
```

Dù ở ví dụ này nguồn là `List<String>`, hợp đồng `List<?>` không tiết lộ điều đó. Nếu cùng đoạn mã nhận `List<Integer>`, thêm chuỗi sẽ phá vỡ ràng buộc kiểu. Trình biên dịch không thể chứng minh một giá trị khác `null` phù hợp với kiểu phần tử đang bị giữ kín.

Một cách hình dung: thay dấu `?` bằng một tên bí mật, chẳng hạn `CAP`, do trình biên dịch quản lý. Ta biết danh sách chứa một kiểu `CAP`, nhưng chưa biết một `String` hoặc một `Integer` bất kỳ có phải `CAP` hay không. Đây là ý tưởng liên quan tới **bắt giữ wildcard (wildcard capture)**; không cần biết tên kiểu nội bộ mà thông báo lỗi hiển thị để hiểu lý do thao tác bị từ chối.

Ngay cả đọc rồi ghi lại bằng một biểu thức cũng không phải lúc nào được chấp nhận trực tiếp:

```java
// unknown.set(0, unknown.get(0)); // Không biên dịch trong dạng này.
```

Kết quả đọc đang được dùng dưới kiểu `Object`, còn `set` cần kiểu phần tử bị giữ kín. Nếu thuật toán cần giữ quan hệ ấy để sắp xếp lại các giá trị vốn đã có, dùng một phương thức generic bắt giữ kiểu hoặc một tiện ích thư viện phù hợp; không ép danh sách sang `List<Object>` để vượt qua kiểm tra.

## 5. null là ngoại lệ về kiểm tra kiểu, không phải quyền thêm tùy ý

Đối với `List<?>`, câu lệnh này hợp lệ về kiểu:

```java
unknown.add(null);
```

`null` có thể phù hợp với một kiểu tham chiếu chưa biết. Tuy nhiên, việc thao tác có thành công khi chạy còn phụ thuộc đối tượng danh sách:

- `ArrayList` cho phép phần tử `null`, nếu đối tượng đang có quyền thay đổi.
- Danh sách tạo bằng `List.of` không cho thay đổi và không chấp nhận phần tử `null` khi tạo.
- Một implementation khác có thể có các ràng buộc riêng theo hợp đồng của nó.

Vì vậy, không nói “wildcard không cho thêm bất kỳ thứ gì” một cách tuyệt đối; câu chính xác hơn là không thể thêm tùy ý một giá trị khác `null` chỉ dựa vào `List<?>`. Đồng thời, cũng không dùng `null` như cách lách để đưa một đối tượng sai kiểu vào danh sách.

Trong thiết kế API thực tế, `null` phải có ý nghĩa rõ ràng hoặc bị từ chối theo hợp đồng. Khả năng biên dịch không chứng minh việc thêm `null` là có ích.

## 6. List<?> không bảo đảm chỉ đọc hoặc bất biến

Wildcard hạn chế những thao tác cần cung cấp một phần tử mới có kiểu chưa biết. Nó không tự chặn mọi thay đổi.

| Thao tác qua `List<?>` | Hợp lệ về kiểu? | Điều kiện khi chạy |
| --- | --- | --- |
| `get(i)` | Có, đọc như `Object` | Chỉ số hợp lệ |
| `size()`, `isEmpty()` | Có | Danh sách khác `null` |
| `contains(value)` | Có | Phụ thuộc hợp đồng implementation khi truy vấn giá trị không được hỗ trợ |
| `add("x")` | Không | Bị từ chối khi biên dịch |
| `add(null)` | Có | Danh sách cho thêm và chấp nhận `null` |
| `remove(0)` | Có | Danh sách hỗ trợ xóa và chỉ số hợp lệ |
| `clear()` | Có | Danh sách hỗ trợ thay đổi tương ứng |
| `set(0, null)` | Có | Hỗ trợ thay thế, chỉ số hợp lệ và chấp nhận `null` |

Ví dụ, `firstView.clear()` có thể xóa các phần tử của danh sách cũng đang được nhìn qua biến `labels`. Phép gán sang wildcard không tạo một lớp bọc bảo vệ nguồn.

Các tiện ích có thể thao tác trên `List<?>` mà không cần biết tên kiểu phần tử. `Collections.reverse(List<?>)` đảo thứ tự các phần tử sẵn có; nó không đưa một đối tượng kiểu tùy ý mới vào danh sách. Phương thức cần danh sách hỗ trợ các thao tác thay thế phù hợp.

Nếu muốn cung cấp dữ liệu không cho thay đổi qua tham chiếu được trao ra, cần cân nhắc các API như `Collections.unmodifiableList` hoặc `List.copyOf` và hiểu quy tắc dùng chung dữ liệu của từng cách. Chỉ đổi kiểu khai báo thành `List<?>` không tạo bảo đảm đó. Một danh sách không cho sửa cấu trúc cũng không tự làm các đối tượng phần tử có thể thay đổi trở nên bất biến.

## 7. So sánh List<?> với List<Object>

```java
List<Object> mixed = new ArrayList<>();
mixed.add("text");
mixed.add(10);

List<?> view = mixed; // Hợp lệ.
// List<Object> wrong = labels; // Không hợp lệ khi labels là List<String>.
```

| Kiểu | Điều đã biết | Thêm đối tượng mới khác `null` | Nhận được `List<String>` có sẵn? |
| --- | --- | --- | --- |
| `List<Object>` | Kiểu phần tử theo hợp đồng là `Object` | Có thể thêm các loại tham chiếu khác nhau, nếu danh sách cho sửa | Không tự gán được |
| `List<?>` | Có một kiểu phần tử chưa biết | Không thể thêm tùy ý qua tham chiếu này | Có |

Vì vậy, tham số `void inspect(List<Object> items)` không phải cách nhận “mọi danh sách”. Nếu chỉ cần quan sát mà không phụ thuộc kiểu phần tử, `void inspect(List<?> items)` thường phù hợp hơn.

Một đối tượng `List<Object>` không bắt buộc đang chứa nhiều kiểu khác nhau; nó có thể tạm chỉ chứa chuỗi. Ngược lại, một tham chiếu `List<?>` không nói dữ liệu thật đồng nhất hay hỗn hợp theo lớp thực tế; nó nói mã đang sử dụng không có thông tin về đối số kiểu cụ thể.

## 8. Chương trình chạy đầy đủ

Lưu thành **`UnboundedWildcardDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class UnboundedWildcardDemo {
    static void show(String label, List<?> items) {
        System.out.println(label + "(" + items.size() + ")=" + items);
    }

    public static void main(String[] args) {
        List<String> colors = new ArrayList<>(List.of("red", "blue"));
        List<Integer> numbers = List.of(2, 4);
        show("colors", colors);
        show("numbers", numbers);

        List<?> view = colors;
        Object first = view.get(0);
        System.out.println("first=" + first);

        Collections.reverse(view);
        System.out.println("reversed=" + colors);

        view.add(null);
        System.out.println("with null=" + colors);

        List<Object> copied = new ArrayList<>(view);
        copied.add(99);
        System.out.println("copied=" + copied);
        System.out.println("source=" + colors);

        Object data = colors;
        if (data instanceof List<?> items) {
            System.out.println("matched size=" + items.size());
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all UnboundedWildcardDemo.java
java UnboundedWildcardDemo
```

Stdout chính xác:

```text
colors(2)=[red, blue]
numbers(2)=[2, 4]
first=red
reversed=[blue, red]
with null=[blue, red, null]
copied=[blue, red, null, 99]
source=[blue, red, null]
matched size=3
```

`show` nhận cả danh sách chuỗi có thể thay đổi và danh sách số không cho thay đổi, vì nó chỉ dùng các thao tác quan sát chung. `Collections.reverse(view)` làm thay đổi danh sách gốc `colors`, chứng minh wildcard không tạo bản sao hay bảo đảm bất biến.

Dòng `view.add(null)` chỉ nhằm minh họa quy tắc kiểu với một `ArrayList` cho phép `null`; không có đối tượng sai kiểu nào được thêm vào. Các phần tử khác `null` của nguồn vẫn là chuỗi.

`new ArrayList<>(view)` tạo một danh sách ngoài mới kiểu `List<Object>`. Nó sao chép các tham chiếu phần tử, nên có thể thêm `99` vào **danh sách mới** mà không thêm số ấy vào `colors`. Không có phép ép kiểu từ danh sách chuỗi sang danh sách đối tượng.

## 9. instanceof với wildcard không kiểm tra kiểu mọi phần tử

Trong chương trình, biểu thức được kiểm tra có kiểu tĩnh `Object`:

```java
Object data = List.of("one", "two");
if (data instanceof List<?> items) {
    System.out.println(items.size());
}
```

`instanceof List<?>` hợp lệ: nó kiểm tra đối tượng có phải một `List` hay không, rồi cung cấp một tham chiếu mà kiểu phần tử được giữ kín. Nó không duyệt các phần tử để chứng minh đó là chuỗi.

Với biến `data` có kiểu `Object` như trên, không thể thay bằng `instanceof List<String>` để yêu cầu JVM kiểm tra đối số kiểu `String` của danh sách. Muốn xác minh dữ liệu ngoài hệ thống có toàn phần tử chuỗi, cần kiểm tra từng phần tử và quyết định chính sách cho `null`, thay vì suy ra từ một phép kiểm tra `List<?>`.

Đây là một lý do wildcard không giới hạn hữu ích ở ranh giới dữ liệu: vẫn biểu đạt rõ rằng có một danh sách, đồng thời không hứa một kiểu phần tử mà mã chưa xác minh.

## 10. Dùng ? ở đâu và khi nào cần tham số kiểu có tên?

Wildcard là một **đối số kiểu tại nơi sử dụng**, chẳng hạn:

```java
java.util.Set<?> anySet;
java.util.Map<?, ?> anyMap;
Class<?> anyClass;
```

Với `Map<?, ?>`, kiểu khóa và kiểu giá trị là hai điều chưa biết độc lập. Không có quan hệ “cùng kiểu” chỉ vì đều được viết bằng `?`.

Không dùng `?` như tên tham số kiểu trong phần khai báo phương thức, và không khởi tạo bằng `new ArrayList<?>()`. Ta tạo một đối tượng với kiểu cụ thể hoặc kiểu được suy luận rồi nhìn nó qua tham chiếu wildcard:

```java
List<?> items = new ArrayList<String>();
```

Nếu thuật toán cần giữ quan hệ kiểu, chẳng hạn trả lại phần tử đúng kiểu mà bên gọi đang có, một tham số kiểu có tên thường phù hợp hơn. Ví dụ đối chiếu các phương thức đặt trong một lớp:

```java
static Object firstOrNull(List<?> items) {
    return items.isEmpty() ? null : items.get(0);
}

static <E> E firstTypedOrNull(List<E> items) {
    return items.isEmpty() ? null : items.get(0);
}
```

Phương thức thứ nhất chỉ hứa kết quả dưới kiểu `Object`. Phương thức thứ hai liên kết kiểu phần tử đầu vào với kiểu kết quả `E`, nên bên gọi có thể giữ thông tin kiểu. Cả hai vẫn cần hợp đồng `null` và danh sách đầu vào khác `null`.

Không cần biến mọi thao tác quan sát thành một phương thức `<E>`. Nếu không liên kết kiểu với vị trí nào khác, wildcard có thể làm ý định ngắn và rõ hơn.

## 11. Tự thực hành

1. Viết một phương thức nhận `List<?>` và trả về số phần tử khác `null`. Gọi nó với danh sách chuỗi và danh sách số.
2. Thử thêm `"green"` qua biến `view` trong chương trình đầy đủ để quan sát lỗi biên dịch. Khôi phục dòng này thành chú thích trước khi chạy.
3. Sau khi đọc phần tử đầu, gọi `view.remove(0)` trên nguồn `ArrayList` và quan sát biến `colors`. Giải thích vì sao thay đổi xuất hiện qua cả hai tham chiếu.
4. Đổi nguồn thành `List.of("red", "blue")`. Phân biệt lỗi kiểm tra kiểu với ngoại lệ khi một thao tác thay đổi được biên dịch nhưng đối tượng không hỗ trợ.
5. So sánh `firstOrNull` và `firstTypedOrNull` khi gán kết quả vào một biến `String`; xác định hợp đồng nào giữ được quan hệ kiểu.

Dấu `?` cho phép dùng một kiểu generic mà chưa cần biết đối số kiểu cụ thể. Khi dùng nó, hãy phân biệt ba điều: đọc được gì, đưa được giá trị nào vào và đối tượng thật có hỗ trợ thay đổi hay không. Ba câu hỏi ấy ngăn được cả nhầm lẫn về kiểu lẫn nhầm lẫn về quyền sửa dữ liệu.

## Tài liệu đối chiếu

- [JLS §4.5.1 — Type Arguments of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.5.1): wildcard và giới hạn của đối số kiểu.
- [JLS §5.1.10 — Capture Conversion](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.10): cơ sở của việc bắt giữ kiểu chưa biết.
- [List — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html): hợp đồng đọc, thêm, thay thế và xóa phần tử.
- [Collections.reverse — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#reverse(java.util.List)): ví dụ API dùng `List<?>` nhưng có thay đổi thứ tự phần tử.
