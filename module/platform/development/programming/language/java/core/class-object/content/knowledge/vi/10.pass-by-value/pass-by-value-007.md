# Trả về đối tượng mới để biểu diễn kết quả thay thế trong Java

Java **luôn truyền đối số theo giá trị (*pass by value*)**. Khi truyền một biến tham chiếu tới phương thức, Java sao chép **giá trị tham chiếu**, không chuyển quyền gán lại chính biến ở bên gọi. Vì vậy, nếu phương thức muốn đề xuất một đối tượng **thay thế** đối tượng mà biến ở bên gọi đang chỉ tới, cách rõ ràng là **trả về tham chiếu kết quả** để bên gọi chủ động nhận và gán lại biến của mình.

Mẫu trọng tâm:

~~~java
current = createReplacement(current);
~~~

Ở đây `createReplacement` tính hoặc tạo ra một đối tượng kết quả rồi `return`; phép gán `current = ...` **diễn ra ở bên gọi**. Điều này khác hẳn với việc phương thức tự viết `parameter = new Object()` bên trong thân rồi kỳ vọng biến `current` bên ngoài đổi theo.

Bài học giải thích cơ chế, khi nào nên tạo đối tượng mới, cách thiết kế phép biến đổi không sửa đầu vào, xử lý dữ liệu mutable, các bẫy về identity/`equals`, lỗi và hiệu năng. Những chương trình có tên tệp đều có thể biên dịch/chạy độc lập bằng **Java 17 trở lên**.

## 1. Vấn đề: tại sao gán lại tham số không thay đổi biến của caller?

Trước khi dùng API trả object mới, nhớ rằng **tham số là biến riêng của callee**, không phải biến local của caller. Snippet giả định `Box(int)` tồn tại:

~~~java
static void replaceLocally(Box box) {
    box = new Box(99);
}
~~~

Gọi `replaceLocally(current)` chỉ làm `box` trong callee trỏ tới object mới; `current` vẫn trỏ tới object cũ. Callee không có quyền gán vào biến local của caller thông qua tham số.

Bài này tập trung vào một giải pháp có hợp đồng rõ: callee **trả về** object kết quả, còn caller **quyết định gán, giữ riêng hoặc bỏ qua**; nếu muốn snapshot bất biến thì phải xử lý cả dữ liệu con mutable. Mẫu `current = transformed(current)` thể hiện phép gán ở đúng vị trí, không giả lập pass-by-reference bằng holder không cần thiết.

## 2. Giải pháp: trả về tham chiếu đối tượng mới

Định nghĩa phương thức **trả về `Box`**:

~~~java
static Box createReplacement(Box current) {
    return new Box(99);
}
~~~

Bên gọi nhận kết quả:

~~~java
Box current = new Box(10);
current = createReplacement(current);
~~~

Diễn biến:

~~~text
1. caller.current ----> Box #1 [value=10]
2. createReplacement(current) tạo Box #2 [value=99].
3. return đưa giá trị tham chiếu tới Box #2 về caller.
4. caller tự thực hiện phép gán:
      current = <tham chiếu tới Box #2>
5. caller.current ----> Box #2 [value=99]
~~~

Các đoạn trên chỉ minh họa trong ngữ cảnh có lớp `Box`. Giá trị tham chiếu **trả về** từ method là giá trị của một biểu thức; Java vẫn không truyền một biến caller theo tham chiếu.

Bản chất của cách làm là **giao thức rõ ràng giữa hai phía**:

1. Callee: “Tôi tạo/tính một kết quả và trả nó.”
2. Caller: “Tôi quyết định giữ kết quả, gán vào biến hiện có hoặc một biến mới.”

Caller cũng có quyền không gán:

~~~java
Box before = new Box(10);
Box after = createReplacement(before);
~~~

Lúc này `before` vẫn chỉ object cũ, còn `after` chỉ object kết quả. Nhờ đó có thể giữ lại lịch sử, so sánh trước–sau hoặc thử một thay đổi mà chưa “áp dụng” nó.

## 3. Ví dụ hoàn chỉnh: phương thức gán lại tham số và phương thức trả object

Tạo tệp **`ReferenceReplacementDemo.java`**:

~~~java
final class Label {
    private final String text;

    Label(String text) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException("text không hợp lệ");
        }
        this.text = text;
    }

    String text() {
        return text;
    }
}

public class ReferenceReplacementDemo {
    static void ineffectiveReplace(Label label) {
        label = new Label("Mới");
        System.out.println("inside=" + label.text());
    }

    static Label replacement(Label old, String newText) {
        return new Label(newText);
    }

    public static void main(String[] args) {
        Label current = new Label("Cũ");
        Label oldAlias = current;

        ineffectiveReplace(current);
        System.out.println("caller before=" + current.text());

        current = replacement(current, "Mới");
        System.out.println("caller after=" + current.text());
        System.out.println("old alias=" + oldAlias.text());
        System.out.println("same reference=" + (current == oldAlias));
    }
}
~~~

Chạy trong thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 ReferenceReplacementDemo.java
java ReferenceReplacementDemo
~~~

**Stdout chính xác:**

~~~text
inside=Mới
caller before=Cũ
caller after=Mới
old alias=Cũ
same reference=false
~~~

**Diễn giải:**

- `ineffectiveReplace` tạo `Label("Mới")` rồi gán **tham số của chính nó**, nên bên trong in `Mới`, nhưng `current` của `main` vẫn in `Cũ`.
- `replacement` trả về một `Label` mới. Lệnh `current = replacement(...)` **ở `main`** mới thực sự gán biến `current` sang object mới.
- `oldAlias` vẫn tham chiếu object cũ. Gán lại `current` **không cập nhật tự động** tất cả các biến đang giữ object cũ.
- `current == oldAlias` là `false` vì phương thức dùng `new Label(...)` để tạo một instance khác.

Ví dụ này cố ý giữ class `Label` đơn giản và bất biến: trường `text` là `final`, còn `String` là kiểu bất biến. Vì thế ta nhìn rõ tác dụng của **thay thế tham chiếu** mà không bị lẫn với việc sửa trạng thái trong object.

**Lưu ý:** tham số `old` trong `replacement` không được đọc vì ví dụ chỉ minh họa thao tác “thay bằng một giá trị khác”. Trong API thực tế, nếu kết quả hoàn toàn không phụ thuộc object cũ thì tên và chữ ký `new Label(newText)` hoặc một factory không nhận `old` có thể đơn giản hơn. Các ví dụ tiếp theo sẽ dùng dữ liệu cũ để tính object mới.

## 4. Bản sao tham chiếu, object mới và giá trị trả về

Hãy phân biệt chính xác bốn biểu thức:

| Biểu thức | Có tạo object mới không? | Có gán lại biến caller không? |
| --- | --- | --- |
| `param = other;` trong method | Không nhất thiết | Không |
| `param = new Box(5);` trong method | Có, một `Box` mới | Không |
| `return new Box(5);` trong method | Có, một `Box` mới | Chưa; chỉ trả kết quả |
| `current = makeBox();` trong caller | Tùy `makeBox` | Có; phép gán nằm ở caller |

**Điểm rất quan trọng:** `return` **không tự gán** kết quả vào một biến có tên giống tham số ở caller. Nó trả về một giá trị tham chiếu; caller phải **tự sử dụng** kết quả đó.

Ví dụ:

~~~java
current = transform(current); // Giữ và áp dụng kết quả.
Box candidate = transform(current); // Giữ kết quả bên cạnh.
transform(current); // Bỏ kết quả nếu không có mục đích sử dụng.
~~~

Đoạn trên là minh họa, giả định `transform` trả về `Box`. Với phương thức được thiết kế thuần, không sửa object đầu vào, lời gọi cuối vẫn thực thi việc tính toán/tạo kết quả, nhưng kết quả bị bỏ đi; trạng thái của `current` không đổi.

Không nên kết luận “mọi phương thức có `return Box` đều tạo object mới”: nó có thể trả `this`, trả một object cache, trả tham số cũ hoặc một instance sẵn có. Nếu hợp đồng yêu cầu **identity mới**, triển khai phải thực sự bảo đảm điều đó; nếu chỉ yêu cầu **giá trị kết quả**, có thể cho phép tái sử dụng instance bất biến.

## 5. Phép biến đổi không làm thay đổi đầu vào: record bất biến

Một thiết kế phổ biến là tạo **đối tượng giá trị (value object)** bất biến. Thay vì cập nhật số tiền bên trong object đang tồn tại, ta trả về **một phiên bản biểu diễn số dư mới**.

Trong Java 17, `record` là lựa chọn thuận tiện cho dữ liệu nhỏ. Tạo tệp **`ImmutableBalanceDemo.java`**:

~~~java
record Balance(String accountId, long cents) {
    Balance {
        if (accountId == null || accountId.isBlank()) {
            throw new IllegalArgumentException("Mã tài khoản không hợp lệ");
        }
        if (cents < 0) {
            throw new IllegalArgumentException("Số dư không được âm");
        }
    }

    Balance deposit(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số nạp phải dương");
        }
        return new Balance(accountId, Math.addExact(cents, amount));
    }

    Balance withdraw(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số rút phải dương");
        }
        if (amount > cents) {
            throw new IllegalArgumentException("Không đủ số dư");
        }
        return new Balance(accountId, cents - amount);
    }
}

public class ImmutableBalanceDemo {
    public static void main(String[] args) {
        Balance original = new Balance("A-01", 1000);
        Balance alias = original;

        Balance next = original.deposit(250);
        System.out.println("old=" + original);
        System.out.println("next=" + next);
        System.out.println("same instance=" + (original == next));
        System.out.println("alias still old=" + (alias == original));

        Balance current = original;
        current = current.deposit(500);
        System.out.println("current=" + current);
        System.out.println("old after assign=" + original);

        try {
            current = current.withdraw(2000);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }
        System.out.println("after failed=" + current);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ImmutableBalanceDemo.java
java ImmutableBalanceDemo
~~~

**Stdout chính xác:**

~~~text
old=Balance[accountId=A-01, cents=1000]
next=Balance[accountId=A-01, cents=1250]
same instance=false
alias still old=true
current=Balance[accountId=A-01, cents=1500]
old after assign=Balance[accountId=A-01, cents=1000]
rejected=Không đủ số dư
after failed=Balance[accountId=A-01, cents=1500]
~~~

### Điều gì được thay đổi?

- `original.deposit(250)` **không sửa `original`**. Nó dùng dữ liệu `accountId`, `cents` từ record cũ để tạo `new Balance(...)`, rồi trả kết quả.
- `next` nhận object mới có `cents = 1250`. `original` vẫn có 1000.
- `current = current.deposit(500)` thực hiện phép **gán lại biến `current` ở caller** sang object mới có 1500. Nó không sửa hoặc “xóa” `original`.
- `alias` vẫn giữ tham chiếu cũ, nên `alias == original` là `true`.
- Với `withdraw(2000)`, hàm ném ngoại lệ **trước khi trả một giá trị**. Vì vế phải không hoàn thành bình thường, phép gán `current = ...` không xảy ra, nên `current` vẫn tham chiếu số dư 1500.

### Hợp đồng của phương thức trả bản thay thế

`deposit(amount)` có hợp đồng:

~~~text
Đầu vào:
    amount > 0
    cents + amount nằm trong miền long

Kết quả thành công:
    result.accountId == old.accountId theo String.equals
    result.cents == old.cents + amount
    object nhận lời gọi không bị sửa

Trường hợp lỗi:
    amount <= 0 -> IllegalArgumentException
    tràn số long -> ArithmeticException
~~~

Đây là **đặc tả minh họa**, không phải cú pháp Java. Trong chương trình, `Math.addExact` ném `ArithmeticException` nếu phép cộng `long` tràn. Constructor mới tiếp tục kiểm tra các invariant.

Record tự có `toString()`, `equals()` và `hashCode()` phù hợp với các component; chính vì thế stdout hiển thị dạng `Balance[accountId=..., cents=...]`. Với record chứa một `String` và một `long`, ví dụ tránh được chuyện phần tử con mutable.

**Đây là mô hình giá trị số dư dùng để học, không phải giao dịch ngân hàng thật.** Trong hệ thống có lưu trữ/đồng thời, trả bản giá trị mới không tự trừ tiền khỏi nguồn dữ liệu bền vững hoặc giải quyết đồng bộ nhiều người cập nhật.

## 6. Không phải cứ trả object là sửa trạng thái cũ

Phân biệt hai phong cách API:

~~~java
// Ví dụ A: mutable object
account.depositInPlace(100);

// Ví dụ B: immutable-style transformation
account = account.withDeposit(100);
~~~

Đây là **các lời gọi minh họa**, không có lớp `account` tương ứng được định nghĩa ở đoạn này. Phong cách A thường cố ý **sửa chính object** mà `account` trỏ tới; phong cách B thường **trả đối tượng kết quả** và yêu cầu caller gán lại nếu muốn áp dụng.

Bảng so sánh:

| Tiêu chí | Sửa tại chỗ (*in-place*) | Trả object thay thế |
| --- | --- | --- |
| Object cũ | Có thể bị cập nhật | Nên giữ nguyên nếu thiết kế không đột biến |
| Biến caller | Không cần gán lại để quan sát sửa field | Cần gán lại để biến đó trỏ kết quả |
| Các alias đến object cũ | Thường nhìn thấy sửa đổi | Tiếp tục nhìn thấy giá trị cũ |
| Kiểm thử | Kiểm tra trạng thái trước/sau | So sánh kết quả mới và tính bất biến đầu vào |
| Lịch sử trạng thái | Phải chụp snapshot riêng | Có thể giữ phiên bản cũ |
| Quản lý identity | Giữ cùng object | Có thể sinh identity mới |
| Chi phí | Có thể giảm cấp phát | Có thể tạo object/cấu trúc bổ sung |

Không có lựa chọn nào luôn tốt hơn. Với entity có identity và tài nguyên ngoại vi, **sửa tại chỗ có chủ đích** đôi khi phù hợp. Với cấu hình, tọa độ, khoảng giá trị hoặc dữ liệu cần dự đoán kết quả, **trả bản thay thế** thường dễ suy luận và kiểm thử.

Đặc biệt, một API được thiết kế trả object mới **không nên âm thầm sửa object đầu vào rồi mới trả** nếu đã hứa không có tác dụng phụ.

## 7. Ví dụ tọa độ: phép biến đổi và chuỗi lời gọi

Một đối tượng tọa độ đơn giản có thể có phương thức `move(dx,dy)` trả về điểm mới, thay vì cập nhật tọa độ của điểm ban đầu.

Tạo tệp **`ImmutablePointDemo.java`**:

~~~java
record Point(int x, int y) {
    Point move(int dx, int dy) {
        return new Point(
                Math.addExact(x, dx),
                Math.addExact(y, dy));
    }
}

public class ImmutablePointDemo {
    public static void main(String[] args) {
        Point start = new Point(1, 2);
        Point moved = start.move(3, -1);
        Point finalPoint = moved.move(0, 5);

        System.out.println("start=" + start);
        System.out.println("moved=" + moved);
        System.out.println("final=" + finalPoint);
        System.out.println("equal start=" + start.equals(new Point(1, 2)));
        System.out.println("same ref=" + (start == moved));
    }
}
~~~

Chạy:

~~~bash
javac ImmutablePointDemo.java
java ImmutablePointDemo
~~~

Stdout:

~~~text
start=Point[x=1, y=2]
moved=Point[x=4, y=1]
final=Point[x=4, y=6]
equal start=true
same ref=false
~~~

`start.move(3,-1)` trả một object mới `(4,1)`, `moved.move(0,5)` trả một object mới khác `(4,6)`, còn `start` vẫn là `(1,2)`.

Có thể nối lời gọi:

~~~java
Point destination = start.move(3, -1).move(0, 5);
~~~

Vì mỗi lần gọi `move` trả về một `Point`, lời gọi tiếp theo chạy trên kết quả trước đó. Điểm mạnh là từng bước **có giá trị đầu ra rõ ràng** và không ảnh hưởng bất ngờ tới object `start`.

**Chú ý:** `start.equals(new Point(1,2))` là `true` vì hai record bằng nhau theo giá trị component; `start == moved` là `false` vì đây là hai instance tạo bằng `new` khác nhau. `equals` và `==` không thể dùng thay thế tùy tiện.

## 8. Giữ object cũ làm “phiên bản trước” thay vì mất lịch sử

Khi phương thức không sửa input, caller có thể giữ nhiều phiên bản:

~~~java
Balance v1 = new Balance("A-01", 1000);
Balance v2 = v1.deposit(300);
Balance v3 = v2.withdraw(100);
~~~

Sau ba dòng này:

~~~text
v1 --> Balance(..., cents=1000)
v2 --> Balance(..., cents=1300)
v3 --> Balance(..., cents=1200)
~~~

Đây là đoạn minh họa dùng record ở mục 5. Mỗi biến lưu một **giá trị quan sát khác nhau**. Nếu thay vào đó luôn viết `current = current.deposit(...)`, biến `current` chỉ giữ phiên bản mới nhất nhưng có thể vẫn còn các tham chiếu khác giữ phiên bản cũ.

Khả năng lưu lại phiên bản cũ hữu ích với:

- Giao diện có **undo/redo** hoặc so sánh trước–sau.
- Xử lý trạng thái kiểu reducer: `nextState = reduce(previousState, action)`.
- Quy tắc cấu hình có nhiều biến thể.
- Kiểm thử nghiệp vụ: tính kết quả từ trạng thái trước mà không cần tự hoàn tác.

Tuy nhiên, tạo object bất biến mới không tự tạo một **lịch sử bền vững**. Nếu ứng dụng muốn lưu các phiên bản qua lần khởi động lại, nó vẫn cần lưu trữ phù hợp; nếu dữ liệu con mutable và bị chia sẻ, “phiên bản” cũ có thể không độc lập như mong đợi.

## 9. Bẫy quan trọng: object mới vẫn có thể chia sẻ dữ liệu con mutable

Giả sử class chứa một trường `List<String>`. Phương thức trả object mới nhưng **sử dụng lại cùng list mutable** có thể làm hai object chia sẻ trạng thái.

Ví dụ rủi ro:

~~~java
class UnsafeCart {
    private final java.util.List<String> items;

    UnsafeCart(java.util.List<String> items) {
        this.items = items;
    }

    UnsafeCart withSameItems() {
        return new UnsafeCart(items);
    }
}
~~~

Đây là **định nghĩa lớp minh họa**, không có `main`. Mặc dù `withSameItems()` dùng `new UnsafeCart(...)`, hai instance vẫn giữ **cùng một đối tượng danh sách**. Nếu bên ngoài còn tham chiếu tới danh sách và gọi `items.add(...)`, trạng thái quan sát của cả hai instance cùng đổi.

**Tạo object wrapper mới không đồng nghĩa deep copy.** Cần kiểm tra cấu trúc con nào được chia sẻ, phần tử có mutable không, và ai được phép cập nhật chúng.

### Khi đầu vào là mảng

Một constructor nhận `int[] numbers` rồi gán `this.numbers = numbers` cũng chỉ lưu một bản sao **giá trị tham chiếu mảng**. Nếu caller sửa `numbers[0]`, object mới vẫn đọc cùng phần tử đã đổi.

Một lựa chọn là sao chép phòng vệ:

~~~java
this.numbers = java.util.Arrays.copyOf(numbers, numbers.length);
~~~

Dòng này là minh họa trong constructor có field `numbers` phù hợp. Với mảng các kiểu nguyên thủy, sao chép phần tử giúp tách dữ liệu; với mảng đối tượng mutable, bản sao mảng vẫn có thể **chia sẻ các object phần tử**.

## 10. Ví dụ hoàn chỉnh: trả giỏ hàng mới và sao chép danh sách

Ta dùng `record CartSnapshot` giữ danh sách tên sản phẩm. Mỗi phép `add` trả về snapshot mới, trong khi snapshot cũ giữ nguyên. Tạo tệp **`CartSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record CartSnapshot(List<String> items) {
    CartSnapshot {
        items = List.copyOf(items);
    }

    CartSnapshot add(String item) {
        Objects.requireNonNull(item, "item");
        List<String> updated = new ArrayList<>(items);
        updated.add(item);
        return new CartSnapshot(updated);
    }
}

public class CartSnapshotDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>(List.of("Bút"));
        CartSnapshot original = new CartSnapshot(input);
        CartSnapshot updated = original.add("Vở");

        input.add("Thước");

        System.out.println("original=" + original.items());
        System.out.println("updated=" + updated.items());
        System.out.println("input=" + input);
        System.out.println("same ref=" + (original == updated));

        try {
            original.items().add("Tẩy");
        } catch (UnsupportedOperationException ex) {
            System.out.println("cannot edit snapshot");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CartSnapshotDemo.java
java CartSnapshotDemo
~~~

**Stdout:**

~~~text
original=[Bút]
updated=[Bút, Vở]
input=[Bút, Thước]
same ref=false
cannot edit snapshot
~~~

### Vì sao phiên bản cũ không thay đổi?

- Constructor compact của record thực hiện `items = List.copyOf(items)`: snapshot giữ một **danh sách không hỗ trợ sửa qua API**, được tạo từ nội dung đầu vào theo hợp đồng `List.copyOf`.
- `add("Vở")` tạo một `ArrayList` mutable tạm chứa các phần tử cũ, thêm `"Vở"`, rồi tạo **`CartSnapshot` mới**. Constructor snapshot mới lại dùng `List.copyOf` để cố định danh sách quan sát được.
- Caller sửa `input.add("Thước")` **sau khi** tạo snapshot đầu tiên. Vì snapshot đã lấy các phần tử sang cấu trúc không chịu ảnh hưởng từ việc thêm vào `input`, `original.items()` vẫn là `[Bút]`.
- `original.items().add("Tẩy")` ném `UnsupportedOperationException`, vì danh sách trong snapshot không cho sửa qua API.
- `original == updated` là `false` vì đây là hai instance record riêng.

**Ranh giới quan trọng:** `List.copyOf` là **sao chép nông theo phần tử tham chiếu**, không tạo bản sao sâu từng object trong list. Ví dụ dùng `String` bất biến nên tính độc lập đủ rõ. Nếu danh sách chứa `MutableItem`, cả hai snapshot vẫn có thể giữ tham chiếu tới cùng `MutableItem`; muốn độc lập sâu phải thiết kế sao chép hoặc bất biến ở cấp phần tử.

`List.copyOf` không chấp nhận **phần tử null**. Trong ví dụ, `new CartSnapshot(null)` cũng không hợp lệ; việc kiểm tra `null` và thông báo lỗi chi tiết hơn có thể được bổ sung theo hợp đồng API thực tế.

## 11. `withX(...)`: thiết kế API trả đối tượng thay thế

Một quy ước đặt tên thường thấy ở kiểu dữ liệu bất biến là `withName`, `withStatus`, `withEmail`, ...: trả về một phiên bản mang giá trị mới ở **một phần trạng thái**, giữ lại các phần khác.

Ví dụ minh họa:

~~~java
record UserProfile(String name, String city) {
    UserProfile withCity(String newCity) {
        return new UserProfile(name, newCity);
    }
}
~~~

Caller:

~~~java
UserProfile oldProfile = new UserProfile("An", "Huế");
UserProfile newProfile = oldProfile.withCity("Đà Nẵng");
~~~

Đoạn này là minh họa hợp lệ trong dự án có khai báo record `UserProfile`. Hai biến có thể cùng tồn tại và chứa hai giá trị thành phố khác nhau. Nhưng tên `withCity` chỉ là **quy ước thiết kế**, không phải cú pháp đặc biệt Java tự thực thi.

Có thể tránh tạo thêm object khi giá trị không thay đổi:

~~~java
UserProfile withCity(String newCity) {
    if (java.util.Objects.equals(city, newCity)) {
        return this;
    }
    return new UserProfile(name, newCity);
}
~~~

Đây là **phiên bản triển khai thay thế**, không thể cùng tồn tại với `withCity(String)` phía trên trong cùng record. Khi trả `this`, nó **không tạo instance mới**; vì vậy cần phân biệt hợp đồng “trả **giá trị phiên bản kết quả**” với hợp đồng “**luôn** tạo identity mới”. Với kiểu dữ liệu bất biến, cho phép trả `this` khi không thay đổi thường hợp lý nhưng không phải quy tắc bắt buộc.

Nếu record có bất biến miền nghiệp vụ, nên kiểm tra tại constructor để mọi đường `withX` cùng duy trì chúng.

## 12. Kết quả trả về không phải “đầu ra truyền bằng tham chiếu”

Xem hai phương án:

~~~java
// A: cập nhật bên trong một object dùng chung
static void appendBang(StringBuilder target) {
    target.append("!");
}

// B: trả về một giá trị mới
static String appendBang(String source) {
    return source + "!";
}
~~~

Đây là hai phương thức minh họa có cùng tên nhưng khác kiểu tham số, nên có thể nạp chồng nếu đặt trong một lớp phù hợp.

Ở A, Java vẫn **truyền giá trị tham chiếu** tới `StringBuilder`. Phương thức sửa **chính object được tham chiếu** qua `append`, do đó caller quan sát được thay đổi mà không gán lại biến.

Ở B, `String` là bất biến; phương thức trả một chuỗi kết quả. Caller muốn dùng giá trị mới phải viết:

~~~java
String message = "Java";
message = appendBang(message);
~~~

Không phương án nào dùng cơ chế “callee nhận quyền gán lại biến caller”. Sự khác biệt là **sửa object được chia sẻ** so với **trả giá trị thay thế để caller tự giữ**.

Khi đặt tên API, có thể dùng `appendInPlace` hoặc `withSuffix` nếu cần nêu rõ khác biệt hành vi, thay vì để người dùng suy đoán từ overload.

## 13. Không gán kết quả: lỗi rất thường gặp

Giả sử một method bất biến:

~~~java
Balance deposit(long amount) {
    return new Balance(accountId, Math.addExact(cents, amount));
}
~~~

Đoạn này chỉ trích ý tưởng từ record `Balance`; constructor ở mục 5 còn kiểm tra các điều kiện cần thiết.

Nếu caller viết:

~~~java
Balance current = new Balance("A-01", 1000);
current.deposit(200); // Kết quả bị bỏ đi.
System.out.println(current.cents()); // 1000
~~~

thì `current` vẫn trỏ object ban đầu; method **không cập nhật trạng thái object cũ**. Lỗi này tương tự với nhiều API bất biến như:

~~~java
String name = "  An  ";
name.trim(); // Bỏ kết quả nên name vẫn là "  An  ".
~~~

Với `String`, `trim()` trả về kết quả chuỗi chứ không sửa object `String` đang tồn tại.

Cách đúng khi muốn áp dụng:

~~~java
current = current.deposit(200);
name = name.trim();
~~~

**Dấu hiệu review:** nếu một method được thiết kế không có tác dụng phụ và **trả về object mới**, lời gọi bỏ qua kết quả thường đáng được xem xét. Tuy nhiên, không phải mọi phương thức trả object đều bắt buộc caller phải giữ kết quả; cần dựa theo hợp đồng cụ thể.

## 14. Lỗi khi tính phiên bản mới: giữ nguyên phiên bản cũ

Một ưu điểm của phương thức tạo kết quả **không sửa input** là có thể tính toán/kiểm tra trước khi công bố phiên bản mới.

Ví dụ `Balance.withdraw`:

~~~java
Balance withdraw(long amount) {
    if (amount <= 0) {
        throw new IllegalArgumentException("Số rút phải dương");
    }
    if (amount > cents) {
        throw new IllegalArgumentException("Không đủ số dư");
    }
    return new Balance(accountId, cents - amount);
}
~~~

Đây là trích đoạn phương thức của record hoàn chỉnh. Khi gọi:

~~~java
current = current.withdraw(2000);
~~~

Nếu `current.cents() == 1500`, phương thức ném exception trước khi trả result. Phép gán `current = ...` của caller **không hoàn thành**, vì phía phải thất bại; `current` vẫn giữ tham chiếu cũ.

Nhưng cần nói rõ giới hạn: đây **không phải transaction/rollback tự động của Java**. Nếu thân phương thức đã sửa input, gửi thông báo, ghi file hoặc cập nhật database **trước khi ném exception**, các tác dụng phụ ấy có thể vẫn tồn tại. Tính “thất bại không đổi giá trị cũ” chỉ đáng tin nếu implementation thực sự **không đụng trạng thái chia sẻ** hoặc có cơ chế hoàn tác thích hợp.

Không nên mô tả phương thức có `return new ...` là “pure” nếu trong quá trình tạo kết quả nó còn thực hiện I/O hoặc sửa global state.

## 15. `null` và hợp đồng của kết quả thay thế

Khi một method trả object, cần xác định rõ liệu nó có thể trả `null` hay không. Ví dụ:

~~~java
static String normalize(String raw) {
    if (raw == null) {
        return null;
    }
    return raw.strip();
}
~~~

Đây là phương thức minh họa; nó chấp nhận null và trả null theo một quy ước. Caller có thể gán:

~~~java
String name = normalize(name);
~~~

Nhưng nếu kết quả có thể null, caller phải biết trước khi gọi method khác. Một lựa chọn khác là từ chối null bằng `Objects.requireNonNull(raw)` hoặc trả `Optional<String>` trong những API mà “không có giá trị” là tình huống hợp lệ. **Không có một chính sách null duy nhất cho mọi API.**

Đối với phép thay thế một object đang giữ trạng thái bắt buộc, thường nên đảm bảo result **khác null và hợp lệ**. Nếu không, phép `current = replacement(current)` có thể khiến biến caller trở thành `null` và gây lỗi ở những bước tiếp theo.

Một cách viết rõ trong Javadoc:

~~~java
/**
 * Trả một Balance mới với số tiền được nạp.
 *
 * @param amount số tiền nạp phải dương
 * @return Balance mới, không null; object nhận lời gọi không đổi
 * @throws IllegalArgumentException nếu amount không dương
 * @throws ArithmeticException nếu phép cộng long bị tràn
 */
~~~

Đây là đoạn **Javadoc minh họa**, không phải một phương thức độc lập. Tài liệu phải phản ánh đúng implementation.

## 16. Identity, `==`, `equals` và kết quả thay thế

Một phương thức `return new Point(...)` tạo **object khác** theo ngữ nghĩa biểu thức tạo instance. Vì vậy:

~~~java
Point a = new Point(1, 2);
Point b = a.move(0, 0);

System.out.println(a == b);      // false, vì move dùng new Point.
System.out.println(a.equals(b));  // true, vì component giống nhau.
~~~

Đây là đoạn minh họa với record `Point` ở mục 7. Hai object khác tham chiếu nhưng bằng nhau về giá trị.

Đối với API có thể `return this` khi nội dung không đổi, không được dùng `a != b` để mặc định suy ra “có thay đổi dữ liệu”:

~~~text
a == b    : hỏi có cùng instance?
a.equals(b): hỏi có cùng giá trị theo hợp đồng của class?
~~~

Một kiểu value object tốt có thể tập trung vào **`equals` theo giá trị**. Một entity với identity riêng có thể cần quy tắc khác. Khi thiết kế phương thức `withX`, không nên dựa vào `==` để phân biệt trạng thái nghiệp vụ nếu API không cam kết identity mới ở mọi lần gọi.

### Lưu ý đối với collection và wrapper

Một số API thư viện như `List.copyOf` có thể **tái sử dụng** danh sách đã bất biến thay vì tạo object khác trong mọi trường hợp. Các wrapper hoặc giá trị được cache cũng có identity khó dự đoán. **Chỉ dùng `==` nếu bạn thực sự muốn hỏi về identity và hợp đồng cho phép phụ thuộc vào điều đó.**

Tính đúng đắn của chương trình nên dựa trên **hành vi và trạng thái được bảo đảm**, không dựa vào giả định mọi phép “copy” đều cấp phát object khác.

## 17. Trả nhiều giá trị hoặc nhiều object thay thế

Khi một phép biến đổi cần cung cấp nhiều thông tin, có thể trả một **result object** thay vì cố sửa các biến tham số của caller.

Ví dụ:

~~~java
record UpdatedUser(String name, String email) {
}

static UpdatedUser updateContact(String name, String email) {
    return new UpdatedUser(name.strip(), email.strip());
}
~~~

Đây là đoạn minh họa, giả định hai đối số khác null. Caller có thể:

~~~java
UpdatedUser result = updateContact("  An  ", "  an@example.org ");
String updatedName = result.name();
String updatedEmail = result.email();
~~~

Thay vì mong một phương thức `void update(String name, String email)` làm **hai biến String của caller** được gán lại, API trả một object thể hiện **hai giá trị kết quả**. Vì `String` bất biến, record đơn giản này dễ hiểu, nhưng production API cần thêm validation địa chỉ email theo yêu cầu.

Tương tự với thao tác chia nguyên có thương và số dư, một `record DivisionResult(int quotient,int remainder)` thường rõ ràng hơn cách cố gắng tạo hai “output parameters” bằng biến primitive.

## 18. Hiệu năng: tạo object mới có tốn chi phí không?

Có thể. Việc tạo nhiều object mới có thể dẫn tới **cấp phát bộ nhớ**, áp lực thu gom rác và sao chép dữ liệu. Tuy nhiên, cần đánh giá trong bối cảnh thực tế:

- JVM có những tối ưu như *escape analysis* và các kỹ thuật loại bỏ cấp phát trung gian trong một số trường hợp; không nên giả định mỗi `new` luôn tương ứng một cấp phát vật lý độc lập đo được.
- Với đối tượng nhỏ và bất biến, lợi ích rõ nghĩa và giảm lỗi mutation có thể đáng giá hơn một ít chi phí cấp phát.
- Với cấu trúc dữ liệu lớn, **sao chép toàn bộ collection sau mỗi cập nhật** có thể tốn chi phí, nhất là trong vòng lặp nhiều lần.
- Cấu trúc dữ liệu bất biến có *structural sharing* có thể tái sử dụng các phần không đổi thay vì sao chép mọi nút.
- Dữ liệu có identity, tài nguyên cần đóng, hoặc chia sẻ trạng thái được quản lý có thể không phù hợp với chiến lược luôn thay object.

Ví dụ:

~~~java
CartSnapshot cart = new CartSnapshot(java.util.List.of());
for (String item : incomingItems) {
    cart = cart.add(item);
}
~~~

Đây là đoạn minh họa trong ngữ cảnh có `incomingItems` phù hợp. Bản `CartSnapshot.add` ở mục 10 tạo danh sách tạm và sao chép phần tử qua mỗi lần thêm; với lượng dữ liệu lớn, cách này có thể không tối ưu. Có thể thu thập các thay đổi vào một builder/list tạm rồi đóng băng thành snapshot **một lần** sau khi hoàn tất.

**Nguyên tắc:** ưu tiên thiết kế đúng và hợp đồng rõ ràng, sau đó đo bằng benchmark/profiling nếu hiệu năng là vấn đề thật. Không sửa API theo suy đoán về bộ nhớ khi chưa có số liệu.

## 19. Đối tượng thay thế và lập trình đồng thời

Kiểu dữ liệu bất biến giúp hạn chế nhiều lỗi do **cùng sửa một object**, nhưng việc **gán lại một tham chiếu chia sẻ giữa nhiều luồng** vẫn cần bảo đảm về visibility và thao tác nguyên tử nếu có cập nhật đồng thời.

Ví dụ ý tưởng:

~~~java
Balance next = current.deposit(100);
current = next;
~~~

Trong một luồng, việc gán `current` là bình thường. Nhưng nếu `current` là một trường chia sẻ và **hai luồng cùng đọc–tính–ghi** mà không đồng bộ, một lần cập nhật có thể bị ghi đè bởi lần cập nhật khác.

Một lựa chọn là `AtomicReference<Balance>` với hàm cập nhật không side effect:

~~~java
java.util.concurrent.atomic.AtomicReference<Balance> current =
        new java.util.concurrent.atomic.AtomicReference<>(
                new Balance("A-01", 1000));

Balance after = current.updateAndGet(old -> old.deposit(100));
~~~

Đây là **đoạn minh họa**, sử dụng record `Balance` đã khai báo ở mục 5. `updateAndGet` thực hiện cập nhật tham chiếu theo cơ chế atomic phù hợp và có thể **đánh giá lambda nhiều lần** khi tranh chấp. Vì vậy hàm biến đổi nên không gây tác dụng phụ và không giả định chỉ chạy đúng một lần.

**Cảnh báo quan trọng:** ví dụ `AtomicReference` chỉ minh họa quản lý trạng thái trong bộ nhớ. Nó **không** thay thế transaction của cơ sở dữ liệu hay xử lý an toàn tiền bạc trong hệ thống thực tế.

Khác biệt cần ghi nhớ:

1. **Object bất biến** giúp bản cũ không bị sửa.
2. **Publication phù hợp** giúp luồng khác nhìn thấy trạng thái được công bố.
3. **Cập nhật nguyên tử** tránh hai luồng vô tình ghi đè kết quả nhau khi cùng thay tham chiếu.
4. **Quản lý nghiệp vụ/giao dịch** giải quyết các quy tắc rộng hơn, không tự xuất hiện từ việc trả object mới.

## 20. Thiết kế API rõ ràng: tên phương thức và hợp đồng

Một method trả đối tượng thay thế nên làm rõ:

- **Dữ liệu đầu vào nào được đọc?** Dùng toàn bộ object cũ hay chỉ một vài component?
- **Object đầu vào có bị sửa không?** Nếu API mang phong cách immutable, lời hứa “không sửa input” phải thực sự đúng cả với dữ liệu con mutable.
- **Result có luôn khác `null` không?** Nếu không, caller cần xử lý như thế nào?
- **Result có bảo đảm là instance mới không?** Hay có thể trả `this` khi không đổi?
- **Có thể ném exception nào?** Nếu lỗi, object cũ và những tác dụng phụ bên ngoài ra sao?
- **Các object con có bị chia sẻ không?** Cần shallow copy, defensive copy hay deep copy?
- **Caller phải làm gì với result?** Có cần gán lại biến, lưu vào collection hay truyền tiếp bước kế?
- **Có ràng buộc đồng thời/transaction không?** Đặc biệt với trạng thái dùng chung.

Tên `withStatus`, `moved`, `updated`, `copyWith`, `next` có thể giúp báo hiệu kiểu trả kết quả; còn tên `setStatus`, `appendInPlace`, `mutate` thường gợi ý cập nhật tại chỗ. Đây chỉ là các **quy ước**, không phải chuẩn bắt buộc. Luôn kết hợp với kiểu trả về và tài liệu.

### Minh họa Javadoc cho phong cách bất biến

Ví dụ sau khai báo một `record` hoàn chỉnh. Constructor kiểm tra tính hợp lệ của email; `withEmail` tạo và trả về một instance mới mà không sửa instance cũ:

~~~java
record UserProfile(String email) {
    UserProfile {
        if (email == null || email.isBlank() || !email.contains("@")) {
            throw new IllegalArgumentException("Email không hợp lệ");
        }
    }

    /**
     * Tạo một phiên bản mới với địa chỉ email được cập nhật.
     *
     * Không sửa trạng thái của đối tượng hiện tại.
     *
     * @param newEmail email mới, phải khác null và hợp lệ
     * @return phiên bản kết quả, không null
     * @throws IllegalArgumentException nếu newEmail không hợp lệ
     */
    UserProfile withEmail(String newEmail) {
        return new UserProfile(newEmail);
    }
}
~~~

Khi gọi `UserProfile updated = original.withEmail("new@example.com");`, `updated` chứa email mới và `original` vẫn giữ email ban đầu. Trường hợp email không hợp lệ được constructor phát hiện bằng `IllegalArgumentException`; phương thức `withEmail` kế thừa đúng quy tắc kiểm tra này.

## 21. Sai lầm thường gặp

| Sai lầm | Tại sao sai | Cách xử lý |
| --- | --- | --- |
| Gán `param = new Type(...)` rồi mong biến caller đổi | Chỉ biến tham số được gán lại | `return` result và gán ở caller |
| Gọi `current.withX(...)` mà bỏ result | Phương thức không sửa object cũ | `current = current.withX(...)` khi muốn áp dụng |
| Cho rằng `return obj` luôn tạo object mới | Có thể trả cùng instance | Đọc hợp đồng identity, không suy từ return type |
| Tạo object wrapper mới và tưởng đã deep-copy mọi thứ | Các field tham chiếu có thể trỏ chung data mutable | Sao chép phòng vệ phần dữ liệu cần độc lập |
| Viết `new ArrayList<>(source)` và nghĩ mọi phần tử object được copy | Chỉ copy các tham chiếu phần tử | Xem shallow/deep copy |
| Dùng `==` để quyết định hai giá trị kết quả bằng nhau | `==` so identity cho reference | Dùng `equals` theo value semantics |
| Dùng `List.copyOf` nhưng lại muốn sửa trực tiếp list kết quả | Danh sách không hỗ trợ mutation qua API | Tạo list tạm và trả snapshot mới |
| Tự tin dữ liệu cũ không đổi dù phương thức đã ghi DB/file | `return new ...` không tự xóa side effect | Thiết kế pure transformation hoặc transaction |
| Mặc định record “deeply immutable” | Component mutable vẫn có thể được chia sẻ | Chọn immutable components/defensive copy |
| Thấy object immutable là chắc chắn thread-safe toàn chương trình | Tham chiếu chia sẻ vẫn cần publication/atomic update | Đồng bộ nơi giữ và thay kết quả |
| Tạo bản sao cả collection trong vòng lặp dài mà không đo hiệu năng | Có thể tăng thời gian và cấp phát đáng kể | Batch/builder/structural sharing khi cần |
| Coi `return this` là lỗi trong mọi trường hợp | Có thể đúng với hàm biến đổi không thay giá trị | Làm rõ hợp đồng result có yêu cầu identity mới không |

## 22. Kiểm thử phép biến đổi trả object

Với API `Balance.deposit`, kiểm thử nên xác nhận **cả kết quả lẫn object cũ**:

| Bước kiểm tra | Kỳ vọng |
| --- | --- |
| Tạo `Balance("A-01",1000)` | Bản gốc có `cents = 1000` |
| `Balance next = original.deposit(250)` | `next.cents() == 1250` |
| Đọc lại `original.cents()` | Vẫn bằng `1000` |
| Kiểm tra `next.accountId()` | Vẫn bằng `"A-01"` |
| So `original == next` | `false` trong implementation luôn dùng `new` |
| `current = original.deposit(500)` | Caller giữ version mới có 1500 |
| `current.withdraw(2000)` | `IllegalArgumentException`, caller vẫn giữ object cũ |
| `original.deposit(Long.MAX_VALUE)` | `ArithmeticException` vì cộng bị tràn |
| Lưu `original` qua alias | Alias vẫn nhìn giá trị 1000 |

Các kiểm tra trên là **yêu cầu kiểm thử**, không phải mã JUnit sẵn chạy. Nếu dùng JUnit, có thể kết hợp `assertEquals`, `assertNotSame` (chỉ khi API hứa instance khác), `assertThrows` và so sánh snapshot trước–sau.

Với `CartSnapshot`, ngoài nội dung list trước/sau, cần thử việc caller thay đổi `input` sau constructor; nếu dùng phần tử mutable, cần thêm kiểm thử về quyền sở hữu và deep-copy theo yêu cầu ứng dụng.

**Đối với phương thức có thể trả `this`:** không nên dùng `assertNotSame` như một tiêu chí bắt buộc nếu hợp đồng chỉ hứa giá trị kết quả. Kiểm thử nên bám theo cam kết thực sự.

## 23. Bài tập tự luyện

**Câu 1 — Vì sao không đổi?** Cho:

~~~java
static void reset(Box p) {
    p = new Box(0);
}
~~~

Caller có `Box current = new Box(10);` rồi gọi `reset(current)`. `current` trỏ object nào sau lời gọi? Cần thay đổi API và cách gọi ra sao nếu muốn trỏ sang object mới?

**Câu 2 — Return có đủ không?** Phương thức `Box reset(Box old) { return new Box(0); }` đã trả object mới, nhưng caller chỉ gọi `reset(current);`. Biến `current` có đổi không? Vì sao?

**Câu 3 — Hai phiên bản.** `Balance a = new Balance("A",100);` và `Balance b = a.deposit(20);`. Giá trị `a.cents()` và `b.cents()` là bao nhiêu? `a == b` thế nào?

**Câu 4 — Aliasing.** Một biến `oldAlias` trỏ cùng object với `current`. Sau `current = current.deposit(50)`, `oldAlias` tự trỏ sang phiên bản mới không?

**Câu 5 — Record và list.** Nếu record chứa `List<MutableItem>`, chỉ viết `items = List.copyOf(items)` có bảo đảm không object con nào bị thay đổi từ bên ngoài không?

**Câu 6 — Với `String`.** Tại sao `name.trim();` có thể không thay đổi `name`, trong khi `name = name.trim();` áp dụng kết quả?

**Câu 7 — Lỗi giữa chừng.** Nếu `current = current.withdraw(1000)` ném ngoại lệ trước `return`, phép gán ở caller có hoàn tất không? Nếu thân đã ghi file trước lỗi thì sao?

**Câu 8 — Hiệu năng.** Trong `CartSnapshot`, thêm 10.000 sản phẩm bằng cách tạo/copy list sau mỗi lần thêm có thể gặp vấn đề gì? Gợi ý hướng cải thiện mà vẫn tạo snapshot cuối cùng bất biến.

**Câu 9 — Identity.** Một hàm `withCity` có thể `return this` nếu city không đổi. Điều đó có vi phạm hợp đồng “trả về **giá trị kết quả**” không? Nếu hợp đồng đòi “một **instance mới**” thì sao?

**Câu 10 — Nhiều luồng.** Nếu hai thread cùng thực hiện `shared = shared.deposit(100)` trên trường shared mà không đồng bộ, liệu chỉ vì `Balance` bất biến mà mọi cập nhật đều được giữ không?

**Câu 11 — Thiết kế.** Khi nào phương thức nên sửa tại chỗ một đối tượng, khi nào nên trả đối tượng thay thế? Nêu hai tiêu chí để lựa chọn.

### Đáp án tham khảo

1. Vẫn trỏ `Box(10)`; đổi phương thức sang `static Box reset(Box old) { return new Box(0); }` và gọi `current = reset(current)`.
2. Không; result bị bỏ, caller không thực hiện phép gán lại.
3. `a.cents() = 100`, `b.cents() = 120`, `a == b` là `false` với implementation `new Balance`.
4. Không; `oldAlias` tiếp tục chỉ object cũ. Gán lại một biến không gán lại các alias.
5. Không; `List.copyOf` không tự sao chép sâu các phần tử mutable.
6. `String` bất biến; `trim()` trả kết quả và caller phải giữ kết quả nếu muốn thay biến.
7. Không; vế phải thất bại khiến gán không xảy ra, nhưng các tác dụng phụ được thực thi trước lỗi (như ghi file) không tự rollback.
8. Có thể tốn thời gian và bộ nhớ do copy nhiều lần; có thể thu thập bằng builder/`ArrayList` tạm rồi chốt một snapshot.
9. Không vi phạm hợp đồng giá trị nếu không đổi nội dung; nhưng vi phạm nếu API cam kết luôn trả một instance **khác**.
10. Không; thao tác đọc–tính–ghi trên shared có thể mất cập nhật. Cần đồng bộ hoặc atomic compare-and-set/update phù hợp.
11. Sửa tại chỗ phù hợp object có identity/lifecycle và API cố ý cập nhật state; trả bản mới phù hợp value object, phiên bản lịch sử và yêu cầu không làm đổi input. Cần cân nhắc tài nguyên/hiệu năng và ownership.

## 24. Tài liệu đối chiếu

- [Java Language Specification 17, §15.12.4 — Run-Time Evaluation of Method Invocation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4): đánh giá biểu thức đối số và xử lý lời gọi.
- [Java Language Specification 17, §15.12.4.2 — Evaluate Arguments](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4.2): thứ tự đánh giá đối số.
- [Java Language Specification 17, §15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): biểu thức `new`.
- [Java Language Specification 17, §14.17 — Return Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.17): ngữ nghĩa `return` và trả giá trị kết quả.
- [Java Language Specification 17, §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): record và các component.
- [Java SE 17 API — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): tạo danh sách không hỗ trợ chỉnh sửa và ngữ nghĩa sao chép.
- [Java SE 17 API — AtomicReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): quản lý tham chiếu cập nhật nguyên tử.

**Ghi nhớ:** Java chuyển **bản sao giá trị tham chiếu** vào tham số, nên callee **không thể đổi biến tham chiếu của caller** bằng việc gán lại tham số. Khi muốn biểu diễn một kết quả thay thế, hãy **tạo/tính object kết quả và `return`**, sau đó để caller **gán lại biến nếu muốn áp dụng**. Nếu yêu cầu giữ object cũ không đổi, cần bảo đảm cả dữ liệu con mutable không bị sửa ngoài ý muốn; phân biệt hợp đồng **giá trị kết quả** với cam kết **identity luôn mới**.
