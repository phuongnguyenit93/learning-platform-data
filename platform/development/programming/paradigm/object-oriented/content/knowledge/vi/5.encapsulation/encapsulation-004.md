# Getter, setter và phương thức thể hiện ý định trong Java

Trong lập trình hướng đối tượng, **đóng gói (encapsulation)** là cách một đối tượng kiểm soát việc bên ngoài đọc và thay đổi trạng thái của nó. Thay vì cho mọi nơi tùy ý sửa field, lớp cung cấp một **giao diện công khai (public API)** với những thao tác có ý nghĩa.

Ba công cụ thường gặp:

- **Getter:** trả về thông tin mà người gọi được phép đọc, chẳng hạn `getBalance()` hoặc `isActive()`.
- **Setter:** thay đổi một thuộc tính theo một hợp đồng đã xác định, chẳng hạn `setDisplayName(...)`.
- **Phương thức thể hiện ý định:** mô tả *hành động nghiệp vụ* mà người gọi muốn làm, chẳng hạn `deposit(...)`, `withdraw(...)`, `confirm()`, `cancel()` hoặc `reschedule(...)`.

Điểm quan trọng là **không phải cứ khai báo field `private` rồi tạo getter/setter cho mọi field là đã thiết kế đóng gói tốt**. Đóng gói tốt bảo vệ các *bất biến (invariant)* của đối tượng: những điều kiện phải luôn đúng sau khi đối tượng được tạo và sau mỗi thao tác thành công.

Ví dụ, tài khoản ngân hàng không nên cho gọi `setBalance(-500)` hay `setBalance(999999)` từ bất kỳ đâu. API `deposit()` và `withdraw()` diễn tả rõ mục đích và là nơi kiểm tra điều kiện hợp lệ.

## 1. Phân biệt getter, setter và phương thức có ý nghĩa nghiệp vụ

| Thành phần | Mục đích | Ví dụ | Điều cần cân nhắc |
|---|---|---|---|
| Getter | Cho phép quan sát thông tin | `getName()`, `getBalance()` | Giá trị trả về có làm lộ dữ liệu có thể sửa không? |
| Setter | Cho phép gán/đổi một thuộc tính | `setNickname("An")` | Giá trị mới có cần được xác thực? |
| Phương thức thể hiện ý định | Thực hiện một hành động có quy tắc | `withdraw(500)`, `confirm()` | Điều kiện trước/sau của hành động là gì? |
| Constructor/factory | Tạo đối tượng ở trạng thái hợp lệ | `new Account("A01")` | Có bắt buộc dữ liệu nào ngay từ đầu? |
| Phương thức truy vấn suy ra | Trả lời câu hỏi từ trạng thái hiện có | `hasEnoughBalance(500)` | Có cần lưu thêm một field hay tính khi được hỏi? |

Một tên phương thức diễn tả ý định giúp code gọi tự đọc được:

~~~java
account.deposit(200_000);
account.withdraw(75_000);
~~~

So sánh với cách gọi không nêu rõ nghiệp vụ:

~~~java
account.setBalance(account.getBalance() + 200_000);
account.setBalance(account.getBalance() - 75_000);
~~~

Ở cách dùng setter, người gọi tự quyết định công thức, điều kiện hợp lệ và cách thay đổi tiền. Mỗi nơi có thể tính khác nhau, dẫn tới lỗi âm số dư, bỏ qua phí hoặc cập nhật sai khi nhiều thao tác cùng lúc.

## 2. Vì sao một lớp có toàn getter/setter vẫn có thể đóng gói kém?

Giả sử có lớp đơn hàng:

~~~java
public class Order {
    private String status;
    private int itemCount;

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public int getItemCount() {
        return itemCount;
    }

    public void setItemCount(int itemCount) {
        this.itemCount = itemCount;
    }
}
~~~

Code bên ngoài có thể tạo những trạng thái không hợp lệ:

~~~java
Order order = new Order();
order.setItemCount(-3);
order.setStatus("CONFIRMED");  // Có thể xác nhận đơn hàng âm số lượng.
order.setStatus("UNKNOWN");    // Không có trạng thái nghiệp vụ tương ứng.
~~~

Field vẫn `private`, nhưng mọi quy tắc đã bị chuyển sang người gọi. Getter/setter dạng này gần giống truy cập field công khai, chỉ khác cú pháp.

Các vấn đề có thể phát sinh:

1. Không có nơi thống nhất kiểm tra giá trị đầu vào.
2. Setter cho phép thay đổi trạng thái ở bất kỳ thời điểm nào, kể cả khi thao tác không hợp lệ.
3. Hai thuộc tính phụ thuộc lẫn nhau có thể tạm thời rơi vào trạng thái mâu thuẫn.
4. Tên `setStatus("CONFIRMED")` không nói vì sao chuyển trạng thái, ai được phép chuyển, hay cần điều kiện gì.
5. Nếu nghiệp vụ đổi, rất khó tìm hết nơi đang sử dụng setter để bổ sung logic.

**Giải pháp không phải cấm mọi setter.** Setter vẫn phù hợp khi một thuộc tính thật sự được phép đổi độc lập và việc đổi đó không làm phá vỡ invariant của đối tượng. Vấn đề là chọn đúng quyền thay đổi và hợp đồng API.

## 3. Ví dụ hoàn chỉnh: getter để đọc, hành vi để kiểm soát trạng thái

Ví dụ này triển khai tài khoản ngân hàng đơn giản. Để tập trung vào nguyên tắc OOP, số tiền được biểu diễn bằng **`long` theo đơn vị đồng**, không dùng số thực để cộng trừ tiền. Chương trình không xử lý ngân hàng thật, giao dịch phân tán hoặc cập nhật đồng thời.

Lưu thành **`Demo.java`** (Java 17+):

~~~java
public class Demo {
    public static void main(String[] args) {
        BankAccount account = new BankAccount("A-101", "Lan");

        account.deposit(500_000);
        account.withdraw(125_000);
        account.renameOwner("Lan Nguyễn");

        System.out.println("Tài khoản: " + account.getAccountNumber());
        System.out.println("Chủ tài khoản: " + account.getOwnerName());
        System.out.println("Số dư: " + account.getBalance());
        System.out.println("Đủ tiền trả 400000? "
                + account.hasEnoughBalance(400_000));

        try {
            account.withdraw(500_000);
        } catch (IllegalStateException ex) {
            System.out.println("Bị từ chối: " + ex.getMessage());
        }

        try {
            account.close();
        } catch (IllegalStateException ex) {
            System.out.println("Không thể đóng: " + ex.getMessage());
        }
        account.withdraw(account.getBalance());
        account.close();
        System.out.println("Đã đóng: " + account.isClosed());
    }
}

final class BankAccount {
    private final String accountNumber;
    private String ownerName;
    private long balance;
    private boolean closed;

    public BankAccount(String accountNumber, String ownerName) {
        this.accountNumber = requireText(
                accountNumber, "Mã tài khoản");
        this.ownerName = requireText(ownerName, "Tên chủ");
        this.balance = 0;
        this.closed = false;
    }

    // Getter: quan sát trạng thái, không tự thay đổi tài khoản.
    public String getAccountNumber() {
        return accountNumber;
    }

    public String getOwnerName() {
        return ownerName;
    }

    public long getBalance() {
        return balance;
    }

    public boolean isClosed() {
        return closed;
    }

    public boolean hasEnoughBalance(long amount) {
        return amount > 0 && !closed && balance >= amount;
    }

    // Hành vi: nạp tiền theo quy tắc.
    public void deposit(long amount) {
        requireOpen();
        requirePositive(amount);
        balance = Math.addExact(balance, amount);
    }

    // Hành vi: chỉ trừ khi đủ tiền.
    public void withdraw(long amount) {
        requireOpen();
        requirePositive(amount);

        if (amount > balance) {
            throw new IllegalStateException("Không đủ số dư");
        }

        balance -= amount;
    }

    // Hành vi: đổi tên và duy trì điều kiện tên hợp lệ.
    public void renameOwner(String newName) {
        requireOpen();
        ownerName = requireText(newName, "Tên chủ");
    }

    // Hành vi: chuyển trạng thái sang đã đóng.
    public void close() {
        requireOpen();
        if (balance != 0) {
            throw new IllegalStateException(
                    "Phải tất toán số dư trước khi đóng");
        }
        closed = true;
    }

    private void requireOpen() {
        if (closed) {
            throw new IllegalStateException(
                    "Tài khoản đã đóng");
        }
    }

    private static void requirePositive(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException(
                    "Số tiền phải lớn hơn 0");
        }
    }

    private static String requireText(
            String value, String fieldName) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    fieldName + " không được để trống");
        }
        return value.strip();
    }
}
~~~

Chạy:

~~~bash
javac Demo.java
java Demo
~~~

Kết quả:

~~~text
Tài khoản: A-101
Chủ tài khoản: Lan Nguyễn
Số dư: 375000
Đủ tiền trả 400000? false
Bị từ chối: Không đủ số dư
Không thể đóng: Phải tất toán số dư trước khi đóng
Đã đóng: true
~~~

Dòng `Không thể đóng` minh họa quy tắc tài khoản còn 375.000 đồng thì `close()` từ chối **trước khi đổi trạng thái**. Sau đó chương trình rút hết số dư, đóng tài khoản thành công và in `Đã đóng: true`. Như vậy cùng một lần chạy kiểm chứng được cả đường từ chối lẫn đường thành công.

Ví dụ này thể hiện ba điểm:

- **Getter** chỉ cho phép đọc dữ liệu mà lớp quyết định công khai. Không có `setAccountNumber()`, bởi vì mã tài khoản không được phép đổi trong vòng đời đối tượng.
- **Phương thức thể hiện ý định** như `deposit()`, `withdraw()`, `renameOwner()`, `close()` kiểm soát những thay đổi hợp lệ. Ví dụ `withdraw()` kiểm tra số tiền và số dư *trước* khi trừ; trường hợp thiếu tiền không làm thay đổi trạng thái.
- **Invariant** như `balance >= 0` và “không được giao dịch sau khi đóng” được tập trung kiểm tra trong lớp. `Math.addExact()` cũng tránh lỗi tràn `long` âm thầm khi cộng tiền.

> Trong phần mềm tài chính thực tế, một đối tượng trong bộ nhớ chưa bảo đảm giao dịch an toàn khi nhiều luồng hoặc nhiều máy chủ truy cập. Việc kiểm tra số dư, ghi nhận giao dịch và chống cập nhật trùng phải được thiết kế ở tầng lưu trữ/giao dịch phù hợp.

### Sơ đồ quyền điều khiển trạng thái

~~~mermaid
flowchart LR
    U["Code bên ngoài"] --> G["Getter<br/>getBalance()"]
    G --> R["Quan sát số dư"]
    U --> D["Hành vi<br/>withdraw(amount)"]
    D --> V{"Kiểm tra điều kiện"}
    V -->|Hợp lệ| S["Thay đổi field private"]
    V -->|Không hợp lệ| E["Báo lỗi, giữ nguyên trạng thái"]
    X["setBalance(value)"] -.->|"Không cung cấp"| S
~~~

Code bên ngoài chỉ đề nghị một **hành động**; lớp quyết định liệu hành động có được phép và cập nhật dữ liệu nội bộ ra sao. Nhờ đó, khi điều kiện nghiệp vụ thay đổi, chỉ cần điều chỉnh hành vi ở nơi sở hữu trạng thái.

## 4. Getter không nhất thiết trả về field nguyên xi

Getter có thể trả về:

- Một **field** có thể quan sát an toàn.
- Giá trị **được tính toán** từ các field khác.
- Một **bản sao** hoặc dạng đọc được của trạng thái.
- Một kiểu biểu diễn rõ sự vắng mặt của dữ liệu.

Ví dụ, không cần lưu thêm `itemCount` nếu có thể tính từ danh sách:

~~~java
import java.util.ArrayList;
import java.util.List;

class ShoppingCart {
    private final List<String> items = new ArrayList<>();

    public int getItemCount() {
        return items.size();
    }

    public boolean isEmpty() {
        return items.isEmpty();
    }

    public void addItem(String item) {
        if (item == null || item.isBlank()) {
            throw new IllegalArgumentException(
                    "Tên sản phẩm không hợp lệ");
        }
        items.add(item);
    }
}
~~~

`getItemCount()` là một **phương thức truy vấn**, không cần có field `itemCount`. Cách tính trực tiếp tránh phải đồng bộ hai giá trị `items.size()` và `itemCount` sau mỗi lần thêm/xóa.

Một getter mang tên `getTotalPrice()` cũng có thể tính từ các mặt hàng, miễn là hợp đồng rõ ràng. Tuy nhiên, getter có truy vấn mạng/database tốn thời gian hoặc thay đổi trạng thái đáng kể có thể gây bất ngờ: nên đặt tên rõ ý định, chẳng hạn `fetchLatestPrice()` hoặc `refreshCache()`, nếu thao tác thực sự làm việc đó.

### Không phải dữ liệu nội bộ nào cũng cần getter

Ngay cả khi chỉ cho đọc, việc công khai toàn bộ dữ liệu nội bộ làm tăng sự phụ thuộc của code bên ngoài vào cấu trúc lớp. Nếu code ngoài chỉ cần biết “đơn hàng có thể thanh toán chưa?”, một API `canCheckout()` thường rõ ý nghĩa hơn việc yêu cầu người gọi lấy `status`, `items`, `shippingAddress` rồi tự kiểm tra cùng một quy tắc ở nhiều nơi.

Tuy vậy, các màn hình hiển thị, công cụ báo cáo và hệ thống serialization vẫn cần một số dữ liệu đọc được; getter là công cụ phù hợp khi thông tin đó thực sự thuộc giao diện lớp.

## 5. Getter trả tham chiếu mutable phải có hợp đồng rõ ràng

Một getter có thể làm lộ trạng thái dù field là `private`:

```java
class UnsafeBasket {
    private final java.util.List<String> items =
            new java.util.ArrayList<>();

    public java.util.List<String> getItems() {
        return items; // Caller có thể gọi getItems().add("")
    }
}
```

Nếu lớp yêu cầu mỗi tên mặt hàng không rỗng, caller gọi `getItems().add("")` sẽ bỏ qua mọi kiểm tra của `addItem()`. Với `List<String>`, getter có thể dùng `List.copyOf(items)` để trả snapshot cấu trúc không sửa được; `String` bất biến nên an toàn để chia sẻ phần tử.

Chọn cách trả theo nhu cầu: `Collections.unmodifiableList(items)` là view chỉ đọc nhưng phản ánh thay đổi từ list gốc; `List.copyOf(items)` là snapshot cấu trúc; `new ArrayList<>(items)` là bản sao caller có thể sửa riêng. **Cả ba đều không tự deep-copy phần tử mutable**. Nếu getter trả mảng, `Date` hoặc đối tượng con có setter, cần bảo vệ tham chiếu sâu hơn.

## 6. Setter thích hợp trong trường hợp nào?

Một setter có thể phù hợp khi:

1. Thuộc tính thực sự được phép thay đổi độc lập.
2. Cập nhật chỉ có một ý nghĩa rõ ràng.
3. Có thể kiểm tra giá trị hợp lệ ngay trong setter.
4. Không làm đối tượng rơi vào trạng thái sai hoặc mở ra thao tác bị cấm theo vòng đời.

Ví dụ người dùng đổi tên hiển thị:

~~~java
public final class Profile {
    private String displayName;

    public Profile(String displayName) {
        setDisplayName(displayName);
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        if (displayName == null || displayName.isBlank()) {
            throw new IllegalArgumentException(
                    "Tên hiển thị không được trống");
        }
        this.displayName = displayName.strip();
    }
}
~~~

Ở đây `setDisplayName()` phù hợp vì đổi tên hiển thị là một cập nhật độc lập, quy tắc giá trị được kiểm soát tại cùng một điểm. Không có nghĩa setter phải cho phép mọi giá trị truyền vào.

Tùy ngữ cảnh nghiệp vụ, một tên `renameTo(...)` hoặc `changeDisplayName(...)` cũng có thể truyền đạt ý định tốt hơn, nhất là khi đổi tên cần kiểm tra quyền, lưu lịch sử hoặc phát sinh sự kiện.

### Setter không nhất thiết là public

Java cho phép:

~~~java
class Task {
    private String title;

    public String getTitle() {
        return title;
    }

    private void setTitle(String title) {
        this.title = title;
    }
}
~~~

`private` setter có thể chỉ dùng nội bộ lớp. Ngoài ra có thể dùng package-private hoặc `protected` khi có nhu cầu thiết kế cụ thể. **Không có quy tắc bắt buộc getter và setter phải cùng mức truy cập**, hay cứ có getter thì phải có setter.

Với đối tượng bất biến (immutable), ta thường không cung cấp setter:

~~~java
public record Coordinates(int latitude, int longitude) {}
~~~

`record` này là ví dụ cú pháp về một kiểu dữ liệu mang giá trị; component accessor có tên `latitude()` và `longitude()`, không phải `getLatitude()`. Mọi field component là final; nhưng record chứa tham chiếu tới dữ liệu mutable vẫn cần thiết kế bảo vệ sâu thêm nếu muốn bất biến thực sự.

## 7. Khi nhiều field phụ thuộc nhau, dùng một hành vi nguyên khối

Giả sử lịch đặt phòng có `start` và `end`. Cho gọi hai setter độc lập có thể tạo trạng thái trung gian sai:

~~~java
booking.setStart(newStart);
booking.setEnd(newEnd);
~~~

Nếu `newStart` đến sau `end` cũ, setter thứ nhất có thể khiến lịch không hợp lệ dù cặp giờ mới là hợp lệ. Nếu setter nào cũng tự kiểm tra toàn bộ invariant, cách cập nhật lần lượt có thể không thực hiện được.

API mang ý định cho phép kiểm tra hai thông số **cùng lúc**:

~~~java
import java.time.LocalDateTime;
import java.util.Objects;

public final class Booking {
    private LocalDateTime start;
    private LocalDateTime end;

    public Booking(LocalDateTime start, LocalDateTime end) {
        reschedule(start, end);
    }

    public LocalDateTime getStart() {
        return start;
    }

    public LocalDateTime getEnd() {
        return end;
    }

    public void reschedule(
            LocalDateTime newStart, LocalDateTime newEnd) {
        Objects.requireNonNull(newStart, "start");
        Objects.requireNonNull(newEnd, "end");

        if (!newStart.isBefore(newEnd)) {
            throw new IllegalArgumentException(
                    "Giờ bắt đầu phải trước giờ kết thúc");
        }

        // Chỉ cập nhật sau khi đã kiểm tra toàn bộ đầu vào.
        this.start = newStart;
        this.end = newEnd;
    }
}
~~~

Ví dụ này bảo vệ invariant theo luồng thực thi tuần tự. Nếu nhiều luồng đồng thời đọc/sửa `Booking`, cần có chiến lược đồng bộ hoặc tính bất biến thích hợp để không quan sát cặp giá trị cập nhật dở dang.

Ưu điểm của `reschedule(start, end)`:

- API thể hiện rõ nghiệp vụ **đổi lịch**.
- Kiểm tra tính hợp lệ của cả hai tham số trước khi sửa.
- Người gọi không cần biết thứ tự gán từng field.
- Sau này có thể thêm điều kiện “không được đổi lịch khi đã hoàn thành” ở cùng một hành vi.

## 8. Đặt tên theo chuyển trạng thái hợp lệ

Khi đối tượng có vòng đời, tránh `setStatus(anyValue)`. API như `confirm()`, `ship(trackingCode)`, `cancel()` cho biết **hành động** đang được yêu cầu và là nơi kiểm tra trạng thái hiện tại. Ví dụ một đơn nháp chỉ xác nhận được khi có dòng hàng; một đơn đã hủy không tự quay lại trạng thái mới nếu quy trình không cho phép.

```java
// Bên trong lớp Order, với enum Status { DRAFT, CONFIRMED, CANCELLED }.
public void confirm() {
    if (status != Status.DRAFT || itemCount <= 0) {
        throw new IllegalStateException("Đơn chưa thể xác nhận");
    }
    status = Status.CONFIRMED;
}
```

Điểm khác với setter là **người gọi không chọn đích chuyển trạng thái tùy ý**. Tính idempotent (ví dụ gọi `cancel()` lần hai nên được chấp nhận hay từ chối) phải do hợp đồng nghiệp vụ quyết định; tên hành động không tự trả lời câu hỏi đó.

## 9. Getter và setter có nhất thiết “đơn giản” không?

Một getter thường nên có ý nghĩa **quan sát**, dễ dự đoán và không gây thay đổi nghiệp vụ bất ngờ. Setter có thể kiểm tra, chuẩn hóa dữ liệu, hoặc cập nhật thuộc tính khác khi thực sự cần duy trì invariant. Tuy nhiên, đặt các hành vi lớn hoặc tác dụng phụ khó thấy trong `setX()` có thể gây khó hiểu:

~~~java
// Dễ gây bất ngờ nếu setter này âm thầm gửi email,
// trừ tiền, gọi API ngoài hoặc phát sự kiện nghiệp vụ.
customer.setEmail("new@example.com");
~~~

Nếu đổi email phải trải qua xác minh, hãy thể hiện quy trình bằng các hành vi cụ thể:

~~~java
customer.requestEmailChange("new@example.com");
// Sau khi nhận và xác minh mã:
// customer.confirmEmailChange(verificationCode);
~~~

Các tên trên chỉ minh họa thiết kế API: để chạy được phải có cài đặt lớp, quy trình xác minh và dữ liệu liên quan. Điểm thiết kế là **người đọc code hiểu điều gì đang được yêu cầu**, đồng thời các quy tắc quan trọng tập trung trong object hoặc service chịu trách nhiệm.

### Tách command và query theo ý nghĩa

- **Query:** `getBalance()`, `isClosed()`, `canWithdraw(amount)` — cung cấp thông tin.
- **Command:** `deposit(amount)`, `close()`, `renameOwner(name)` — yêu cầu thay đổi trạng thái.

Phân biệt này là hướng dẫn thiết kế hữu ích, không phải quy tắc cú pháp bắt buộc của Java. Nếu query phải tính toán tốn kém, cache hoặc truy cập hệ thống bên ngoài, hợp đồng và tên phương thức nên giúp người gọi dự đoán chi phí.

Cũng đừng dựa hoàn toàn vào `canWithdraw()` rồi mới gọi `withdraw()` trong mã đa luồng: trạng thái có thể thay đổi giữa hai lần gọi (*time-of-check to time-of-use*). Chính lệnh `withdraw()` vẫn phải kiểm tra điều kiện tại thời điểm cập nhật.

## 10. Getter/setter theo JavaBeans và nhu cầu framework

JavaBeans là một quy ước phổ biến cho tên accessor:

~~~java
public class PersonBean {
    private String name;
    private boolean active;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public boolean isActive() {
        return active;
    }

    public void setActive(boolean active) {
        this.active = active;
    }
}
~~~

Theo quy ước thường thấy, `getName()/setName()` ứng với property `name`, `isActive()/setActive()` ứng với boolean property `active`. Đây là **quy ước đặt tên/khám phá property** chứ không phải cú pháp đặc biệt. Java vẫn cho phép phương thức tên khác.

Một số thư viện/framework (như công cụ bean introspection, binding dữ liệu, serialization hoặc ORM) có thể dựa trên getter, setter, field access, constructor, record hoặc annotation tùy phiên bản/cấu hình. Vì vậy:

- Kiểm tra **hợp đồng thật** của framework trước khi mở thêm setter chỉ để “cho framework chạy”.
- Không tự động kết luận mọi domain entity cần public setter cho tất cả field.
- Nếu framework cần tạo object và gán field, có thể tách **DTO/binding model** với **domain model** thay vì làm lộ toàn bộ hành vi sửa trạng thái của domain.
- Validation ở ranh giới API (ví dụ DTO) vẫn không thay thế các invariant phải luôn được bảo vệ bên trong domain object.

### DTO có thể đơn giản, domain object cần luật

**DTO (Data Transfer Object)** dùng để chở dữ liệu qua lớp ứng dụng hoặc qua mạng. Nếu DTO chỉ chứa dữ liệu đầu vào/đầu ra, các accessor hoặc record thường đủ:

~~~java
public record ChangeDisplayNameRequest(String displayName) {}
~~~

Tầng xử lý phải kiểm tra và dùng hành vi trên domain model:

~~~java
// Ví dụ minh họa trong ứng dụng có User và UserRepository:
ChangeDisplayNameRequest request =
        new ChangeDisplayNameRequest("Minh");

user.changeDisplayName(request.displayName());
repository.save(user);
~~~

Hai dòng cuối phụ thuộc vào `user`, `repository` và lớp được định nghĩa trong dự án thật. Mục đích là phân biệt **dữ liệu được yêu cầu** với **hành động được phép trên domain object**.

## 11. Không lộ dữ liệu nhạy cảm qua getter

Việc một field `private` không có nghĩa nó nên được công khai bằng getter.

Ví dụ:

~~~java
final class UserCredentials {
    private final String passwordHash;

    UserCredentials(String passwordHash) {
        this.passwordHash =
                java.util.Objects.requireNonNull(passwordHash);
    }

    // Không tự tạo public getPasswordHash()
    // nếu bên ngoài không có nhu cầu hợp lệ để biết giá trị.
}
~~~

Nếu có dữ liệu phải dùng cho logic xác thực, cung cấp một phương thức hoặc dịch vụ thích hợp cho thao tác xác thực thay vì bộc lộ dữ liệu nội bộ tùy tiện. Mức truy cập là một phần của thiết kế an toàn, nhưng an toàn thực tế còn phụ thuộc xử lý dữ liệu nhạy cảm, kiểm soát quyền và cơ chế xác thực.

Cùng nguyên tắc áp dụng với token, khóa bí mật, dữ liệu cá nhân và thông tin triển khai nội bộ.

## 12. Setter và đối tượng bất biến

Không phải mọi object đều cần thay đổi trạng thái sau khi tạo. Với kiểu dữ liệu biểu diễn giá trị, **immutable object** có nhiều lợi ích: dễ suy luận, dễ dùng làm value object, giảm rủi ro bị sửa từ nơi khác.

~~~java
import java.util.Objects;

public record Money(String currency, long minorUnits) {
    public Money {
        Objects.requireNonNull(currency, "currency");
        if (currency.isBlank()) {
            throw new IllegalArgumentException("Thiếu đơn vị tiền");
        }
        if (minorUnits < 0) {
            throw new IllegalArgumentException("Giá trị âm");
        }
    }

    public Money plus(Money other) {
        Objects.requireNonNull(other, "other");
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                    "Không thể cộng khác đơn vị tiền");
        }
        return new Money(currency,
                Math.addExact(minorUnits, other.minorUnits));
    }
}
~~~

`Money` này không có setter. `plus()` trả về **giá trị mới**, không sửa đối tượng hiện có:

~~~java
Money price = new Money("VND", 50_000);
Money fee = new Money("VND", 5_000);
Money total = price.plus(fee);

System.out.println(price.minorUnits()); // 50000
System.out.println(total.minorUnits()); // 55000
~~~

`minorUnits` là đơn vị tiền nhỏ nhất do hệ thống quy định; ví dụ dùng VND minh họa. Trong ứng dụng đa tiền tệ, cần quy ước rõ quy mô tiền tệ, làm tròn, giới hạn nghiệp vụ và xử lý số âm tùy loại giao dịch.

Một hành vi có ý nghĩa không nhất thiết phải **thay đổi** trạng thái của object; nó có thể trả về object mới như `plus()`.

## 13. Chọn thiết kế theo nhu cầu

| Nhu cầu | API thường phù hợp | Vì sao |
|---|---|---|
| Đọc tên chủ tài khoản | `getOwnerName()` | Chỉ cần quan sát |
| Đổi nickname cho phép tự do trong giới hạn | `setNickname(...)` hoặc `renameTo(...)` | Một thuộc tính, có validation |
| Cộng tiền vào tài khoản | `deposit(amount)` | Bảo vệ quy tắc và số dư |
| Trừ tiền | `withdraw(amount)` | Kiểm tra số dư/điều kiện giao dịch |
| Chuyển trạng thái đơn hàng | `confirm()`, `cancel()` | Ngăn chuyển trạng thái trái phép |
| Đổi hai thời điểm phụ thuộc nhau | `reschedule(start, end)` | Kiểm tra trọn cặp dữ liệu |
| Lấy danh sách mặt hàng | `getItems()` trả snapshot/read-only | Không làm lộ collection nội bộ |
| Đọc số lượng phần tử | `getItemCount()` | Có thể tính, không cần field dư thừa |
| Value object bất biến | Constructor + accessor + phương thức tạo giá trị mới | Không có lý do sửa tại chỗ |
| Truyền dữ liệu qua API | DTO/record hoặc bean theo framework | Giao diện dữ liệu phù hợp nhiệm vụ |
| Dữ liệu bí mật không cần công khai | Không cung cấp getter tùy tiện | Giảm bề mặt lộ dữ liệu |

Không nên xem tên phương thức là tiêu chí duy nhất. Ví dụ `setBalance()` có thể đúng cho một công cụ quản trị hoặc dữ liệu mô phỏng với quyền hạn cụ thể, nhưng là API nguy hiểm nếu ai cũng được gọi vào một tài khoản đang hoạt động. Quyết định phụ thuộc **vai trò của lớp, hợp đồng và người gọi**.

## 14. Tự kiểm tra kiến thức

### Bài 1 — Phát hiện điểm yếu

~~~java
class InventoryItem {
    private int stock;

    public int getStock() {
        return stock;
    }

    public void setStock(int stock) {
        this.stock = stock;
    }
}
~~~

**Câu hỏi:** Có gì nguy hiểm nếu mọi module được gọi setter? Bạn sẽ thiết kế lại thế nào?

**Gợi ý:** Setter có thể đặt tồn kho âm hoặc thay số lượng mà không có lý do nghiệp vụ. Cân nhắc `receive(quantity)`, `reserve(quantity)`, `releaseReservation(quantity)` hay `ship(quantity)`, tùy quy trình. Mỗi hành vi phải xác thực số lượng và cập nhật theo quy tắc tồn kho.

### Bài 2 — Tại sao phải sao chép dữ liệu?

~~~java
import java.util.ArrayList;
import java.util.List;

class Course {
    private final List<String> students = new ArrayList<>();

    public List<String> getStudents() {
        return students;
    }
}
~~~

**Đáp án:** Getter trả chính list mutable, người gọi có thể `add/remove` bỏ qua quy tắc đăng ký lớp học. Nên trả snapshot chỉ đọc hoặc một kiểu dữ liệu quan sát phù hợp. Nếu phần tử mutable, xét thêm sao chép/bảo vệ phần tử.

### Bài 3 — Setter có phải luôn sai?

**Đáp án:** Không. `setDisplayName()` có thể là API đơn giản và hợp lệ nếu việc đổi tên độc lập, có validation và không vi phạm vòng đời. Không cần tạo một lớp phức tạp chỉ để thay một trường dữ liệu đơn giản.

### Bài 4 — Thiết kế lịch hẹn

Có `start` và `end` với điều kiện `start < end`. Nên cung cấp `setStart()` và `setEnd()` độc lập không?

**Đáp án:** Có nguy cơ tạo trạng thái trung gian không hợp lệ. `reschedule(start, end)` nhận cùng lúc hai giá trị, xác thực cả cặp rồi mới cập nhật sẽ phù hợp hơn.

### Bài 5 — Getter và đa luồng

Trong một ứng dụng có nhiều luồng, nếu gọi `if (account.hasEnoughBalance(100))` rồi `account.withdraw(100)`, kiểm tra ban đầu có bảo đảm lệnh rút chắc chắn thành công không?

**Đáp án:** Không. Có thể có một giao dịch khác thay đổi số dư giữa hai lời gọi. `withdraw()` cần tự kiểm tra điều kiện cùng cập nhật trạng thái một cách an toàn theo mô hình đồng thời đã chọn.

### Bài 6 — Value object

Một đối tượng `Coordinates` bất biến cần dịch chuyển 5 đơn vị theo trục x. Nên viết `setX(x + 5)` không?

**Đáp án gợi ý:** Không cần setter; có thể cung cấp `translate(dx, dy)` trả về một `Coordinates` mới. Điều này giữ nguyên value object ban đầu và thể hiện ý định.

## Cách suy nghĩ khi thiết kế API của một đối tượng

Trước khi thêm getter, setter hoặc phương thức mới, hãy hỏi:

1. **Người gọi có thực sự cần đọc dữ liệu này không?** Có thể trả thông tin ít hơn hoặc kết quả suy ra thay vì toàn bộ trạng thái nội bộ?
2. **Có được phép sửa thuộc tính ấy độc lập không?** Nếu có, setter kèm validation là lựa chọn hợp lý.
3. **Đây có phải một hành động nghiệp vụ?** Nếu có, đặt tên theo hành động như `confirm()`, `withdraw()`, `reschedule()`.
4. **Có những điều kiện nào phải luôn đúng?** Đặt việc kiểm tra gần nơi cập nhật trạng thái và tránh làm lộ tham chiếu mutable.
5. **Đối tượng có cần mutable không?** Nếu không, cân nhắc immutable class/record và phương thức trả về giá trị mới.

**Thông điệp chính:** Getter và setter là **công cụ**, còn đóng gói là **nguyên tắc thiết kế**. Hãy công khai đúng những gì người gọi cần biết và những hành động họ được phép yêu cầu; giữ việc bảo vệ trạng thái và quy tắc nghiệp vụ ở nơi sở hữu chúng.