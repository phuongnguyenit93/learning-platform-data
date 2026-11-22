# addFirst, addLast và di chuyển vị trí phần tử đã tồn tại

Java 21 bổ sung `SequencedSet`, một interface biểu diễn tập hợp vừa không chứa phần tử trùng lặp, vừa có thứ tự gặp phần tử được xác định. Hai thao tác `addFirst()` và `addLast()` cho phép thêm phần tử vào đầu hoặc cuối tập hợp. Điểm quan trọng là nếu phần tử đã tồn tại, các thao tác này sẽ di chuyển phần tử đó đến vị trí được yêu cầu thay vì tạo ra một bản sao.

Trong phạm vi `JAVA_VERSION_JAVA21` (Java 21), `LinkedHashSet` là một triển khai quen thuộc của `SequencedSet`. Nó giữ thứ tự chèn và hỗ trợ điều khiển vị trí ở hai đầu. Những API này phù hợp khi cần vừa loại bỏ trùng lặp, vừa chủ động sắp xếp thứ tự xử lý, chẳng hạn danh sách bước nghiệp vụ hoặc danh sách phần tử được dùng gần đây.

## SequencedSet và thứ tự của phần tử

`SequencedSet` được giới thiệu cùng nhóm Sequenced Collections trong JEP 431. Interface này mở rộng `Set` và `SequencedCollection`, nên giữ hai đặc tính:

- Mỗi phần tử chỉ xuất hiện một lần theo quy tắc bằng nhau của `Set`.
- Tập hợp có thứ tự gặp phần tử, vì vậy có thể xác định phần tử đầu và cuối.

`LinkedHashSet` triển khai `SequencedSet` từ Java 21. Khi duyệt một `LinkedHashSet`, phần tử được trả về theo thứ tự chèn. Với các phương thức mới, chương trình có thể chủ động thay đổi thứ tự ở hai đầu mà không cần tự ghép một chuỗi thao tác xóa rồi thêm lại.

```java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.SequencedSet;

public class SequencedSetBasics {
    public static void main(String[] args) {
        SequencedSet<String> steps = new LinkedHashSet<>(
                List.of("NEW", "PAID", "PACKED"));

        System.out.println(steps); // [NEW, PAID, PACKED]
    }
}
```

Khai báo biến bằng kiểu interface `SequencedSet` giúp mã thể hiện đúng những thao tác mà chương trình cần. Đối tượng thực tế vẫn là `LinkedHashSet`, nên thứ tự được duy trì theo quy tắc của cấu trúc này.

## Thêm phần tử vào đầu bằng addFirst

`addFirst(element)` đặt phần tử ở vị trí đầu tiên của sequenced set. Nếu phần tử chưa có, nó được thêm vào đầu. Nếu phần tử đã có, nó được di chuyển từ vị trí hiện tại lên đầu; kích thước tập hợp không tăng và không tạo phần tử trùng lặp.

```java
SequencedSet<String> steps = new LinkedHashSet<>(
        List.of("NEW", "PAID", "PACKED"));

steps.addFirst("SHIPPED");
System.out.println(steps); // [SHIPPED, NEW, PAID, PACKED]

steps.addFirst("PAID");
System.out.println(steps); // [PAID, SHIPPED, NEW, PACKED]
```

Lần gọi đầu thêm `SHIPPED` vì phần tử chưa tồn tại. Lần gọi tiếp theo di chuyển `PAID` từ vị trí thứ ba lên đầu. `PAID` chỉ xuất hiện một lần.

## Thêm phần tử vào cuối bằng addLast

`addLast(element)` có quy tắc tương tự ở đầu còn lại: phần tử mới được thêm vào cuối, còn phần tử đã tồn tại được di chuyển đến cuối.

```java
SequencedSet<String> steps = new LinkedHashSet<>(
        List.of("NEW", "PAID", "PACKED"));

steps.addLast("DELIVERED");
System.out.println(steps); // [NEW, PAID, PACKED, DELIVERED]

steps.addLast("NEW");
System.out.println(steps); // [PAID, PACKED, DELIVERED, NEW]
```

Sau lần gọi thứ hai, `NEW` được chuyển từ đầu xuống cuối. Tập hợp vẫn có bốn phần tử, và thứ tự duyệt phản ánh vị trí mới.

## Phân biệt add, addFirst và addLast

Các thao tác này đều tôn trọng quy tắc không trùng lặp của `Set`, nhưng ý nghĩa về thứ tự khác nhau:

| Thao tác | Phần tử chưa tồn tại | Phần tử đã tồn tại |
| --- | --- | --- |
| `add(element)` | Thêm theo quy tắc thứ tự của triển khai | Không thêm bản sao; không yêu cầu di chuyển vị trí |
| `addFirst(element)` | Thêm vào đầu | Di chuyển phần tử lên đầu |
| `addLast(element)` | Thêm vào cuối | Di chuyển phần tử xuống cuối |

Ví dụ:

```java
SequencedSet<String> names = new LinkedHashSet<>(
        List.of("An", "Binh", "Chi"));

names.add("An");
System.out.println(names); // [An, Binh, Chi]

names.addLast("An");
System.out.println(names); // [Binh, Chi, An]
```

`add("An")` không thay đổi thứ tự vì phần tử đã tồn tại. `addLast("An")` diễn đạt rõ ý định chuyển phần tử đó xuống cuối.

Một điểm khác về chữ ký API: `Set.add(E)` trả về `boolean` để cho biết tập hợp có thay đổi do thêm phần tử hay không; `SequencedCollection.addFirst(E)` và `addLast(E)` trả về `void`. Nếu nghiệp vụ cần biết phần tử đã có trước khi gọi hay chưa, có thể kiểm tra bằng `contains()` trước thao tác. Trong môi trường đa luồng, việc kiểm tra rồi thay đổi phải được bảo vệ bằng cơ chế đồng bộ phù hợp nếu cần tính nguyên tử.

## Phần tử được xem là đã tồn tại như thế nào?

`SequencedSet` vẫn tuân theo hợp đồng của `Set`. Một phần tử được xem là đã có khi nó bằng một phần tử hiện tại theo quy tắc equality của tập hợp. Với `LinkedHashSet`, việc xác định trùng lặp dựa trên `equals()` và `hashCode()`.

Vì vậy, khi lưu các đối tượng tự định nghĩa trong `LinkedHashSet`, cần triển khai `equals()` và `hashCode()` nhất quán. Nếu hai đối tượng được xem là bằng nhau, `addFirst()` hoặc `addLast()` sẽ di chuyển phần tử đã có theo quy tắc tập hợp thay vì cho phép cả hai cùng tồn tại.

Không nên thay đổi những trường tham gia vào `equals()` hoặc `hashCode()` trong lúc đối tượng đang nằm trong hash-based set. Việc đó có thể khiến tập hợp không tìm thấy phần tử ở bucket dự kiến và làm hỏng các thao tác membership thông thường.

## Ví dụ thực tế: đưa trạng thái vừa cập nhật lên đầu

Một màn hình quản trị có thể cần hiển thị các mã đơn hàng duy nhất theo thứ tự cập nhật gần nhất. Mỗi lần một mã được cập nhật, đưa nó lên đầu:

```java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.SequencedSet;

public class RecentOrders {
    private static final int LIMIT = 5;

    private final SequencedSet<String> recentOrderIds = new LinkedHashSet<>();

    public void markUpdated(String orderId) {
        Objects.requireNonNull(orderId, "orderId");
        recentOrderIds.addFirst(orderId);

        while (recentOrderIds.size() > LIMIT) {
            recentOrderIds.removeLast();
        }
    }

    public List<String> snapshot() {
        return List.copyOf(recentOrderIds);
    }
}
```

Trong ví dụ, `addFirst()` vừa thêm mã mới, vừa đưa mã đã tồn tại về đầu. Vòng `while` loại bỏ phần tử cuối khi vượt giới hạn, nhờ đó giữ tối đa năm mã duy nhất. Phương thức `snapshot()` dùng `List.copyOf()` để trả về danh sách độc lập, không cho phép bên gọi thay đổi tập hợp nội bộ; thứ tự danh sách vẫn là mới nhất trước.

Lớp ví dụ trên chưa tự bảo đảm an toàn đa luồng. Nếu nhiều thread cùng gọi `markUpdated()` hoặc đọc dữ liệu đồng thời, cần đồng bộ hóa các thao tác hoặc dùng một cấu trúc dữ liệu được thiết kế cho yêu cầu đồng thời của ứng dụng.

## Kết hợp với reversed()

`SequencedSet` cung cấp `reversed()` để lấy view có thứ tự gặp phần tử ngược lại. Với view này, phần tử cuối của tập hợp gốc trở thành phần tử đầu của view và ngược lại.

```java
SequencedSet<String> steps = new LinkedHashSet<>(
        List.of("NEW", "PAID", "PACKED"));

SequencedSet<String> reverseView = steps.reversed();
System.out.println(reverseView); // [PACKED, PAID, NEW]

reverseView.addFirst("DELIVERED");
System.out.println(reverseView); // [DELIVERED, PACKED, PAID, NEW]
System.out.println(steps);       // [NEW, PAID, PACKED, DELIVERED]
```

`reversed()` trả về view được liên kết với tập hợp gốc, không phải bản sao độc lập. Vì vậy, thay đổi qua view được phản ánh ở tập hợp gốc và thay đổi trên tập hợp gốc cũng được nhìn thấy qua view. Do hướng nhìn đã đảo ngược, `reverseView.addFirst(x)` tương ứng với việc đưa `x` xuống cuối của `steps`.

Nếu chỉ muốn duyệt ngược mà không thay đổi dữ liệu, có thể dùng vòng lặp trên view:

```java
for (String step : steps.reversed()) {
    System.out.println(step);
}
```

Không cần tạo một `ArrayList` mới chỉ để duyệt theo thứ tự ngược. Nếu cần lưu kết quả độc lập, lúc đó mới sao chép các phần tử từ view sang một collection khác.

## Giới hạn và điểm cần lưu ý

- `addFirst()` và `addLast()` là các thao tác có thể không được hỗ trợ bởi mọi implementation hoặc mọi view. Một tập hợp không cho phép sửa đổi có thể ném `UnsupportedOperationException`.
- Với cấu trúc có thứ tự được quyết định bởi comparator, chương trình không thể tùy ý đặt phần tử ở đầu hoặc cuối mà vẫn giữ quy tắc sắp xếp; các thao tác định vị có thể không được hỗ trợ.
- `LinkedHashSet` giữ thứ tự chèn, không tự chuyển phần tử lên đầu khi chỉ gọi `contains()` hoặc `add()` với phần tử đã có.
- `addFirst()` và `addLast()` trả về `void`; không dùng giá trị trả về để suy ra phần tử vừa được thêm mới hay đã được di chuyển.
- `SequencedSet` không tự làm cho implementation trở nên thread-safe. Cần quản lý truy cập đồng thời theo yêu cầu của ứng dụng.
- `reversed()` là view có liên kết với collection gốc. Không coi nó là snapshot độc lập.

Với `LinkedHashSet`, các thao tác đầu/cuối thường có hiệu năng kỳ vọng hằng số nhờ cấu trúc hash và liên kết thứ tự. Tuy nhiên, hãy chọn cấu trúc dựa trên hợp đồng thứ tự và yêu cầu truy cập thực tế; không suy rộng đặc tính hiệu năng của một implementation cho mọi `SequencedSet`.

## Khi nào nên dùng addFirst và addLast?

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Thêm phần tử mới vào đầu hoặc cuối một tập hợp có thứ tự | `addFirst()` hoặc `addLast()` |
| Đưa phần tử đã có lên đầu theo lần cập nhật mới nhất | `addFirst()` |
| Đưa phần tử đã có xuống cuối để đánh dấu vừa xử lý | `addLast()` |
| Thêm phần tử nhưng giữ nguyên vị trí nếu đã tồn tại | `add()` |
| Duyệt theo thứ tự ngược | `reversed()` |
| Cần các phần tử trùng lặp hoặc truy cập theo chỉ số | Chọn `List` thay vì `SequencedSet` |
| Thứ tự luôn do comparator quyết định | Dùng sorted set và tuân theo thứ tự sắp xếp |

## Quy trình áp dụng trong dự án Java 21

1. **Xác định có cần cả uniqueness và encounter order hay không.** Nếu cần cả hai, `SequencedSet` có thể phù hợp; nếu cần trùng lặp hoặc vị trí theo chỉ số, hãy cân nhắc `List`.
2. **Chọn implementation phù hợp.** Dùng `LinkedHashSet` khi cần thứ tự chèn có thể điều chỉnh ở hai đầu.
3. **Chọn đúng thao tác.** Dùng `add()` để thêm theo hành vi thông thường, `addFirst()` để đưa lên đầu và `addLast()` để đưa xuống cuối.
4. **Kiểm tra equality của phần tử.** Bảo đảm `equals()` và `hashCode()` đúng hợp đồng nếu lưu đối tượng tùy chỉnh trong `LinkedHashSet`.
5. **Quản lý view đảo ngược.** Dùng `reversed()` để duyệt hoặc thao tác theo chiều ngược; tạo bản sao nếu cần snapshot độc lập.
6. **Kiểm tra khả năng sửa đổi và đồng thời.** Implementation có thể không hỗ trợ định vị ở hai đầu hoặc không thread-safe.
7. **Biên dịch theo Java 21.** `SequencedSet`, `addFirst()`, `addLast()` và `reversed()` là API được bổ sung trong Java 21; cần runtime tương thích để sử dụng.

`addFirst()` và `addLast()` làm cho thứ tự của một sequenced set trở thành thứ có thể điều khiển trực tiếp. Với `LinkedHashSet`, chúng vừa duy trì tính duy nhất của `Set`, vừa cho phép thêm mới hoặc di chuyển phần tử đã tồn tại đến đầu hay cuối. Hãy chọn thao tác theo ý nghĩa thứ tự mà nghiệp vụ cần và lưu ý rằng khả năng này phụ thuộc vào implementation cụ thể.
