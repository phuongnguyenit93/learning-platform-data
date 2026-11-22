# Sao chép phòng vệ, bản chụp và vỏ bọc chỉ đọc

Một dịch vụ Java trả về danh sách sản phẩm trong giỏ hàng. Người gọi lấy danh sách, thêm một phần tử và vô tình thay đổi luôn giỏ hàng đang được dịch vụ quản lý. Ở một tình huống khác, dịch vụ trả về một danh sách “không thể sửa”, nhưng khi giỏ hàng thay đổi, danh sách mà người gọi đang giữ cũng đổi theo. Hai hiện tượng này đều liên quan đến **chia sẻ tham chiếu**, nhưng cần những giải pháp khác nhau.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta học các thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Thuộc chương **Dữ liệu và trạng thái**, bài học này tập trung vào ba kỹ thuật: **sao chép phòng vệ (defensive copying)**, **bản chụp (snapshot)** và **vỏ bọc chỉ đọc (read-only wrapper)**. Chúng giúp xác định ai có thể sửa dữ liệu, khi nào người đọc thấy thay đổi và ranh giới nào chịu trách nhiệm bảo vệ trạng thái.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao hai biến cùng tham chiếu một đối tượng có thể gây tác động ngoài ý muốn.
- Phân biệt **bản sao có thể sửa**, **bản chụp không thể sửa qua API** và **vỏ bọc chỉ đọc phản ánh nguồn dữ liệu**.
- Sử dụng `List.copyOf`, `Collections.unmodifiableList` và sao chép mảng trong đúng ngữ cảnh Java.
- Nhận diện khác biệt giữa **sao chép nông** và **sao chép sâu**, đặc biệt với phần tử có thể thay đổi.
- Thiết kế API giữ bất biến, viết kiểm thử chống rò rỉ trạng thái và hiểu giới hạn khi có nhiều luồng truy cập.

## 1. Vấn đề gốc: nhiều tham chiếu tới cùng một đối tượng

Trong Java, biến tham chiếu tới đối tượng không chứa bản sao tự động của đối tượng đó. Khi gán một tham chiếu cho biến khác, cả hai biến có thể trỏ tới **cùng một đối tượng**.

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> original = new ArrayList<>();
original.add("PEN");

List<String> alias = original;
alias.add("BOOK");

System.out.println(original); // [PEN, BOOK]
~~~

Thao tác `alias.add("BOOK")` làm thay đổi chính danh sách được đặt tên `original`. Nếu danh sách đó là dữ liệu nội bộ của một đối tượng, việc đưa tham chiếu ra ngoài có thể cho phép người gọi **bỏ qua các quy tắc cập nhật** mà đối tượng phải bảo vệ.

Ví dụ thiếu an toàn:

~~~java
public final class Cart {
    private final List<String> productIds = new ArrayList<>();

    public List<String> getProductIds() {
        return productIds; // Rò rỉ tham chiếu có thể sửa.
    }
}
~~~

Người gọi có thể viết `cart.getProductIds().clear()` hoặc `add(...)` mà không đi qua phương thức kiểm tra nghiệp vụ nào của `Cart`. Trường `private` không đủ bảo vệ trạng thái nếu phương thức công khai trả về chính tham chiếu có thể sửa.

Một lỗi tương tự có thể xuất hiện **khi nhận dữ liệu vào**:

~~~java
public final class UnsafeCart {
    private final List<String> productIds;

    public UnsafeCart(List<String> productIds) {
        this.productIds = productIds; // Giữ luôn danh sách của người gọi.
    }
}
~~~

Nếu sau khi tạo `UnsafeCart`, người gọi tiếp tục sửa danh sách đầu vào, trạng thái bên trong giỏ hàng cũng thay đổi. Vì vậy cần xem xét **cả ranh giới vào và ranh giới ra**, không chỉ getter.

## 2. Ba lựa chọn cho một danh sách

Giả sử:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> source = new ArrayList<>(List.of("PEN"));

List<String> mutableCopy = new ArrayList<>(source);
List<String> snapshot = List.copyOf(source);
List<String> readOnlyView = Collections.unmodifiableList(source);

source.add("BOOK");

System.out.println(mutableCopy);  // [PEN]
System.out.println(snapshot);     // [PEN]
System.out.println(readOnlyView); // [PEN, BOOK]
~~~

Cả ba biến đều có thể được đọc như danh sách, nhưng **quyền sửa** và **khả năng phản ánh thay đổi của nguồn** khác nhau.

| Cách tạo | Người giữ kết quả có thể gọi `add`/`remove`? | Khi `source` thay đổi, kết quả có đổi theo không? | Mục đích chính |
| --- | --- | --- | --- |
| `new ArrayList<>(source)` | **Có** | **Không**, với thay đổi cấu trúc của danh sách gốc | Tạo bản sao để người gọi tự chỉnh sửa |
| `List.copyOf(source)` | **Không** | **Không**, với cấu trúc/phần tử tham chiếu ở thời điểm sao chép | Bản chụp cấu trúc không thể sửa qua API |
| `Collections.unmodifiableList(source)` | **Không**, qua vỏ bọc | **Có**, khi danh sách nền thay đổi | Cung cấp cửa sổ chỉ đọc tới danh sách nền |
| `source` hoặc một alias trực tiếp | **Có**, nếu danh sách nền cho phép | **Có** | Chia sẻ toàn quyền đối tượng; cần hợp đồng sở hữu rõ |

Với `snapshot.add("ERASER")` hoặc `readOnlyView.clear()`, API ném `UnsupportedOperationException`. Tuy nhiên, vỏ bọc chỉ đọc **không khóa** danh sách nguồn: câu lệnh `source.add("BOOK")` vẫn thành công và thay đổi những gì `readOnlyView` nhìn thấy.

### Những thuật ngữ dễ nhầm

**Bản sao (copy)** chỉ nói rằng ta tạo một biểu diễn khác theo một mức độ nào đó. Bản sao vẫn **có thể sửa** hoặc không thể sửa.

**Bản chụp (snapshot)** nói về **thời điểm quan sát**: kết quả biểu diễn trạng thái nguồn tại lúc lấy bản chụp, trong phạm vi dữ liệu được sao chép. Bản chụp có thể được cung cấp dưới dạng có thể sửa hoặc không thể sửa.

**Vỏ bọc chỉ đọc (read-only wrapper)** nói về **quyền thao tác thông qua một giao diện**. Nó có thể tiếp tục phản ánh mọi thay đổi được thực hiện qua một tham chiếu khác tới nguồn.

**Bất biến (immutable)** là thuộc tính của dữ liệu hoặc đối tượng trong phạm vi được xét: trạng thái quan sát được của đối tượng không thể bị thay đổi sau khi tạo. Một API không có setter hoặc một trường `final` **chưa đủ** để chứng minh toàn bộ đồ thị đối tượng bất biến.

## 3. Khi nào dùng vỏ bọc chỉ đọc?

Giả sử giao diện cần hiển thị số lượng học viên hiện tại trong một khóa học. Người xem không được thêm/xóa trực tiếp, nhưng khi hệ thống ghi danh thêm học viên, giao diện được phép thấy dữ liệu mới.

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public final class EnrollmentStore {
    private final List<String> studentIds = new ArrayList<>();

    public void enroll(String id) {
        studentIds.add(id); // Ví dụ tối giản, chưa kiểm tra trùng.
    }

    public List<String> enrolledStudentsView() {
        return Collections.unmodifiableList(studentIds);
    }
}
~~~

~~~java
EnrollmentStore store = new EnrollmentStore();
store.enroll("ST-001");

List<String> view = store.enrolledStudentsView();
store.enroll("ST-002");

System.out.println(view); // [ST-001, ST-002]
// view.add("ST-003");   // UnsupportedOperationException
~~~

Đây là **khung nhìn đang sống (live view)**: người gọi không thể sửa thông qua `view`, nhưng vẫn nhìn thấy các thay đổi từ `EnrollmentStore`. Điều này có thể là chủ đích nếu API được mô tả rõ.

Tuy nhiên, live view có những rủi ro cần chấp nhận hoặc kiểm soát:

- Người gọi có thể nghĩ mình đang giữ một danh sách ổn định để tính toán, trong khi danh sách thay đổi ở lần đọc sau.
- Nếu danh sách nền bị sửa trong lúc duyệt, một số iterator có thể ném `ConcurrentModificationException`; việc không ném lỗi cũng **không chứng minh** đọc đồng thời an toàn.
- Với cấu trúc chứa phần tử có thể sửa, vỏ bọc chỉ ngăn thay danh sách, **không ngăn sửa từng phần tử**.
- Việc đổi triển khai nội bộ từ một danh sách có thứ tự sang nguồn dữ liệu khác có thể làm thay đổi ý nghĩa của live view.

Nếu người gọi cần một tập dữ liệu **ổn định trong suốt quá trình xử lý**, nên cân nhắc cung cấp bản chụp thay vì live view.

## 4. Khi nào dùng bản chụp?

Một chức năng xuất hóa đơn có thể cần danh sách dòng hàng **cố định cho lần xuất**. Nếu giỏ hàng tiếp tục thay đổi trong lúc tạo tệp PDF hoặc gửi thông điệp, việc đọc live view ở nhiều bước có thể cho ra kết quả không nhất quán.

~~~java
List<String> productIdsAtExportTime =
    List.copyOf(cartProductIds);
~~~

Sau khi tạo `productIdsAtExportTime`, thêm/xóa phần tử trong `cartProductIds` không làm thay đổi **cấu trúc danh sách** của bản chụp.

Với Java 10 trở lên, `List.copyOf(collection)` tạo ra một danh sách không thể sửa qua các phương thức cập nhật. Nếu đầu vào đã là một danh sách bất biến phù hợp, triển khai **có thể tái sử dụng đối tượng đầu vào**; không nên dựa vào việc mỗi lần gọi chắc chắn tạo tham chiếu mới. Điều được cần đến là **ngữ nghĩa không thay đổi**, không phải danh tính tham chiếu.

Các giới hạn cần lưu ý:

- `List.copyOf` **không chấp nhận phần tử `null`**; sẽ ném `NullPointerException` nếu nguồn chứa `null`.
- Kết quả **không thể sửa qua API của danh sách**, nhưng không tự sao chép sâu các đối tượng phần tử.
- Việc tạo bản chụp cần duyệt và lưu các tham chiếu tới phần tử (trừ trường hợp tối ưu tái sử dụng), nên với dữ liệu lớn hoặc tần suất gọi cao có chi phí đáng cân nhắc.
- Bản chụp thể hiện dữ liệu **tại một thời điểm lấy mẫu**; nó có thể cũ sau khi nguồn được cập nhật. Đây có thể là hành vi đúng nếu người gọi cần tính ổn định.

**Bản chụp không phải lời hứa rằng dữ liệu vẫn là mới nhất.** API cần thể hiện rõ liệu người gọi đang nhận “trạng thái hiện tại” hay “trạng thái đã chốt tại một mốc thời gian”.

## 5. Sao chép phòng vệ ở cả đầu vào và đầu ra

Xét mô hình giỏ hàng đơn giản với các dòng hàng bất biến. Ví dụ sử dụng Java 17.

~~~java
public record CartLine(String sku, int quantity) {
    public CartLine {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
    }
}
~~~

`CartLine` chứa `String` (bất biến) và `int`, vì vậy một dòng hàng không thể bị sửa sau khi tạo. Ta có thể thiết kế `ShoppingCart`:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public final class ShoppingCart {
    private final List<CartLine> lines;

    public ShoppingCart(List<CartLine> initialLines) {
        Objects.requireNonNull(initialLines, "initialLines");
        this.lines = new ArrayList<>();

        for (CartLine line : initialLines) {
            this.lines.add(Objects.requireNonNull(line, "line"));
        }
    }

    public void add(CartLine line) {
        lines.add(Objects.requireNonNull(line, "line"));
    }

    public List<CartLine> itemsSnapshot() {
        return List.copyOf(lines);
    }

    public List<CartLine> itemsReadOnlyView() {
        return Collections.unmodifiableList(lines);
    }
}
~~~

Ở constructor, `ShoppingCart` **không giữ nguyên tham chiếu** tới `initialLines`. Nó lấy những dòng hàng đầu vào vào một danh sách thuộc quyền quản lý của giỏ. Người gọi có thể `clear()` danh sách ban đầu mà không làm mất dữ liệu bên trong giỏ.

Ở đầu ra, hai phương thức diễn đạt hai hợp đồng khác nhau:

- `itemsSnapshot()`: danh sách tại lúc gọi, không nhận thêm phần tử khi giỏ hàng thay đổi sau đó.
- `itemsReadOnlyView()`: danh sách không thể sửa qua vỏ bọc, nhưng tiếp tục phản ánh các lần thêm phần tử vào giỏ.

~~~java
List<CartLine> input = new ArrayList<>();
input.add(new CartLine("PEN", 1));

ShoppingCart cart = new ShoppingCart(input);
input.clear(); // Không xóa dòng hàng trong cart.

List<CartLine> snapshot = cart.itemsSnapshot();
List<CartLine> view = cart.itemsReadOnlyView();

cart.add(new CartLine("BOOK", 2));

System.out.println(snapshot.size()); // 1
System.out.println(view.size());     // 2
~~~

Đoạn mã này làm rõ **quyền sở hữu**: giỏ hàng kiểm soát việc thêm dòng, còn người gọi chỉ nhận dữ liệu theo hợp đồng đã đặt tên. Thiết kế này giả định các lời gọi không diễn ra đồng thời; trường hợp nhiều luồng sẽ được xét ở phần sau.

### Vì sao không chỉ trả về `new ArrayList<>(lines)`?

Đó cũng là **sao chép phòng vệ hợp lệ** ở đầu ra: người gọi có thể thêm, xóa trên bản sao mà không sửa `lines`. Nhưng bản sao đó **có thể sửa**, nên nếu API muốn người dùng đối xử với kết quả như một dữ liệu đã chốt, `List.copyOf(lines)` diễn đạt ý định rõ hơn.

Trong một số trường hợp như trình chỉnh sửa bản nháp, việc trả **bản sao có thể sửa** là chính xác. Điều quan trọng là chọn quyền sửa phù hợp với hợp đồng, không áp đặt “mọi danh sách đều phải bất biến”.

## 6. Sao chép nông và sao chép sâu

Những ví dụ trên an toàn ở mức phần tử vì `CartLine` là kiểu giá trị bất biến. Nhưng nếu phần tử **có thể sửa**, việc sao chép danh sách chỉ tạo một lớp bảo vệ.

~~~java
import java.util.ArrayList;
import java.util.List;

StringBuilder mutableName = new StringBuilder("PEN");
List<StringBuilder> source = new ArrayList<>();
source.add(mutableName);

List<StringBuilder> snapshot = List.copyOf(source);
mutableName.append("-BLUE");

System.out.println(snapshot.get(0)); // PEN-BLUE
~~~

`List.copyOf(source)` đã ngăn sửa **cấu trúc danh sách**, nhưng danh sách vẫn giữ tham chiếu tới cùng một `StringBuilder`. Đây là **sao chép nông (shallow copy)**: phần tử tham chiếu chưa được nhân bản.

| Cấp độ | Được bảo vệ điều gì? | Điều vẫn có thể thay đổi? |
| --- | --- | --- |
| Vỏ bọc `unmodifiableList` | Không thể thay cấu trúc qua vỏ bọc | Danh sách gốc và phần tử có thể đổi |
| `List.copyOf` | Cấu trúc danh sách không đổi qua thời gian sau bản chụp | Trạng thái bên trong phần tử có thể đổi |
| Sao chép các phần tử có thể sửa | Có thể tách cả danh sách và trạng thái phần tử đã sao chép | Các đối tượng lồng sâu chưa sao chép vẫn có thể được chia sẻ |
| Đồ thị giá trị bất biến | Trạng thái quan sát được không thay đổi trong phạm vi mô hình | Dữ liệu ở hệ thống ngoài vẫn có thể đổi |

**Sao chép sâu (deep copy)** thường chỉ việc sao chép cả những đối tượng lồng bên trong để không còn chia sẻ phần trạng thái có thể thay đổi cần bảo vệ. Nhưng thế nào là “sâu đủ” phải được xác định theo **đồ thị đối tượng và ranh giới sở hữu**, đặc biệt khi có tài nguyên I/O, đối tượng dùng chung hoặc quan hệ vòng.

Một lựa chọn khác là **chuyển phần tử thành kiểu giá trị bất biến**; cách này thường đơn giản hơn việc liên tục tạo bản sao sâu cho cả cấu trúc.

## 7. Mảng và `record` cũng có thể làm rò rỉ dữ liệu

Mảng trong Java có thể sửa từng phần tử. Trường `private final byte[]` chỉ cố định **tham chiếu mảng**; nó không ngăn thay đổi nội dung mảng.

Ví dụ thiếu bảo vệ:

~~~java
public final class UnsafeAttachment {
    private final byte[] content;

    public UnsafeAttachment(byte[] content) {
        this.content = content;
    }

    public byte[] content() {
        return content;
    }
}
~~~

Người gọi có thể đổi byte trong mảng được truyền vào constructor **sau khi tạo đối tượng**, hoặc sửa trực tiếp mảng mà getter trả về. Hai đường này đều thay đổi trạng thái nội bộ.

Cách bảo vệ ở cả hai đầu:

~~~java
import java.util.Objects;

public final class Attachment {
    private final byte[] content;

    public Attachment(byte[] content) {
        this.content = Objects.requireNonNull(content, "content").clone();
    }

    public byte[] content() {
        return content.clone();
    }
}
~~~

~~~java
byte[] bytes = {1, 2, 3};
Attachment attachment = new Attachment(bytes);

bytes[0] = 99;
byte[] returned = attachment.content();
returned[1] = 88;

System.out.println(attachment.content()[0]); // 1
System.out.println(attachment.content()[1]); // 2
~~~

Ở đây `clone()` của mảng byte tạo mảng mới chứa các **giá trị nguyên thủy**, đủ tách trạng thái vì byte không tham chiếu đối tượng có thể sửa. Với mảng đối tượng, `clone()` chỉ sao chép các **tham chiếu phần tử**, nên vẫn là sao chép nông.

Java `record` không tự bảo đảm bất biến sâu. Ví dụ:

~~~java
public record Picture(byte[] pixels) {
}
~~~

Trường của `record` là `final`, nhưng `pixels` vẫn là mảng có thể sửa; accessor được sinh tự động sẽ trả về chính mảng đó. Nếu cần bảo vệ dữ liệu, phải kiểm soát việc sao chép ở constructor và accessor, hoặc chọn một kiểu dữ liệu thực sự bất biến.

## 8. Kiểm thử ranh giới sở hữu dữ liệu

JUnit 5 có thể kiểm tra chính những đường gây rò rỉ trạng thái. Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class ShoppingCartTest {

    @Test
    void constructorDoesNotRetainMutableInputList() {
        List<CartLine> input = new ArrayList<>();
        input.add(new CartLine("PEN", 1));

        ShoppingCart cart = new ShoppingCart(input);
        input.clear();

        assertEquals(1, cart.itemsSnapshot().size());
    }

    @Test
    void snapshotKeepsMembershipAtCaptureTime() {
        ShoppingCart cart = new ShoppingCart(
            List.of(new CartLine("PEN", 1))
        );

        List<CartLine> captured = cart.itemsSnapshot();
        cart.add(new CartLine("BOOK", 2));

        assertEquals(1, captured.size());
        assertEquals(2, cart.itemsSnapshot().size());
        assertThrows(UnsupportedOperationException.class,
            () -> captured.add(new CartLine("ERASER", 1)));
    }

    @Test
    void readOnlyViewReflectsLaterUpdatesButCannotWrite() {
        ShoppingCart cart = new ShoppingCart(
            List.of(new CartLine("PEN", 1))
        );

        List<CartLine> view = cart.itemsReadOnlyView();
        cart.add(new CartLine("BOOK", 2));

        assertEquals(2, view.size());
        assertThrows(UnsupportedOperationException.class, view::clear);
    }

    @Test
    void byteArrayIsCopiedOnEntryAndExit() {
        byte[] original = {1, 2};
        Attachment attachment = new Attachment(original);

        original[0] = 99;
        attachment.content()[1] = 88;

        assertEquals(1, attachment.content()[0]);
        assertEquals(2, attachment.content()[1]);
    }
}
~~~

Các test này kiểm tra **hợp đồng bảo vệ trạng thái**, không chỉ kiểm tra danh sách có bao nhiêu phần tử ở một thời điểm. Khi refactor getter hoặc constructor, chúng có thể bắt lỗi vô tình trả lại tham chiếu gốc.

Nếu phần tử là kiểu có trạng thái thay đổi được, hãy thêm test sửa phần tử **qua nguồn ban đầu** và **qua dữ liệu trả về**. Test phải chứng minh đúng mức độc lập mà API cam kết: tách cấu trúc, tách phần tử hay tách toàn bộ đồ thị.

## 9. “Bản chụp” trong chương trình đa luồng cần điều kiện gì?

Một nhầm lẫn phổ biến là nghĩ:

~~~java
List<CartLine> snapshot = List.copyOf(sharedList);
~~~

sẽ tự động tạo **bản chụp nguyên tử** khi luồng khác đang sửa `sharedList`. Điều này **không được bảo đảm**. Với danh sách thông thường như `ArrayList`, sao chép đồng thời với thêm/xóa có thể tạo kết quả không nhất quán hoặc lỗi; bản thân việc dùng một vỏ bọc chỉ đọc cũng không làm danh sách trở nên thread-safe.

Nếu yêu cầu là chụp nhất quán danh sách đang được nhiều luồng sử dụng, mọi thao tác đọc/ghi có liên quan phải theo **cùng một giao thức đồng bộ**. Ví dụ phác thảo:

~~~java
private final Object lock = new Object();
private final List<CartLine> lines = new ArrayList<>();

public void add(CartLine line) {
    synchronized (lock) {
        lines.add(java.util.Objects.requireNonNull(line));
    }
}

public List<CartLine> snapshot() {
    synchronized (lock) {
        return List.copyOf(lines);
    }
}
~~~

Đây là các thành viên minh họa cho một lớp quản lý giỏ hàng, **không phải đoạn mã độc lập để dán vào ngoài lớp**. Khi **mọi thao tác sửa cùng danh sách đều dùng `lock` đó**, việc sao chép và việc sửa không xen vào nhau. Nếu có thành phần khác giữ tham chiếu và sửa trực tiếp danh sách, cam kết này bị phá vỡ.

Nếu các phần tử bên trong cũng có thể thay đổi, chỉ khóa danh sách chưa đủ bảo đảm nhất quán cho **trạng thái phần tử**. Cần bảo đảm phần tử bất biến, hoặc đồng bộ và sao chép trạng thái phần tử theo cùng hợp đồng.

Tùy bài toán, có thể dùng cấu trúc dữ liệu bất biến, lưu phiên bản, `CopyOnWriteArrayList` cho trường hợp nhiều đọc ít ghi, hoặc cơ chế transaction ở tầng lưu trữ. Mỗi lựa chọn có chi phí và ngữ nghĩa khác nhau; “copy” không tự giải quyết mọi vấn đề đồng thời.

## 10. Chọn giải pháp dựa trên hợp đồng API

Không phải lúc nào cũng cần bản chụp. Trước khi chọn kỹ thuật, cần trả lời:

1. **Ai sở hữu dữ liệu?** Thành phần hiện tại hay người gọi? Có được phép chia sẻ tham chiếu không?
2. **Người nhận cần sửa dữ liệu không?** Nếu cần chỉnh bản nháp độc lập, dùng bản sao có thể sửa. Nếu chỉ đọc, chọn API chỉ đọc.
3. **Người nhận cần thấy cập nhật mới không?** Nếu có, live view có thể phù hợp; nếu cần dữ liệu chốt tại một mốc, dùng snapshot.
4. **Các phần tử có thể sửa không?** Nếu có, cần quyết định có sao chép phần tử hoặc chuyển sang kiểu bất biến không.
5. **Có truy cập đồng thời không?** Cần cơ chế bảo đảm nhất quán tại thời điểm lấy dữ liệu.
6. **Chi phí sao chép có phù hợp không?** Dữ liệu lớn, tần suất cao hoặc đồ thị đối tượng sâu có thể đòi hỏi cách tổ chức khác.
7. **API cần xử lý `null` thế nào?** `List.copyOf` không chấp nhận phần tử `null`; chuyển từ một danh sách trước đó cho phép `null` sang `List.copyOf` có thể làm thay đổi hành vi.

| Nhu cầu | Lựa chọn thường phù hợp | Điều kiện cần nhớ |
| --- | --- | --- |
| Người gọi muốn tự sửa bản nháp, không ảnh hưởng dữ liệu gốc | `new ArrayList<>(source)` | Phần tử vẫn chia sẻ nếu có thể sửa |
| Trả danh sách chỉ đọc và ổn định về cấu trúc | `List.copyOf(source)` | Sao chép nông; nguồn cần ổn định lúc sao chép |
| Trả danh sách chỉ đọc luôn phản ánh dữ liệu nền | `Collections.unmodifiableList(source)` | Chỉ chặn sửa qua wrapper; không thread-safe tự động |
| Lưu mảng byte đầu vào, không cho thay đổi sau khi tạo | `clone()` khi nhận và khi trả | Phù hợp mảng kiểu nguyên thủy; mảng object cần xem sâu hơn |
| Tạo đối tượng giá trị không đổi | Thành phần bất biến + sao chép phòng vệ cần thiết | Kiểm tra cả các cấp tham chiếu lồng nhau |
| Giữ tính nhất quán trong môi trường đồng thời | Đồng bộ, dữ liệu bất biến, versioning hoặc transaction | Snapshot phải có phạm vi và mốc thời gian rõ |

Một cách tổ chức API tốt là **đặt tên theo ngữ nghĩa**: `snapshot()` gợi ý dữ liệu chốt tại thời điểm gọi; `view()` gợi ý cửa sổ nhìn vào dữ liệu được quản lý ở nơi khác. Nhưng tên gọi chỉ giúp người đọc; hành vi thực tế phải được tài liệu hóa và kiểm thử.

## 11. Những sai lầm thường gặp

| Nhận định sai | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “Trường `final` nên đối tượng chắc chắn bất biến.” | `final` cố định tham chiếu, không cố định nội dung mảng/list | Dùng kiểu giá trị bất biến và sao chép phòng vệ |
| “`unmodifiableList` chính là snapshot.” | Wrapper vẫn nhìn thấy cập nhật từ danh sách nền | Dùng `List.copyOf` hoặc copy + wrapper khi cần bản chụp |
| “`List.copyOf` làm mọi phần tử bất biến.” | Phần tử vẫn có thể là đối tượng mutable | Sao chép phần tử hoặc dùng kiểu bất biến |
| “Getter chỉ đọc nên trả collection gốc cũng an toàn.” | Người gọi có thể sửa collection gốc qua getter | Trả snapshot hoặc read-only view theo hợp đồng |
| “Copy collection là đủ để an toàn đồng thời.” | Nguồn có thể bị sửa trong lúc copy | Đồng bộ và xác định mốc nhất quán |
| “Cứ dùng deep copy là tốt nhất.” | Tốn chi phí, khó xác định với tài nguyên/đồ thị phức tạp | Chỉ sao chép những trạng thái cần tách theo ranh giới sở hữu |
| “Bản chụp luôn là dữ liệu mới nhất.” | Nguồn có thể thay đổi ngay sau đó | Công bố thời điểm chụp, version hoặc cơ chế làm mới khi cần |

## 12. Bài tập tự kiểm tra

Xét đoạn mã:

~~~java
List<StringBuilder> source = new ArrayList<>();
source.add(new StringBuilder("A"));

List<StringBuilder> view =
    Collections.unmodifiableList(source);
List<StringBuilder> snapshot = List.copyOf(source);

source.add(new StringBuilder("B"));
source.get(0).append("1");
~~~

**Câu hỏi A.** Sau các thao tác cuối, `view.size()` và `snapshot.size()` là bao nhiêu?

**Câu hỏi B.** Giá trị `snapshot.get(0).toString()` là gì? Tại sao?

**Câu hỏi C.** Nếu ứng dụng yêu cầu “danh sách và nội dung mỗi phần tử không thay đổi sau khi chụp”, cần sửa mô hình như thế nào?

**Câu hỏi D.** Nếu một luồng khác thêm phần tử vào `source` trong lúc gọi `List.copyOf(source)`, có thể khẳng định đó là bản chụp nguyên tử không?

### Gợi ý đáp án

**A.** `view.size()` là **2** vì wrapper phản ánh thay đổi cấu trúc của danh sách gốc; `snapshot.size()` là **1** vì bản chụp chỉ chứa tham chiếu tới phần tử tại thời điểm sao chép.

**B.** Giá trị là **"A1"**. Cả `source` và `snapshot` đều chứa tham chiếu tới cùng đối tượng `StringBuilder` ban đầu; `List.copyOf` không tạo bản sao của phần tử.

**C.** Có thể chuyển nội dung sang kiểu bất biến như `String` rồi dùng `List.copyOf`. Nếu bắt buộc sử dụng đối tượng mutable, phải sao chép nội dung của từng phần tử và bảo đảm kết quả không cho người ngoài sửa lại những phần tử đã chụp.

**D.** Không. Cần một cơ chế kiểm soát truy cập đồng thời nhất quán, hoặc một nguồn dữ liệu có ngữ nghĩa snapshot rõ ràng. Việc gọi `List.copyOf` riêng lẻ không biến một `ArrayList` dùng chung thành cấu trúc thread-safe.

## Ghi nhớ

**Sao chép phòng vệ bảo vệ ranh giới sở hữu; bản chụp bảo vệ trạng thái quan sát được tại một mốc; vỏ bọc chỉ đọc giới hạn quyền sửa qua một tham chiếu.** Ba kỹ thuật này giải quyết những vấn đề khác nhau và có thể được kết hợp khi cần.

Để mã nguồn đáng tin cậy, dễ hiểu và dễ thay đổi, hãy làm rõ **ai sở hữu dữ liệu, ai có quyền sửa, phần nào cần bất biến, người đọc cần trạng thái mới nhất hay một bản chụp**, và **điều kiện đồng thời nào phải được bảo đảm**. Chọn giải pháp theo hợp đồng dữ liệu thay vì chỉ nhìn tên API Java.
