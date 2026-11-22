# Ẩn trường bằng `private` và cung cấp thao tác có ý nghĩa trong Java

Khi học **đóng gói (encapsulation)**, ta thường bắt đầu bằng lời khuyên “đặt field thành `private` rồi tạo getter/setter”. Nhưng đó mới là **bước đầu**, chưa phải mục tiêu thực sự.

Một class được đóng gói tốt phải **kiểm soát trạng thái của chính nó**. Thay vì để bên ngoài tự ý chỉnh từng field, class cung cấp những **thao tác có nghĩa trong miền bài toán**: tài khoản có `deposit(...)` và `withdraw(...)`; đơn hàng có `confirm()` và `cancel()`; giỏ hàng có `addItem(...)` và `removeItem(...)`; đồng hồ nhiệt có `increase()` và `decrease()`. Những thao tác đó kiểm tra điều kiện và bảo đảm object không chuyển sang trạng thái bất hợp lệ.

Đặt cạnh nhau:

~~~java
account.setBalanceCents(-500);  // API đặt số dư tùy ý, dễ phá invariant.
account.withdraw(500);         // API thể hiện hành vi và kiểm tra điều kiện.
~~~

Hai dòng trên là **mã so sánh ý tưởng**, không phải chương trình chạy độc lập. Dòng thứ hai chỉ đúng nếu class triển khai `withdraw` với validation đầy đủ. `private` không tự ngăn một setter công khai cho phép giá trị sai; **chính thiết kế public API** mới quyết định trạng thái có được bảo vệ hay không.

Bài này thuộc phần **Đóng gói** của Java Core — Class & Object, dùng Java 17+ và đi từ nguyên tắc, cơ chế access control đến thiết kế hành vi, defensive copy, invariant, exception, test và những giới hạn thực tế.

## 1. Mục tiêu học tập

Sau bài học, bạn cần có khả năng:

1. Giải thích được **field `private`** khác field public ở điểm nào và vì sao che giấu trạng thái thường hữu ích.
2. Phân biệt **ẩn dữ liệu** với **đóng gói quy tắc**: private field không đủ nếu public setter phá invariant.
3. Xác định **invariant** của một object, ví dụ số dư không âm, số lượng hợp lệ, trạng thái đơn hàng chuyển đổi đúng.
4. Thiết kế **phương thức có ý nghĩa** thay vì cung cấp một setter tùy ý cho mọi field.
5. Quyết định lúc nào cần **getter, command method, factory, setter có kiểm tra** hoặc không công khai cách sửa state.
6. Biết giữ invariant trong constructor **và** mọi phương thức cập nhật.
7. Biết cách tránh để lộ tham chiếu tới **mảng, list hoặc object mutable** trong field private.
8. Hiểu ý nghĩa của `final`, object immutable, record và defensive copy.
9. Xử lý exception sao cho một thao tác thất bại không để lại trạng thái sai.
10. Kiểm thử **hành vi công khai** thay vì phụ thuộc chi tiết field private.
11. Hiểu `private` không phải cơ chế xác thực, phân quyền người dùng, mã hóa hay đồng bộ đa luồng.
12. Biết nhận diện các trường hợp setter là hợp lý thay vì cực đoan cấm setter.

## 2. Ba lớp cần phân biệt: state, behavior và invariant

Một object có thể được hình dung như sau:

~~~text
                  Public API
           +------------------------+
Caller --->| deposit(amount)        |
Caller --->| withdraw(amount)       |
Caller --->| balanceCents()         |
           +------------+-----------+
                        |
                        v
           +------------------------+
           | private balanceCents   |
           | invariant: balance>=0  |
           +------------------------+
~~~

**State** là những dữ liệu object đang giữ, ví dụ `balanceCents`.

**Behavior** là hành vi object cung cấp, ví dụ `deposit` và `withdraw`.

**Invariant** là điều kiện class cam kết đúng đối với object ở trạng thái hợp lệ, ví dụ `balanceCents >= 0`.

Một public method không nên làm mất invariant mà constructor đã bảo đảm. Nếu một class cho phép:

~~~java
new BankAccount(1_000);  // Khởi tạo hợp lệ.
account.setBalanceCents(-20_000); // Setter bỏ qua invariant!
~~~

thì invariant bị phá ngay sau bước khởi tạo. Mục tiêu của đóng gói là **không cho mã bên ngoài tự do đi đường vòng qua những quy tắc đó**.

### `private` là gì?

`private` là access modifier của Java. Member `private` chỉ có thể được truy cập từ những ngữ cảnh mà quy tắc Java cho phép trong class/nest khai báo nó. Một top-level class khác, dù cùng package, **không tự** được quyền đọc private field của class kia.

~~~java
public final class Profile {
    private String displayName;

    public Profile(String displayName) {
        this.displayName = displayName;
    }
}
~~~

Một class độc lập ngoài `Profile` không thể đơn giản viết `profile.displayName = "A";` nếu field là private. Tuy nhiên **method trong chính Profile** vẫn có thể sửa `displayName`. Vì thế việc field private có duy trì tính hợp lệ hay không còn phụ thuộc **những method class công khai**.

## 3. So sánh: public field và private field

Cách dễ viết nhưng thiếu kiểm soát:

~~~java
public class PublicAccount {
    public long balanceCents;
}
~~~

Một caller có thể:

~~~java
PublicAccount account = new PublicAccount();
account.balanceCents = -999;
~~~

Nếu điều kiện nghiệp vụ yêu cầu số dư không âm, code đã phá vỡ điều kiện đó mà class không được can thiệp.

Phiên bản bảo vệ state:

~~~java
public class Account {
    private long balanceCents;

    public Account(long initialBalanceCents) {
        if (initialBalanceCents < 0) {
            throw new IllegalArgumentException("initial balance must be >= 0");
        }
        this.balanceCents = initialBalanceCents;
    }

    public long balanceCents() {
        return balanceCents;
    }

    public void deposit(long amountCents) {
        if (amountCents <= 0) {
            throw new IllegalArgumentException("deposit must be positive");
        }
        balanceCents = Math.addExact(balanceCents, amountCents);
    }
}
~~~

Hai class trên là **đoạn minh họa thay thế về thiết kế**, không phải một chương trình hoàn chỉnh chung tệp. Ở phiên bản thứ hai, caller chỉ có thể thay số dư qua những đường được class cho phép. `deposit` từ chối số không dương và dùng `Math.addExact` để không âm thầm tạo kết quả sai khi `long` tràn.

### Quyền của một field không quyết định toàn bộ thiết kế

Đặt field thành private rồi công khai:

~~~java
public void setBalanceCents(long newBalance) {
    this.balanceCents = newBalance;
}
~~~

vẫn cho caller tự ý thay số dư. Dù compiler không cho đọc/ghi field trực tiếp, method trên tương đương một **đường sửa trạng thái quá rộng**. Nếu muốn số dư chỉ được tăng/giảm qua nghiệp vụ, hãy cung cấp `deposit`, `withdraw` hoặc `transfer` với hợp đồng phù hợp.

## 4. Ví dụ chạy đầy đủ: chỗ ngồi được quản lý qua hành vi

Để thấy **`private` không chỉ là che tên field**, xét một lớp quản lý số chỗ được phân bổ trong buổi học. Bất biến: `0 <= allocated <= capacity`. Caller không có `setAllocated`; các thay đổi đi qua `allocate` và `release`.

Lưu **`SeatAllocationDemo.java`**:

~~~java
public class SeatAllocationDemo {
    static final class SeatAllocation {
        private final String course;
        private final int capacity;
        private int allocated;

        SeatAllocation(String course, int capacity) {
            if (course == null || course.isBlank()) {
                throw new IllegalArgumentException("course required");
            }
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity must be positive");
            }
            this.course = course.strip();
            this.capacity = capacity;
        }

        void allocate(int seats) {
            requirePositive(seats);
            if (seats > capacity - allocated) {
                throw new IllegalStateException("not enough seats");
            }
            allocated += seats;
        }

        void release(int seats) {
            requirePositive(seats);
            if (seats > allocated) {
                throw new IllegalStateException("more than allocated");
            }
            allocated -= seats;
        }

        String summary() {
            return course + ": " + allocated + "/" + capacity;
        }

        private static void requirePositive(int value) {
            if (value <= 0) {
                throw new IllegalArgumentException("seats must be positive");
            }
        }
    }

    public static void main(String[] args) {
        SeatAllocation seats = new SeatAllocation("  Java Core  ", 10);
        seats.allocate(3);
        seats.allocate(4);
        System.out.println(seats.summary());

        try {
            seats.allocate(5);
        } catch (IllegalStateException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }

        seats.release(2);
        try {
            seats.release(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }

        System.out.println("after failures: " + seats.summary());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SeatAllocationDemo.java
java SeatAllocationDemo
~~~

~~~text
Java Core: 7/10
rejected: not enough seats
rejected: seats must be positive
after failures: Java Core: 5/10
~~~

### Diễn biến và lý do thiết kế

1. Constructor kiểm tên và capacity, sau đó instance bắt đầu với `allocated == 0`.
2. Hai thao tác `allocate(3)`, `allocate(4)` đưa kết quả lên 7/10.
3. `allocate(5)` bị từ chối trước khi tăng vì chỉ còn ba chỗ; không có setter bỏ qua kiểm tra.
4. `release(2)` đưa kết quả xuống 5/10; `release(0)` bị từ chối.
5. So sánh `seats > capacity - allocated` không cộng số lượng trước khi kiểm tra, tránh overflow không cần thiết và giữ bất biến.

Đây là mô hình **đơn luồng**, không định danh từng người hay hợp đồng hủy chỗ cụ thể. Hệ thống thực phải bổ sung ranh giới concurrency, authorization và transaction khi phù hợp. Bài học là **method công khai mô tả hành vi có nghĩa và bảo vệ state qua mọi đường gọi**.

## 5. Vì sao getter/setter cho mọi field không đồng nghĩa encapsulation tốt?

Một class thường được sinh mã tự động:

~~~java
class Person {
    private String name;
    private int age;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public int getAge() {
        return age;
    }

    public void setAge(int age) {
        this.age = age;
    }
}
~~~

Đây là class minh họa. Các field là private, nhưng `setName(null)` và `setAge(-500)` vẫn được chấp nhận. Nếu class có invariant tên không rỗng và tuổi không âm, các setter này phá invariant.

**Điều cần hỏi không phải “field nào chưa có setter?”, mà là “tại sao caller cần thay đổi dữ liệu này?”**

Ví dụ, với một đơn hàng, có thể hợp lý khi có `changeDeliveryAddress(Address newAddress)` **chỉ trước khi gửi hàng**, thay vì `setAddress(...)` được gọi ở bất cứ trạng thái nào. Với một điểm số đã chốt, có thể chỉ cho phép `recordGrade(...)` bởi quy trình xác thực phù hợp, không cho `setGrade(...)` tùy ý.

### Khi setter có thể hợp lý?

Setter không phải điều cấm của Java:

- Một bean cấu hình đang ở giai đoạn xây dựng có thể cần `setTimeout(...)` với validation.
- Một đối tượng giao diện người dùng có thể cần cập nhật thuộc tính hiển thị nhiều lần.
- DTO hoặc framework serialization có thể yêu cầu dạng constructor/setter nhất định.
- Thuộc tính không có ràng buộc nghiệp vụ phức tạp có thể dùng setter có kiểm tra rõ ràng.

Khi setter thật sự phù hợp, hãy đảm bảo nó **validate** và bảo toàn các ràng buộc liên quan. Tránh viết public setter chỉ vì một IDE có chức năng Generate Getters and Setters.

## 6. “Tell, don't ask”: yêu cầu object thực hiện hành vi

Thiết kế quá phụ thuộc getter đôi khi khiến caller lấy dữ liệu ra, tự tính toán, rồi ghi ngược:

~~~java
if (account.getBalanceCents() >= amount) {
    account.setBalanceCents(account.getBalanceCents() - amount);
}
~~~

Đây là **đoạn phản ví dụ**. Quy tắc rút tiền đang bị đặt **ngoài class Account**:

- Bất kỳ caller nào cũng có thể quên kiểm tra số dư.
- Nhiều nơi sẽ viết lại cùng một logic.
- Một thay đổi quy tắc nghiệp vụ phải sửa nhiều caller.
- Trong môi trường đa luồng, kiểm tra rồi cập nhật bằng các lời gọi tách biệt còn có nguy cơ race condition.

Cách hướng đối tượng:

~~~java
account.withdraw(amount);
~~~

Caller gửi **một yêu cầu có ý nghĩa**; object kiểm tra điều kiện và thực hiện trạng thái chuyển đổi phù hợp. Đây là một ứng dụng thực tế của nguyên tắc **Tell, Don't Ask**: ưu tiên đặt hành vi bên cạnh dữ liệu và invariant mà hành vi đó quản lý.

Không phải mọi getter đều xấu. `balanceCents()` rất hữu ích để hiển thị báo cáo. Vấn đề xuất hiện khi caller dùng getter để **tái triển khai luật nội bộ** và ghi ngược bằng setter không kiểm soát.

## 7. Thiết kế phương thức dựa trên miền bài toán

So sánh:

| Mục đích | API ít ý nghĩa | API mô tả hành vi |
| --- | --- | --- |
| Nạp tiền | `setBalance(old + amount)` | `deposit(amount)` |
| Rút tiền | `setBalance(old - amount)` | `withdraw(amount)` |
| Chốt đơn hàng | `setStatus(CONFIRMED)` | `confirm()` |
| Hủy đơn hàng | `setStatus(CANCELED)` | `cancel(reason)` |
| Tăng số lượng | `setQuantity(old + n)` | `addQuantity(n)` |
| Bật thiết bị | `setPower(true)` | `turnOn()` |
| Đăng ký khóa học | `setEnrolled(true)` | `enroll(student)` |
| Hoàn thành nhiệm vụ | `setDone(true)` | `complete()` |

Các tên phía phải có lợi khi hành vi **cần kiểm tra điều kiện riêng**. Nếu API chỉ là dữ liệu thuần túy không có quy tắc miền, việc tạo quá nhiều method dài dòng cũng không hữu ích.

### Một thao tác có ý nghĩa nên quy định

- Điều kiện được phép gọi (precondition).
- Tác động thành công lên trạng thái (postcondition).
- Invariant nào phải giữ.
- Khi nào lỗi được báo và bằng exception nào hoặc kiểu kết quả nào.
- Có side effect bên ngoài không.
- Có thể gọi lặp lại hay không (idempotence hoặc chính sách rõ).
- Dữ liệu nào caller có thể đọc sau đó.

Ví dụ `cancel()` có thể được gọi nhiều lần và im lặng nếu đã hủy, **hoặc** ném exception ở lần thứ hai. Cả hai chính sách đều có thể hợp lệ; class cần chọn một hợp đồng nhất quán.

## 8. Ví dụ chạy: đóng gói các chuyển trạng thái

Lưu file **`OrderLifecycleDemo.java`**:

~~~java
public class OrderLifecycleDemo {
    enum State {
        DRAFT, CONFIRMED, CANCELED
    }

    static final class Order {
        private final String code;
        private State state = State.DRAFT;

        Order(String code) {
            if (code == null || code.isBlank()) {
                throw new IllegalArgumentException("code required");
            }
            this.code = code.strip();
        }

        void confirm() {
            if (state != State.DRAFT) {
                throw new IllegalStateException("only draft can be confirmed");
            }
            state = State.CONFIRMED;
        }

        void cancel() {
            if (state == State.CANCELED) {
                throw new IllegalStateException("already canceled");
            }
            state = State.CANCELED;
        }

        String describe() {
            return code + " -> " + state;
        }
    }

    public static void main(String[] args) {
        Order order = new Order("  O-01  ");
        System.out.println(order.describe());

        order.confirm();
        System.out.println(order.describe());

        try {
            order.confirm();
        } catch (IllegalStateException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }

        order.cancel();
        System.out.println(order.describe());
    }
}
~~~

~~~bash
javac -encoding UTF-8 OrderLifecycleDemo.java
java OrderLifecycleDemo
~~~

Stdout:

~~~text
O-01 -> DRAFT
O-01 -> CONFIRMED
rejected: only draft can be confirmed
O-01 -> CANCELED
~~~

Nếu class công khai `setState(State)` tự do, caller có thể đưa đơn từ trạng thái `CANCELED` trở lại `DRAFT` trái ý định. API `confirm()` và `cancel()` diễn đạt một **state machine nhỏ**:

~~~text
            confirm()
DRAFT ----------------> CONFIRMED
  |                         |
  | cancel()                | cancel()
  v                         v
CANCELED <--------------- CANCELED
~~~

Trong ví dụ, `cancel()` cho phép hủy từ DRAFT hoặc CONFIRMED; đây là một **quy tắc giả định**. Với hệ thống thật, có thể cần chặn hủy sau khi giao hàng, lưu lý do hủy, hoàn tiền hay kiểm tra quyền.

**Lưu ý về đóng gói:** Field `state` private là một phần bảo vệ; điểm quan trọng hơn là **không có public setter bỏ qua luật chuyển trạng thái**.

## 9. Constructor cũng phải bảo vệ invariant

Nếu chỉ kiểm tra trong các method nhưng constructor cho tạo object sai, mọi điều kiện sau đó dễ bị phá.

Ví dụ nên tránh:

~~~java
class InventoryItem {
    private int stock;

    InventoryItem(int stock) {
        this.stock = stock; // Cho phép stock âm.
    }

    void take(int amount) {
        // Phương thức có thể giả định stock ban đầu hợp lệ, nhưng không phải vậy.
    }
}
~~~

Phiên bản tốt hơn phải kiểm tra `stock >= 0` ngay khi khởi tạo, và mọi method cập nhật phải giữ `stock >= 0`. Cùng một invariant cần được áp dụng nhất quán trong các constructor overload và đường tạo object qua factory.

### Chống tự gán tham số

Trong constructor:

~~~java
class Item {
    private final String code;

    Item(String code) {
        this.code = code;
    }
}
~~~

`this.code` là field, còn `code` bên phải là tham số. Viết `code = code;` chỉ tự gán tham số và không gán field đúng ý định. Với `final` field, compiler có thể phát hiện field chưa được khởi tạo; với field không final, lỗi có thể âm thầm để lại giá trị mặc định.

### Fail fast và phép gán bên ngoài

Nếu constructor ném exception, biểu thức `new Item(...)` không hoàn tất bình thường và không cung cấp reference mới cho caller. Câu lệnh:

~~~java
current = new Item(invalidCode);
~~~

không gán reference mới vào `current` nếu vế phải ném exception. Nhưng nếu constructor đã ghi log, tăng static counter, đăng ký callback hay thực hiện side effect trước khi ném, những side effect ấy **không tự rollback**. Đóng gói tốt cũng cần tránh đưa một `this` chưa khởi tạo xong ra bên ngoài.

## 10. Validation: kiểm tra argument trước khi sửa state

Một phương thức thao tác có ý nghĩa nên báo lỗi **trước khi** để trạng thái ở dạng không hợp lệ.

~~~java
void remove(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException("quantity must be positive");
    }
    if (quantity > stock) {
        throw new IllegalStateException("not enough stock");
    }
    stock -= quantity;
}
~~~

Đây là method minh họa trong class có private field `stock` và invariant `stock >= 0`. Khi `quantity <= 0` hoặc số lượng yêu cầu vượt tồn kho, method ném exception **trước khi trừ**.

Phân biệt:

- `IllegalArgumentException`: giá trị tham số vi phạm hợp đồng, chẳng hạn số lượng không dương.
- `IllegalStateException`: thao tác không thực hiện được do trạng thái hiện tại, chẳng hạn không đủ hàng.
- `NullPointerException`: có thể là chính sách rõ khi dùng `Objects.requireNonNull(...)` cho argument không được phép null.
- Checked exceptions: dùng khi hành vi có loại thất bại checked như I/O mà hợp đồng API cần biểu diễn.

Không có công thức máy móc bắt buộc mọi domain model phải dùng đúng những exception kể trên. Quan trọng là loại và message có nghĩa, được mô tả nhất quán trong API.

### Rủi ro thay đổi nửa chừng

Ví dụ:

~~~java
void unsafeRemove(int quantity) {
    stock -= quantity;
    if (stock < 0) {
        throw new IllegalStateException("not enough stock");
    }
}
~~~

Nếu ném exception, `stock` **đã bị giảm âm**. Exception trong Java không tự đưa field về giá trị cũ. Thiết kế tốt thường **tính toán và validate trước, commit sau**, hoặc có phương án rollback thực sự khi nhiều bước phải thay đổi.

## 11. Chống tràn số cũng là bảo vệ invariant

Một phép cộng trên `int` hoặc `long` có thể **tràn** mà không ném lỗi nếu dùng phép `+` thông thường.

Ví dụ:

~~~java
long balance = Long.MAX_VALUE;
balance = balance + 1; // Tràn về Long.MIN_VALUE.
~~~

Nếu invariant yêu cầu số dư không âm, kết quả tràn tạo trạng thái sai. Dùng `Math.addExact` hoặc `Math.subtractExact` có thể giúp phát hiện tràn trong trường hợp phù hợp.

~~~java
long updated = Math.addExact(balanceCents, amountCents);
balanceCents = updated;
~~~

Nếu `Math.addExact` ném `ArithmeticException`, phép gán field **chưa xảy ra**. Đây là lý do nên **tính kết quả mới vào local rồi gán field sau khi tính toán thành công** khi muốn giảm nguy cơ cập nhật nửa chừng.

Trong bài toán tiền tệ thực tế còn cần xét đơn vị tiền, giới hạn giao dịch, chính sách làm tròn, trùng lặp yêu cầu và tính nhất quán đa luồng. `private` không thay thế các biện pháp đó.

## 12. Getter an toàn và getter làm lộ trạng thái

Một getter đọc giá trị primitive thường ít rủi ro:

~~~java
public int count() {
    return count;
}
~~~

Nhưng một getter trả reference mutable có thể phá đóng gói, kể cả field là private:

~~~java
class Team {
    private final java.util.List<String> members =
            new java.util.ArrayList<>();

    public java.util.List<String> members() {
        return members; // Trả nguyên reference mutable nội bộ!
    }
}
~~~

Caller có thể:

~~~java
team.members().clear();
~~~

và sửa danh sách nội bộ **mà không qua phương thức nghiệp vụ**. Trường hợp này field private **không mang lại encapsulation hữu hiệu**, vì API công khai một alias có quyền sửa state.

**Nguyên tắc:** Đừng chỉ kiểm tra modifier của field. Hãy kiểm tra **những reference mà public API trả ra** và những method có thể gọi trên object được trả.

## 13. Defensive copy: nhận dữ liệu mutable từ caller

Khi constructor nhận mảng hoặc collection mutable, việc gán thẳng reference vào field private có thể để caller tiếp tục sửa dữ liệu bên trong object.

~~~java
class Roster {
    private final java.util.List<String> names;

    Roster(java.util.List<String> names) {
        this.names = names; // Vẫn dùng chung ArrayList của caller.
    }
}
~~~

Nếu caller làm `source.add("X")` sau `new Roster(source)`, `Roster` cũng nhìn thấy phần tử mới. Field là `private final` nhưng **đối tượng List được tham chiếu vẫn mutable**.

Một phương án phù hợp khi danh sách chứa các phần tử `String` immutable là:

~~~java
this.names = java.util.List.copyOf(names);
~~~

`List.copyOf`:

- Không cho sửa cấu trúc danh sách trả về bằng các method mutation thông thường.
- Từ chối source null và phần tử null.
- Có thể tái sử dụng một list đã không thay đổi được; không phải luôn bắt buộc tạo container mới.
- **Không deep copy** các object phần tử mutable.

Với `List<Person>` và `Person` mutable, `List.copyOf` chỉ bảo vệ cấu trúc list; những Person objects bên trong vẫn có thể bị sửa qua alias khác.

## 14. Ví dụ chạy: bảo vệ danh sách nội bộ

Lưu file **`RosterEncapsulationDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class RosterEncapsulationDemo {
    static final class Roster {
        private final List<String> names;

        Roster(List<String> names) {
            Objects.requireNonNull(names, "names");

            List<String> copy = List.copyOf(names);
            if (copy.isEmpty()) {
                throw new IllegalArgumentException("roster must not be empty");
            }
            for (String name : copy) {
                if (name.isBlank()) {
                    throw new IllegalArgumentException("name must not be blank");
                }
            }

            this.names = copy;
        }

        List<String> members() {
            return names;
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("Mai");
        input.add("An");

        Roster roster = new Roster(input);

        input.add("Binh");
        System.out.println("input=" + input);
        System.out.println("roster=" + roster.members());

        try {
            roster.members().add("Lan");
        } catch (UnsupportedOperationException ex) {
            System.out.println("cannot modify roster list");
        }

        System.out.println("roster size=" + roster.members().size());
    }
}
~~~

~~~bash
javac -encoding UTF-8 RosterEncapsulationDemo.java
java RosterEncapsulationDemo
~~~

Stdout:

~~~text
input=[Mai, An, Binh]
roster=[Mai, An]
cannot modify roster list
roster size=2
~~~

### Vì sao ví dụ này giữ encapsulation?

1. Constructor kiểm tra reference `names` khác null.
2. `List.copyOf` tạo/nhận một list không thay đổi được qua API mutation bình thường, tách cấu trúc khỏi `ArrayList` mutable caller truyền vào.
3. Class kiểm tra danh sách có phần tử và mỗi tên không blank.
4. Sau khi caller thêm `Binh` vào `input`, state của `Roster` vẫn là `[Mai, An]`.
5. `roster.members().add("Lan")` bị từ chối bằng `UnsupportedOperationException`; caller không thể tùy ý sửa collection state từ accessor.
6. `String` là immutable nên trong ví dụ không có vấn đề caller sửa field bên trong phần tử.

Có thể thay `members()` bằng `List.copyOf(names)` một lần nữa, nhưng không bắt buộc nếu `names` đã tham chiếu một list không thay đổi được theo hợp đồng và các phần tử đều immutable. Tránh sao chép lặp lại vô ích trong API gọi nhiều lần.

## 15. Mảng: `private` không ngăn tham chiếu bị lộ

Mảng là mutable object. Nếu constructor giữ thẳng `input` hay getter trả thẳng `values`, caller có thể sửa phần tử dù field là `private final`. Với `int[]`, một lựa chọn là **copy khi nhận, kiểm trên bản copy và copy khi trả**. Với `Person[]`, `clone()` chỉ sao chép array references, không sao chép mutable Person objects.

## 16. Ví dụ chạy: thao tác có kiểm soát và snapshot mảng

Khác với getter trả array đơn thuần, ví dụ này vừa bảo vệ hai chiều aliasing, vừa có **method cập nhật có kiểm tra** để giữ bất biến `0 <= score <= 100`.

Lưu **`ScorePolicyDemo.java`**:

~~~java
import java.util.Arrays;

public class ScorePolicyDemo {
    static final class ScoreSheet {
        private final int[] scores;

        ScoreSheet(int[] input) {
            if (input == null || input.length == 0) {
                throw new IllegalArgumentException("scores required");
            }
            int[] copy = input.clone();
            for (int score : copy) {
                validate(score);
            }
            scores = copy;
        }

        void replaceScore(int index, int next) {
            validate(next);
            scores[index] = next;
        }

        int[] snapshot() {
            return scores.clone();
        }

        private static void validate(int score) {
            if (score < 0 || score > 100) {
                throw new IllegalArgumentException("invalid score");
            }
        }
    }

    public static void main(String[] args) {
        int[] input = {70, 80};
        ScoreSheet sheet = new ScoreSheet(input);

        input[0] = -10;
        int[] outward = sheet.snapshot();
        outward[1] = -30;
        System.out.println(Arrays.toString(sheet.snapshot()));

        sheet.replaceScore(0, 95);
        try {
            sheet.replaceScore(1, 120);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }
        System.out.println(Arrays.toString(sheet.snapshot()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ScorePolicyDemo.java
java ScorePolicyDemo
~~~

~~~text
[70, 80]
rejected: invalid score
[95, 80]
~~~

Input/output alias mutations không chạm private array. `replaceScore(0,95)` thành công; `replaceScore(1,120)` bị từ chối trước khi thay nên điểm thứ hai vẫn 80. Ví dụ nhấn mạnh **encapsulation của hành vi**, còn các trường hợp sao chép sâu cho object arrays, multidimensional arrays, lists/maps, mutable elements và concurrency phải được xác định qua **ownership contract** riêng, không chỉ dựa vào `clone()`.

## 17. Cung cấp hành vi thay vì đưa collection mutable ra ngoài

Đôi khi người dùng cần chỉnh danh sách chứ không chỉ xem. Thay vì trả `List` mutable nội bộ, class có thể cung cấp:

~~~java
cart.addItem(sku, unitPriceCents, quantity);
cart.removeItem(sku);
cart.totalCents();
cart.itemsSnapshot();
~~~

Trong đó:

- `addItem` kiểm tra SKU, giá và số lượng.
- `removeItem` quyết định điều gì xảy ra nếu SKU không tồn tại.
- `totalCents` tính tổng dựa trên dữ liệu bên trong.
- `itemsSnapshot` trả một snapshot không cho caller sửa collection state.

Thiết kế này có ưu điểm là **luật cập nhật tập trung**. Caller không cần biết class lưu `ArrayList`, `HashMap`, mảng hay cấu trúc khác.

### Không biến API thành bộ sưu tập setter trá hình

Một method tên đẹp nhưng vẫn cho phép truyền state tùy ý cũng không đủ:

~~~java
void updateEverything(int stock, long price, boolean sold) {
    this.stock = stock;
    this.price = price;
    this.sold = sold;
}
~~~

Nếu không validate quan hệ giữa ba giá trị và không biểu diễn một operation domain rõ, `updateEverything` vẫn làm lộ quyền điều khiển trạng thái quá rộng. **Tên method không thay thế thiết kế hợp đồng.**

## 18. Ví dụ giỏ hàng chỉ công khai thao tác hợp lệ

Lưu file **`ShoppingCartEncapsulationDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ShoppingCartEncapsulationDemo {
    record Line(String sku, long unitPriceCents, int quantity) {
        Line {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("sku required");
            }
            if (unitPriceCents < 0 || quantity <= 0) {
                throw new IllegalArgumentException("invalid price or quantity");
            }
        }

        long subtotalCents() {
            return Math.multiplyExact(unitPriceCents, quantity);
        }
    }

    static final class Cart {
        private final List<Line> lines = new ArrayList<>();

        void addItem(String sku, long unitPriceCents, int quantity) {
            Line candidate = new Line(sku, unitPriceCents, quantity);
            candidate.subtotalCents(); // Kiểm tra tràn trước khi lưu.
            lines.add(candidate);
        }

        long totalCents() {
            long total = 0;
            for (Line line : lines) {
                total = Math.addExact(total, line.subtotalCents());
            }
            return total;
        }

        List<Line> itemsSnapshot() {
            return List.copyOf(lines);
        }
    }

    public static void main(String[] args) {
        Cart cart = new Cart();
        cart.addItem("P01", 100, 2);
        cart.addItem("P02", 50, 1);

        List<Line> snapshot = cart.itemsSnapshot();
        System.out.println("lines=" + snapshot.size());
        System.out.println("total=" + cart.totalCents());

        try {
            snapshot.clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot cannot be cleared");
        }

        try {
            cart.addItem("BAD", 20, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid item rejected");
        }

        System.out.println("total after errors=" + cart.totalCents());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ShoppingCartEncapsulationDemo.java
java ShoppingCartEncapsulationDemo
~~~

Stdout:

~~~text
lines=2
total=250
snapshot cannot be cleared
invalid item rejected
total after errors=250
~~~

**Vì sao thiết kế này hợp lý cho phạm vi ví dụ?**

- `lines` private, không có method trả nguyên `ArrayList` mutable.
- `addItem` kiểm tra một dòng dữ liệu trước khi thêm.
- `Line` là record chứa `String` và primitive, nên dữ liệu từng dòng trong ví dụ không có mutable reference component.
- `List.copyOf(lines)` trả list không sửa được; caller không thể clear giỏ bằng cách sửa snapshot.
- Khi thêm một dòng có quantity không hợp lệ, `new Line(...)` ném exception **trước `lines.add`**, nên số dòng và tổng không thay đổi.
- `totalCents` chứa logic tính tổng, giảm việc caller phải duyệt/nhân/cộng bên ngoài.

**Giới hạn:** Ví dụ cho phép nhiều dòng có cùng SKU và tính tổng khi được yêu cầu. Một giỏ hàng thực tế có thể phải gộp SKU, kiểm tra tổng khả năng thanh toán ngay khi thêm, hỗ trợ xóa/cập nhật có điều kiện, thuế, khuyến mãi và concurrent updates. Khi điều kiện nghiệp vụ mở rộng, chúng nên tiếp tục được giữ bên trong những thao tác có nghĩa của Cart hoặc một domain service phù hợp.

## 19. `private final` khác immutable object thế nào?

~~~java
private final java.util.List<String> names;
~~~

Từ khóa `final` trên field ngăn **gán lại field reference** sau khi được khởi tạo theo quy tắc Java, nhưng **không tự làm object List bất biến**.

~~~java
final java.util.List<String> names = new java.util.ArrayList<>();
names.add("Mai"); // Hợp lệ: thay đổi object.
 // names = new java.util.ArrayList<>(); // Sai: gán lại biến final.
~~~

Do đó:

- `private` giới hạn **nơi có thể trực tiếp truy cập field**.
- `final` giới hạn **khả năng gán lại field/biến**.
- **Immutable object** là một đặc tính của thiết kế state và public API.
- **Defensive copy** là một kỹ thuật để ngăn alias mutable từ bên ngoài phá invariant.

Một class có thể có mọi field `private final` nhưng vẫn mutable thông qua `List.add`, `StringBuilder.append` hoặc những object bên trong field. Đừng coi private + final là điều kiện đủ của deep immutability.

### Immutable value object

Một value object có thể thiết kế không có method sửa state:

~~~java
public final class Quantity {
    private final int value;

    public Quantity(int value) {
        if (value < 0) {
            throw new IllegalArgumentException("negative quantity");
        }
        this.value = value;
    }

    public int value() {
        return value;
    }

    public Quantity plus(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("negative addition");
        }
        return new Quantity(Math.addExact(value, amount));
    }
}
~~~

`plus(...)` tạo **Quantity mới** thay vì sửa object cũ. Đây cũng là encapsulation: caller có hành vi hợp lệ để tạo giá trị kết quả và không có quyền phá invariant của Quantity hiện có.

## 20. Record: tiện cho value object, nhưng không tự có invariant

Trong Java 17, `record` hỗ trợ các value-like data carriers. Nhưng record **không tự từ chối null hoặc giá trị sai**.

~~~java
record Price(long cents) {
    Price {
        if (cents < 0) {
            throw new IllegalArgumentException("price must be nonnegative");
        }
    }

    Price plus(Price other) {
        java.util.Objects.requireNonNull(other, "other");
        return new Price(Math.addExact(cents, other.cents));
    }
}
~~~

Đây là record minh họa. Compact constructor kiểm tra invariant `cents >= 0`. `plus` mô tả thao tác cộng giá với một Price khác và tạo instance mới hợp lệ.

### Record không phải biện pháp bảo vệ mutable component tự động

~~~java
record UnsafeRoster(java.util.List<String> names) {}
~~~

Caller có thể tạo `new UnsafeRoster(mutableList)` rồi sửa list từ bên ngoài; record component accessor cũng trả reference tới list ấy. Record fields final không ngăn mutation của list.

Một record muốn immutable sâu hơn có thể dùng compact constructor:

~~~java
record SafeRoster(java.util.List<String> names) {
    SafeRoster {
        names = java.util.List.copyOf(names);
    }
}
~~~

Với phần tử `String` immutable, list cấu trúc không sửa được trong ví dụ. Với phần tử mutable, cần tiếp tục xét copy/ownership ở cấp phần tử. Không sử dụng record chỉ vì cú pháp ngắn mà bỏ qua invariant.

## 21. `private` có áp dụng với class con không?

Một subclass không được trực tiếp sử dụng private field của superclass như một inherited accessible member.

~~~java
class Parent {
    private int counter = 10;

    protected void incrementCounter() {
        counter++;
    }

    public int counter() {
        return counter;
    }
}

class Child extends Parent {
    void perform() {
        incrementCounter(); // Gọi protected operation.
        // counter++;        // Không truy cập được private field của Parent.
    }
}
~~~

Đây là class minh họa. Object kiểu `Child` vẫn có state do phần `Parent` quản lý, nhưng Child không được tự do sửa private field của Parent. Nó phải dùng những **operation được Parent cho phép**.

### Vì sao không mở field `protected` cho tiện?

`protected int counter` cho subclass nhiều quyền điều chỉnh state hơn, có thể khiến subclass phá invariant của superclass. Một **protected method có hợp đồng** như `incrementCounter()` thường an toàn hơn protected mutable field.

Không có quy tắc cấm protected field tuyệt đối, nhưng protected là một quyết định mở rộng API dành cho inheritance và dễ tạo ràng buộc tương thích về sau.

### Nested classes và private access

Nested classes trong cùng nest có thể truy cập private members theo quy tắc Java 17. Điều này **không** làm private thành package-private hay public. Mục tiêu của private vẫn là giới hạn boundary của code được tin cậy quản lý chi tiết cài đặt, không phải cô lập từng dòng mã khỏi mọi class lồng nhau.

## 22. Có nên giữ mọi field `private`?

Đối với class domain mutable, private thường là **mặc định tốt**, nhưng không phải luật buộc mọi kiểu dữ liệu:

- `public static final` constants thật sự ổn định có thể công khai.
- Java record có component accessors public tương ứng theo hợp đồng kiểu.
- Một data carrier không có luật nghiệp vụ đáng kể có thể dùng cấu trúc đơn giản phù hợp.
- Framework có yêu cầu về access hoặc mapping; cần cân bằng với encapsulation và khả năng kiểm thử.
- Trong library API, dữ liệu mutable được đưa ra ngoài có thể tạo cam kết khó thay đổi về sau.

Điểm quan trọng là **đừng công khai một chi tiết cài đặt mutable nếu caller không cần quyền sửa nó**.

### Quy tắc thiết kế API gợi ý

| Nhu cầu caller | API có thể phù hợp |
| --- | --- |
| Xem một số nguyên/giá trị immutable | Getter/query method |
| Yêu cầu chuyển trạng thái | Method có tên hành vi: `confirm()`, `cancel()` |
| Điều chỉnh một đại lượng theo quy tắc | `increase(...)`, `withdraw(...)` |
| Xem nhiều phần tử | Unmodifiable snapshot hoặc iterator/query được kiểm soát |
| Thêm/xóa phần tử | `addItem(...)`, `removeItem(...)` |
| Tạo object với invariant | Constructor/factory validate |
| Cập nhật nhiều thuộc tính liên quan | Method nhận value object/command, validate atomically trong phạm vi object |
| Chỉ cần truyền dữ liệu giữa các tầng | DTO/record có hợp đồng rõ, không nhất thiết nhiều domain behaviors |

Đừng biến đóng gói thành hàng trăm method chỉ để không có setter. Chọn boundary theo **ai sở hữu invariant và ai chịu trách nhiệm giữ nó**.

## 23. Tách read API và write API

Một thiết kế dễ hiểu thường phân biệt:

**Query methods**: trả thông tin mà không sửa state quan sát được, ví dụ `balanceCents()`, `isConfirmed()`, `totalCents()`.

**Command methods**: yêu cầu object thay đổi state có kiểm soát, ví dụ `deposit(...)`, `confirm()`, `addItem(...)`.

Sự phân biệt này gần với **Command–Query Separation (CQS)** ở mức phương thức, không đồng nghĩa bắt buộc dùng kiến trúc CQRS toàn hệ thống.

### API query vẫn có thể làm lộ mutable state

~~~java
List<Item> items() {
    return internalItems;
}
~~~

Tên method là query, nhưng kết quả chứa reference mutable tới state nội bộ thì caller vẫn có thể thay đổi object. Vì vậy phải đánh giá **kiểu dữ liệu trả về và quyền sửa** chứ không chỉ tên method.

### Một command nên giữ invariant trên mọi đường bình thường

Nếu `complete()` có thể bị gọi khi task đã canceled, method nên từ chối hoặc định nghĩa một trạng thái chuyển hợp lệ. Việc chuyển `status` tùy ý sang COMPLETE không thể được kiểm soát nếu class cho public setter không kiểm tra.

## 24. Encapsulation và tính nguyên tử: một operation có thể gồm nhiều bước

Một thao tác như chuyển tiền giữa hai Account objects cần kiểm tra cả hai phía, tránh trừ bên gửi rồi ném exception trước khi cộng bên nhận.

Phản ví dụ:

~~~java
void transferUnsafe(Account from, Account to, long amount) {
    from.withdraw(amount);
    to.deposit(amount);
}
~~~

Đây là **mảnh mã minh họa**. Nếu `to.deposit(amount)` ném exception sau khi `from.withdraw(amount)` thành công, tiền bên gửi đã bị trừ. Việc code được tổ chức thành hai method đóng gói riêng không tự tạo **transaction nguyên tử trên nhiều object**.

Muốn an toàn phải xác định:

- Có quyền chuyển không, có đủ số dư không?
- Người nhận có hợp lệ không? Có giới hạn số dư không?
- Nếu cập nhật một bên thất bại thì làm thế nào?
- Có nhiều thread/thao tác đồng thời không?
- Có I/O, database hoặc mạng không? Cần transaction/idempotency không?

Với hệ thống có database, một **domain service/transaction boundary** có thể phối hợp nhiều object để bảo đảm tính nhất quán. Với cấu trúc in-memory, cũng cần kiểm soát đồng bộ và việc cập nhật các phần tử liên quan. **Encapsulation bảo vệ invariant cục bộ; không tự bảo đảm atomicity xuyên nhiều object hoặc process.**

## 25. `private` không làm class thread-safe

Một mutable field private vẫn có thể bị cập nhật từ nhiều thread qua public method:

~~~java
class Counter {
    private int value;

    public void increment() {
        value++;
    }

    public int value() {
        return value;
    }
}
~~~

`value++` là phép đọc–tính–ghi, **không mặc nhiên atomic** cho hai thread. Nếu cả hai thread gọi `increment()` đồng thời, có thể có cập nhật bị mất. Private chỉ giới hạn direct access, **không tự giải quyết race condition, visibility hay happens-before**.

Khi object được chia sẻ giữa nhiều thread, cân nhắc:

- Bất biến (immutable) nếu state không cần thay đổi.
- Synchronization như `synchronized` hoặc lock được dùng nhất quán.
- Kiểu atomic thích hợp khi chỉ có thao tác đơn giản.
- Ownership theo một thread hoặc message passing khi kiến trúc cho phép.

Không chỉ bảo vệ write; query đọc cùng state cũng cần chiến lược visibility nhất quán. Không nên dùng `synchronized` một cách ngẫu nhiên trên vài method rồi khẳng định mọi invariant đa trường đã an toàn.

### Encapsulation hỗ trợ concurrency, nhưng không thay thế concurrency design

Điểm tốt của API có nghĩa là có **ít đường thay đổi state hơn**, nên sau này dễ đặt synchronization/transaction quanh toàn bộ operation. Nếu public setters cho phép caller tự đọc–tính–ghi, class khó kiểm soát được một operation gồm nhiều bước.

## 26. `private` không phải xác thực, phân quyền hay bảo mật dữ liệu

Access modifiers chủ yếu kiểm soát **quy tắc truy cập của Java code**. Chúng không phải biện pháp thay thế cho:

- Kiểm tra caller có được phép giao dịch hay không.
- Xác thực người dùng.
- Authorization theo vai trò hoặc tài nguyên.
- Mã hóa dữ liệu nhạy cảm.
- Chống ghi đè cơ sở dữ liệu ngoài quy trình.
- Kiểm tra dữ liệu từ mạng, file hoặc reflection/framework.

Một public method có thể bị bất kỳ caller code nào có quyền gọi nó dùng để thử giao dịch. Nếu nghiệp vụ cần phân quyền, hãy kiểm tra quyền ở boundary đúng như service/API layer và thiết kế quyền của domain command thích hợp.

Reflection, serialization và một số môi trường runtime cũng có cơ chế tiếp cận dữ liệu khác với việc đọc field trực tiếp bằng cú pháp Java thông thường, tùy quyền truy cập/module policy. Vì vậy, **field private giúp encapsulation**, nhưng không nên quảng bá như “bí mật không thể đọc được từ mọi ngữ cảnh”.

## 27. Chọn lớp chứa nghiệp vụ: object hay service?

Không phải tất cả quy tắc đều phải nằm trong một entity:

- **Bên trong object**: invariant nội tại của nó, chẳng hạn Quantity phải dương, Account không cho rút vượt số dư trong mô hình đơn giản, Order không được chuyển từ CANCELED về DRAFT.
- **Trong value object**: kiểm tra và chuẩn hóa một đơn vị dữ liệu, ví dụ `EmailAddress`, `Money` hoặc `DateRange`.
- **Trong domain/application service**: quy tắc liên quan nhiều aggregate, repository, authorization, giao dịch hoặc dịch vụ ngoài.
- **Tại adapter/boundary**: parse JSON, xác minh input format và ánh xạ lỗi đến HTTP/UI.

Không nên “nhồi” dịch vụ gửi email hoặc kết nối database vào constructor chỉ để object tự quản lý toàn bộ cuộc sống của nó. Ngược lại, cũng không nên tạo entity chỉ có getter/setter rồi đưa **toàn bộ invariant cục bộ** ra service khiến state có thể sai giữa các lời gọi.

### Một mô hình phân trách nhiệm

~~~text
HTTP/UI/CLI input
       |
       v
Validation/Mapping boundary
       |
       v
Application service --------> Authorization / transaction
       |
       v
Domain object --------------> confirm(), cancel(), withdraw()
       |
       v
Private fields + invariants
~~~

Sơ đồ này mô tả các trách nhiệm có thể có, không phải quy định mọi chương trình Java nhỏ phải dùng nhiều tầng kiến trúc.

## 28. Kiểm thử API công khai thay vì field private

Một bài test tốt nên hỏi: “Với trạng thái và dữ liệu đầu vào này, **operation công khai** có kết quả/exception đúng không?” Không cần dùng reflection để đọc private field hoặc đổi modifier của field thành public chỉ để test.

Ví dụ: với Account có `deposit`, `withdraw`, `balanceCents()`, test cần bao gồm:

- Constructor cho phép số dư bằng 0.
- Constructor từ chối số dư âm.
- `deposit` với số dương tăng số dư đúng.
- `withdraw` trong hạn mức giảm đúng.
- `withdraw` vượt số dư ném lỗi và **giữ nguyên số dư**.
- `deposit` với số không dương ném lỗi.
- Phép cộng tràn ném lỗi và không làm thay đổi số dư.

### Chương trình kiểm thử độc lập không cần thư viện

Lưu file **`EncapsulationContractTestDemo.java`**:

~~~java
public class EncapsulationContractTestDemo {
    static final class Wallet {
        private long cents;

        Wallet(long cents) {
            if (cents < 0) {
                throw new IllegalArgumentException("negative balance");
            }
            this.cents = cents;
        }

        void deposit(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("invalid deposit");
            }
            cents = Math.addExact(cents, amount);
        }

        void withdraw(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("invalid withdrawal");
            }
            if (amount > cents) {
                throw new IllegalStateException("insufficient funds");
            }
            cents -= amount;
        }

        long balance() {
            return cents;
        }
    }

    static void assertEquals(long expected, long actual) {
        if (expected != actual) {
            throw new AssertionError(
                    "expected=" + expected + " actual=" + actual);
        }
    }

    static void expectInsufficient(Runnable operation) {
        try {
            operation.run();
        } catch (IllegalStateException expected) {
            System.out.println("insufficient funds rejected");
            return;
        }
        throw new AssertionError("Expected IllegalStateException");
    }

    public static void main(String[] args) {
        Wallet wallet = new Wallet(100);
        wallet.deposit(40);
        wallet.withdraw(15);
        assertEquals(125, wallet.balance());

        expectInsufficient(() -> wallet.withdraw(500));
        assertEquals(125, wallet.balance());

        System.out.println("Contract tests passed");
    }
}
~~~

~~~bash
javac -encoding UTF-8 EncapsulationContractTestDemo.java
java EncapsulationContractTestDemo
~~~

Stdout:

~~~text
insufficient funds rejected
Contract tests passed
~~~

Test này chỉ dùng constructor và methods, không truy cập private field. Nếu thay triển khai `Wallet` từ `long cents` sang một value object `Money` nhưng giữ public behavior tương đương, test có thể tiếp tục kiểm chứng hợp đồng. Đó là lợi ích của **implementation hiding**.

Trong dự án thực tế, JUnit với `assertThrows`, `assertEquals`, property-based tests và kiểm thử đa luồng có thể giúp bao quát nhiều trường hợp hơn. Không nhất thiết phải kiểm tra private fields bằng reflection.

## 29. Ví dụ hai file: bên ngoài không được sửa private field

Để nhìn trực tiếp compiler kiểm soát truy cập, tạo thư mục với hai file:

~~~text
private-lab/
├── Counter.java
└── CounterClient.java
~~~

**`Counter.java`**:

~~~java
public final class Counter {
    private int count;

    public void increment() {
        count = Math.addExact(count, 1);
    }

    public int value() {
        return count;
    }
}
~~~

**`CounterClient.java`**:

~~~java
public class CounterClient {
    public static void main(String[] args) {
        Counter counter = new Counter();
        counter.increment();
        counter.increment();

        System.out.println("count=" + counter.value());

        // counter.count = -5; // Lỗi compile: count là private.
    }
}
~~~

~~~bash
javac -encoding UTF-8 Counter.java CounterClient.java
java CounterClient
~~~

Stdout:

~~~text
count=2
~~~

Ở đây `CounterClient` là **top-level class khác** và không nằm trong cùng nest với `Counter`, nên `counter.count` không thể được truy cập trực tiếp, kể cả hai file ở cùng default package. Bỏ comment dòng lỗi rồi biên dịch sẽ bị từ chối.

**Chú ý Java 17 nested class:** Nếu đặt `Counter` là nested class bên trong `CounterClient`, các quy tắc private nestmate có thể cho phép mã outer truy cập private members. Vì vậy ví dụ dùng **hai top-level classes** để thể hiện đúng ranh giới private thông thường.

## 30. Lỗi phổ biến khi thiết kế private state

| Lỗi | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| Mọi field đều public | Caller tự sửa, phá invariant | Private field và API có chủ đích |
| Private field nhưng public setter vô điều kiện | Chỉ giấu cú pháp truy cập, không bảo vệ state | Validation hoặc domain command |
| Chỉ validate constructor, bỏ qua mutators | Object hợp lệ lúc tạo nhưng sai về sau | Kiểm tra invariant trên mọi đường cập nhật |
| Gán field trước rồi mới validate | Exception có thể để lại state hỏng | Validate/tính kết quả trước commit |
| Getter trả List/array mutable nội bộ | Caller sửa field qua alias | Snapshot/unmodifiable API/copy |
| Constructor giữ thẳng input mutable | Caller sửa ngoài, object thay đổi ngầm | Defensive copy khi cần |
| Chỉ dùng `final` để bảo vệ list | Final không ngăn list mutation | Immutable elements / copy / thiết kế ownership |
| Record chứa mutable component không copy | Record vẫn có state sâu mutable | Defensive copy hoặc contract rõ |
| Mọi getter đều bị cấm | Caller không thể quan sát dữ liệu cần thiết | Cho query an toàn |
| Mọi setter đều bị cấm | API phức tạp không cần thiết cho DTO/config | Dùng setter hợp lệ nếu nghiệp vụ cho phép |
| Toàn bộ logic ở service, entity chỉ getter/setter | Invariant cục bộ dễ bị bỏ qua | Đưa quy tắc nội tại về object |
| Toàn bộ I/O, giao dịch ở constructor | Khó rollback, test và tái sử dụng | Tách boundary/service |
| `private` bị coi là phân quyền | Không kiểm tra user/role thật | Authorization riêng |
| `private` bị coi là thread-safe | Race condition vẫn xảy ra | Đồng bộ, atomicity, immutable |
| Getter trả object mutable do caller cũng giữ | Aliasing gián tiếp làm state thay đổi | Copy hoặc chỉ expose operation |
| Overridable method gọi trong constructor | Subclass có thể chưa khởi tạo field | Tránh dispatch có thể override khi đang tạo |
| Test private field bằng reflection ở mọi nơi | Test phụ thuộc triển khai | Test public contract và invariant |
| Đổi access rộng hơn chỉ để compiler hết lỗi | Mở API quá mức và tăng coupling | Xác định đúng boundary và operation |

## 31. Một quy trình thiết kế class đóng gói tốt

**Bước 1 — Viết invariant.** Ví dụ giỏ hàng không chứa dòng quantity âm; đơn hàng đã hủy không được chuyển về draft; tài khoản không có số dư âm.

**Bước 2 — Đặt dữ liệu nội bộ vào private fields.** Chọn kiểu phù hợp; dùng `final` cho field không cần gán lại, nhưng đánh giá sự mutable của object được field tham chiếu.

**Bước 3 — Bảo vệ đường tạo object.** Constructor/factory validate đầu vào; chuẩn hóa và copy dữ liệu khi cần. Tránh xuất bản `this` trước khi khởi tạo hoàn tất.

**Bước 4 — Liệt kê hành vi mà caller thật sự cần.** Không mặc định sinh setter cho mỗi field. Ưu tiên các lệnh có tên thể hiện nghiệp vụ.

**Bước 5 — Tách query và command khi có giá trị.** Query trả dữ liệu an toàn; command xử lý thay đổi state và báo lỗi rõ ràng.

**Bước 6 — Giữ invariant trên mọi đường thất bại.** Kiểm tra trước commit; lưu ý overflow, side effects, concurrency và nhiều object.

**Bước 7 — Kiểm soát aliasing.** Không trả mảng/list mutable nội bộ, không giữ mutable input của caller nếu muốn ownership độc lập.

**Bước 8 — Thiết kế hợp đồng ngoại lệ.** Phân biệt dữ liệu đầu vào sai, thao tác không hợp lệ theo trạng thái hiện tại và lỗi hệ thống.

**Bước 9 — Test qua API.** Happy path, boundary, input sai, thứ tự gọi sai, giữ state sau exception, thay đổi input/snapshot ngoài object.

**Bước 10 — Xem lại nhu cầu mở rộng.** Package-private/protected/public chỉ dùng đúng khi các thành phần khác thực sự cần; cân nhắc độ ổn định của API.

## 32. Bài tập 1 — Sửa class chỉ có getter/setter

Đề bài:

~~~java
class BankAccount {
    private long balance;

    long getBalance() {
        return balance;
    }

    void setBalance(long balance) {
        this.balance = balance;
    }
}
~~~

Yêu cầu:

- Xây dựng constructor nhận số dư ban đầu không âm.
- Bỏ setter cho phép gán số dư tùy ý.
- Thêm `deposit(long amount)` và `withdraw(long amount)`.
- Với mọi amount phải dương; không cho rút vượt số dư.
- Không để phép cộng tràn âm thầm; dùng `Math.addExact` nơi phù hợp.
- Getter/query cho phép hiển thị số dư nhưng không sửa field.
- Test số dư không đổi sau thao tác bị từ chối.

**Gợi ý:** Xem `BankAccountEncapsulationDemo`; điểm chính là **giữ invariant ở chính class** chứ không chỉ chuyển field từ public sang private.

## 33. Bài tập 2 — Trạng thái đơn hàng

Đề bài có `status` nhận `DRAFT`, `CONFIRMED`, `SHIPPED`, `CANCELED`. Hãy thiết kế:

- `confirm()` chỉ hợp lệ khi DRAFT.
- `ship()` chỉ hợp lệ khi CONFIRMED.
- `cancel()` hợp lệ ở những trạng thái được nghiệp vụ cho phép, không cho sau khi SHIPPED.
- Không có public `setStatus(State)` vô điều kiện.
- Query `status()` chỉ đọc.
- Test mọi chuyển trạng thái hợp lệ và không hợp lệ.

Việc thiết kế **state transition table** trước khi viết code giúp không bỏ sót một đường cập nhật.

## 34. Bài tập 3 — Bảo vệ private mảng

Cho class lưu điểm:

~~~java
class Report {
    private int[] scores;

    Report(int[] scores) {
        this.scores = scores;
    }

    int[] getScores() {
        return scores;
    }
}
~~~

Yêu cầu:

- Reject null và mảng rỗng nếu domain yêu cầu có điểm.
- Từng điểm thuộc `0..100`.
- Copy mảng ở constructor và khi trả ra.
- Thêm method query `average()` với quy tắc làm tròn được nói rõ.
- Chứng minh sửa mảng input hoặc snapshot không sửa state Report.
- Giải thích vì sao `private` và `final` mà **không copy** vẫn chưa đủ.

## 35. Bài tập 4 — Thao tác thay vì setter đại trà

Một `InventoryItem` có private `stock` và private `reserved`. Invariant:

~~~text
stock >= 0
reserved >= 0
reserved <= stock
~~~

Hãy thiết kế những method như `restock(int quantity)`, `reserve(int quantity)`, `releaseReservation(int quantity)` và `fulfillReservation(int quantity)` với quy tắc cụ thể. Không cho caller đặt `stock` hay `reserved` bằng số tùy ý.

**Gợi ý:** `fulfillReservation` có thể cần giảm **cả stock và reserved** trong một operation. Hãy tính các giá trị mới và kiểm tra trước khi gán để tránh cập nhật nửa chừng.

## 36. Bài tập 5 — Public API của class chứa list

Một class `Course` có private `List<Student> students` và trả nguyên list từ `students()`. Hãy chọn một thiết kế:

1. Chỉ đọc danh sách; trả unmodifiable snapshot phù hợp.
2. Có thể ghi danh: thêm `enroll(Student)`, từ chối null/trùng lặp theo identity hoặc business ID được định nghĩa.
3. Có thể hủy ghi danh: thêm `unenroll(Student)` với chính sách không tồn tại rõ ràng.
4. Nếu `Student` mutable, phân tích việc `List.copyOf` **không** bảo vệ các field bên trong Student.

Mục tiêu không phải “dùng `List.copyOf` là xong” mà là **định nghĩa ai có quyền thay đổi phần nào của object graph**.

## 37. Câu hỏi thường gặp

### 37.1. Nếu field private, object khác cùng class có đọc được không?

Có, trong code của chính class khai báo, ví dụ `this.balance == other.balance` có thể đọc private field trên `other`. Quy tắc truy cập private dựa trên **ngữ cảnh class/nest**, không chỉ receiver `this`.

### 37.2. Một class cùng package có đọc được private field không?

Không chỉ vì cùng package. Package-private field mới mở cho class khác cùng package theo quy tắc bình thường; `private` khác với package-private.

### 37.3. Phải tạo getter và setter cho tất cả private fields?

Không. API nên phản ánh **những dữ liệu cần quan sát** và **những hành vi hợp lệ**. Không phải field nào cũng nên có setter. Getter trả object mutable cũng cần xem xét.

### 37.4. Setter có validation là đủ chưa?

Có thể đủ cho một thuộc tính đơn lẻ; nhưng nếu có invariant **liên quan nhiều field** hoặc phụ thuộc trạng thái, các setter riêng có thể cho phép trạng thái trung gian sai. Một method có ý nghĩa cập nhật nhất quán nhiều field thường thích hợp hơn.

### 37.5. `private final List<T>` có bất biến không?

Không tự động. `final` giữ field reference không bị gán lại; List object vẫn có thể mutable, và các phần tử T có thể mutable. Cần thêm thiết kế ownership, copy và API không sửa phù hợp.

### 37.6. Trả `Collections.unmodifiableList(list)` có giống copy không?

Không hoàn toàn. **Unmodifiable view** có thể phản ánh những thay đổi của backing list nếu backing list được sửa qua reference khác. `List.copyOf(list)` tạo/nhận một unmodifiable list với cấu trúc không phụ thuộc việc sửa ArrayList nguồn theo cách trong ví dụ, nhưng không deep copy element objects. Chọn theo yêu cầu snapshot hay live view.

### 37.7. `private` có bảo vệ khỏi nhiều thread cùng sửa field không?

Không. Các thread vẫn có thể gọi public methods trên cùng object. Cần cơ chế concurrency riêng.

### 37.8. Có nên để business logic vào constructor?

Constructor nên bảo đảm trạng thái tạo thành công hợp lệ. Các hoạt động nhiều bước, I/O, transaction hoặc giao dịch bên ngoài thường thích hợp hơn ở method/factory/service có hợp đồng rõ và quản lý vòng đời tài nguyên tốt.

### 37.9. Có nên luôn dùng immutable object?

Immutable object rất hữu ích cho nhiều kiểu giá trị (Money, DateRange, Address bất biến), nhưng không phải mọi domain object đều cần bất biến. Giỏ hàng, đơn hàng hoặc tài khoản có thể cần thay đổi state qua command methods được kiểm soát.

### 37.10. Dùng reflection để test private field có nên không?

Có thể có tình huống rất đặc thù, nhưng test hành vi thông thường nên kiểm tra **public contract** và invariant quan sát được. Lạm dụng reflection khiến test phụ thuộc chi tiết triển khai và giảm tự do refactor.

## 38. Checklist cuối bài

- [ ] Tôi phân biệt được **ẩn field** với **bảo vệ invariant**.
- [ ] Tôi hiểu `private` giới hạn direct access nhưng không tự làm object immutable.
- [ ] Tôi biết tại sao public setter tùy ý có thể phá đóng gói.
- [ ] Tôi biết đặt tên method theo hành vi: `deposit`, `withdraw`, `confirm`, `cancel`.
- [ ] Tôi chọn được getter/query khi caller thực sự cần quan sát state.
- [ ] Tôi biết constructor phải validate trạng thái ban đầu.
- [ ] Tôi bảo toàn invariant trong tất cả đường cập nhật bình thường và thất bại.
- [ ] Tôi dùng exception theo hợp đồng và không mặc định exception tự rollback field.
- [ ] Tôi biết xử lý tràn số trước khi gán giá trị mới.
- [ ] Tôi không trả nguyên mảng/list mutable nội bộ qua getter nếu cần bảo vệ state.
- [ ] Tôi biết khi nào cần defensive copy đầu vào và đầu ra.
- [ ] Tôi phân biệt shallow copy, deep copy và unmodifiable view.
- [ ] Tôi hiểu `final` reference khác immutable object.
- [ ] Tôi biết record có thể cần validate/copy mutable components.
- [ ] Tôi hiểu subclass không được tự truy cập private field của superclass.
- [ ] Tôi biết `private` không tự bảo đảm thread-safety hay authorization.
- [ ] Tôi biết khi nào domain service/transaction phối hợp nhiều object là cần thiết.
- [ ] Tôi có thể viết test cho public behavior, invalid state transition và failure path.
- [ ] Tôi tự biên dịch, chạy và giải thích các chương trình Java 17+ trong bài.

**Kết luận:** Đóng gói hiệu quả không phải là “biến mọi field thành private rồi sinh toàn bộ getter/setter”, mà là **cho object tự chịu trách nhiệm giữ trạng thái hợp lệ**. Dùng `private` để ẩn chi tiết cài đặt; đưa những thay đổi hợp lệ vào các phương thức mô tả hành vi; chỉ cho caller đọc thông tin cần thiết mà không làm lộ mutable state. Một API nhỏ, rõ nghĩa và giữ invariant giúp chương trình dễ kiểm thử, dễ thay đổi cấu trúc bên trong và giảm lỗi do mã bên ngoài sửa object sai cách.
