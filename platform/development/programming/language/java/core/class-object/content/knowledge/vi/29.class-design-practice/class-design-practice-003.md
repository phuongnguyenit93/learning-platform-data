# Thiết kế thao tác nghiệp vụ để giữ quy tắc hợp lệ trong Java

> **Module:** Java Core – class/object  
> **Nhóm:** Thiết kế và thực hành  
> **Chủ đề:** Thiết kế thao tác nghiệp vụ để giữ quy tắc hợp lệ  
> **Nền tảng:** Java 17+, ví dụ không dùng preview features hay framework đặc biệt.

## 1. Vấn đề thiết kế: đối tượng phải luôn ở trạng thái hợp lệ

Trong lập trình hướng đối tượng, không chỉ cần một class lưu các trường dữ liệu. Một class tốt cần bảo vệ được **các quy tắc về trạng thái (invariants)** trong suốt vòng đời của object.

Ví dụ: một tài khoản không được có số dư âm. Nếu class cho phép mã bên ngoài gọi `setBalance(-100)` thì quy tắc chỉ tồn tại trong tài liệu, không được code bảo vệ. Nếu một đơn hàng đã giao vẫn cho sửa danh sách sản phẩm, trạng thái đơn hàng có thể trở nên mâu thuẫn với hóa đơn và biên nhận.

Mục tiêu của thiết kế thao tác nghiệp vụ là:

1. Biểu diễn **đúng những hành động có nghĩa trong miền nghiệp vụ**: `deposit`, `withdraw`, `pay`, `ship`, `reserveStock`, `enroll` thay cho một tập `setX` vô điều kiện.
2. Đặt việc **kiểm tra điều kiện** tại nơi sở hữu trạng thái, không chỉ tại form/controller.
3. Bảo đảm object bắt đầu ở trạng thái hợp lệ và **mỗi thao tác thành công đưa object tới trạng thái hợp lệ tiếp theo**.
4. Khi một thao tác thất bại, tránh để lại **trạng thái thay đổi một phần**.
5. Không làm lộ các collections hoặc mutable references cho code khác sửa mà bỏ qua kiểm tra.
6. Xác định rõ **phạm vi tính nguyên tử**: một object, nhiều objects, nhiều luồng, database hay hệ thống phân tán.
7. Thiết kế API để trạng thái sai **khó biểu diễn và khó tạo ra một cách vô tình**.

Điểm mấu chốt: **đóng gói không phải chỉ là để field `private`; đóng gói còn là đưa quy tắc hợp lệ và thao tác làm thay đổi trạng thái vào cùng boundary đáng tin**.

## 2. Các khái niệm cần phân biệt

| Khái niệm | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| Invariant (bất biến nghiệp vụ) | Điều gì phải luôn đúng trong các trạng thái quan sát được? | `balance >= 0` |
| Precondition | Điều gì phải đúng trước khi thao tác được phép? | Rút tiền cần `amount > 0` và đủ số dư |
| Postcondition | Sau khi thao tác thành công, điều gì đúng? | Số dư giảm chính xác bằng số tiền rút |
| State transition | Đối tượng được chuyển từ trạng thái nào sang trạng thái nào? | `PAID → SHIPPED` |
| Encapsulation boundary | Ai được quyền sửa dữ liệu? | Chỉ `Order.ship()` đổi trạng thái giao |
| Aggregate boundary | Nhóm objects nào phải nhất quán cùng nhau? | Đơn hàng và các dòng hàng do Order quản lý |
| Failure atomicity | Khi thất bại có để lại cập nhật nửa chừng không? | Giữ nguyên kho nếu một SKU thiếu |
| Defensive copy | Caller có thể sửa dữ liệu nội bộ qua alias không? | Trả `List.copyOf(items)` |
| Concurrency invariant | Nhiều threads có thể phá quy tắc dù mỗi method đúng khi chạy đơn luồng không? | Hai lần rút cùng số dư |
| Persistence transaction | Những thay đổi database nào phải commit hoặc rollback cùng nhau? | Trừ tồn kho và tạo đơn hàng |

Một **invariant** phải được phát biểu sao cho kiểm chứng được. “Tài khoản hợp lý” quá mơ hồ; “số dư không âm và tiền rút lớn hơn 0” là điều kiện có thể code và test.

### 2.1. Bất biến không có nghĩa dữ liệu không bao giờ thay đổi

Số dư có thể tăng/giảm, số chỗ trống có thể thay đổi, trạng thái đơn hàng có thể chuyển tiếp. “Invariant” nghĩa là **điều kiện đúng qua mọi trạng thái hợp lệ**, không phải object immutable.

### 2.2. Phân biệt invariants với rules phụ thuộc ngữ cảnh

Một hóa đơn phải có tổng không âm là invariant nội bộ tương đối ổn định. Khuyến mãi “giảm 10% vào thứ Sáu” là chính sách theo thời gian; có thể đến từ một service/policy object. Không nhồi mọi quy tắc biến động vào setter của một entity.

### 2.3. Hợp lệ tại constructor chưa đủ

Một constructor có thể kiểm tra số dư ban đầu nhưng `setBalance(-5)` vẫn cho phá trạng thái sau đó. Cần xét **mọi đường thay đổi**: methods, exposed mutable lists, reflection/frameworks, deserialization, concurrency và các collaborators.

## 3. Thiết kế yếu: cho phép setter tùy ý

~~~java
class Account {
    private long balanceCents;

    Account(long balanceCents) {
        this.balanceCents = balanceCents;
    }

    long getBalanceCents() {
        return balanceCents;
    }

    void setBalanceCents(long balanceCents) {
        this.balanceCents = balanceCents;
    }
}
~~~

Đây là **fragment minh họa thiết kế có lỗ hổng**. Caller có thể:

~~~java
Account account = new Account(1000);
account.setBalanceCents(-500);
~~~

Không có một domain operation nào giải thích tại sao số dư thành âm, hoặc liệu có nghiệp vụ cho phép overdraft không. Nếu mọi nơi tự kiểm tra trước khi gọi setter, mỗi nơi có thể quên hoặc dùng điều kiện khác nhau.

### 3.1. Không thể “để controller kiểm tra là đủ”

Có thể có REST controller, scheduled job, import script, test fixture hoặc một API mới trong tương lai cùng gọi entity. Nếu invariant chỉ nằm ở một controller, code path khác có thể phá nó.

Controller vẫn nên kiểm tra lỗi nhập liệu để đưa thông báo thân thiện. Nhưng **điều kiện cốt lõi của domain vẫn phải được thực thi tại object/service sở hữu trạng thái**.

### 3.2. Vấn đề của CRUD-centric API

Một API có `getStatus/setStatus` cho phép chuyển trực tiếp `DRAFT → SHIPPED` mà bỏ bước thanh toán, không log domain event và không kiểm tra các dòng hàng. Để sửa, thay bằng methods diễn đạt hành vi: `pay()`, `ship()`, `cancel()` với guard hợp lệ.

### 3.3. Không phải setter nào cũng xấu

Một object thuần cấu hình hoặc DTO có thể dùng setters theo contract. Với state mang quy tắc nghiệp vụ, điều quan trọng là **không để setter mở đường tạo trạng thái sai**. Setter có validation nghiêm ngặt vẫn có thể hợp lệ khi nó chính là thao tác nghiệp vụ đủ ý nghĩa, nhưng tên method thường cần diễn đạt business intent rõ hơn.

## 4. Viết invariant thành công thức và test cases

Với tài khoản không cho rút âm:

- `balanceCents >= 0` luôn đúng sau khi tạo và sau mỗi public operation.
- `deposit(amount)` yêu cầu `amount > 0` và không overflow.
- `withdraw(amount)` yêu cầu `amount > 0`, `amount <= balanceCents`.
- Deposit thành công: `newBalance = oldBalance + amount`.
- Withdraw thành công: `newBalance = oldBalance - amount`.
- Nếu tham số sai hoặc thiếu số dư, **số dư không đổi**.

Một cách trình bày bằng Hoare-style reasoning:

~~~text
Trước withdraw:
  balance >= 0
  amount > 0
  amount <= balance

Thao tác:
  balance = balance - amount

Sau withdraw:
  balance >= 0
  balance_new = balance_old - amount
~~~

### 4.1. Bắt đầu với invariant mạnh, nhỏ

Với class nhỏ, một vài điều kiện rõ có thể đủ. Đừng viết “object luôn consistent” mà không định nghĩa consistent gồm những gì.

### 4.2. Đánh dấu các điểm thay đổi trạng thái

Tìm mọi câu lệnh gán vào state fields, mutations của collections và calls tới mutable collaborators. Mỗi điểm thay đổi phải đi qua một luồng kiểm tra/commit hợp lệ.

### 4.3. Phân loại lỗi đầu vào

Một số errors là **vi phạm precondition**: amount âm, ID rỗng, thời gian kết thúc trước thời gian bắt đầu. Một số là **business rejection**: không đủ số dư, kho hết, đơn không được giao ở trạng thái DRAFT. API có thể dùng exception riêng hoặc result type, nhưng phải giúp caller phân biệt nguyên nhân đủ để xử lý.

## 5. Chương trình hoàn chỉnh 1 — giữ giới hạn chỗ đặt với operation có điều kiện

Để tập trung vào **thiết kế thao tác bảo vệ invariant** thay vì viết lại bài thực hành BankAccount, xét một nhóm chỗ có tổng sức chứa cố định. Quy tắc nghiệp vụ là:

- `capacity > 0` ngay từ lúc tạo.
- `0 <= reserved <= capacity` ở mọi trạng thái có thể quan sát.
- `reserve(n)` chỉ nhận `n > 0` và còn đủ chỗ.
- `release(n)` chỉ nhận `n > 0` và `n <= reserved`.
- Một lệnh bị từ chối phải **không thay đổi** số chỗ đã đặt.

Tạo file **`SeatReservationDemo.java`**:

~~~java
public class SeatReservationDemo {
    static final class SeatPool {
        private final int capacity;
        private int reserved;

        SeatPool(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException(
                        "capacity must be positive");
            }
            this.capacity = capacity;
        }

        void reserve(int count) {
            requirePositive(count);
            if (count > capacity - reserved) {
                throw new IllegalStateException(
                        "insufficient seats");
            }
            reserved += count;
        }

        void release(int count) {
            requirePositive(count);
            if (count > reserved) {
                throw new IllegalStateException(
                        "not reserved");
            }
            reserved -= count;
        }

        int reserved() {
            return reserved;
        }

        int available() {
            return capacity - reserved;
        }

        private static void requirePositive(int count) {
            if (count <= 0) {
                throw new IllegalArgumentException(
                        "count must be positive");
            }
        }
    }

    public static void main(String[] args) {
        SeatPool seats = new SeatPool(4);
        seats.reserve(2);
        seats.reserve(1);
        System.out.println("reserved=" + seats.reserved());

        try {
            seats.reserve(2);
        } catch (IllegalStateException ex) {
            System.out.println("reserve rejected="
                    + ex.getMessage());
        }

        try {
            seats.release(4);
        } catch (IllegalStateException ex) {
            System.out.println("release rejected="
                    + ex.getMessage());
        }

        seats.release(1);
        System.out.println("after release=" + seats.reserved());
        System.out.println("available=" + seats.available());
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 SeatReservationDemo.java
java SeatReservationDemo
~~~

Stdout dự kiến:

~~~text
reserved=3
reserve rejected=insufficient seats
release rejected=not reserved
after release=2
available=2
~~~

### 5.1. Vì sao đây là API nghiệp vụ thay vì setter?

Nếu cung cấp `setReserved(int)`, caller có thể tự đặt `reserved = -1` hoặc lớn hơn capacity. `reserve` và `release` thể hiện **hành động**, không chỉ là phép gán field, và kiểm tra cả yêu cầu mới lẫn trạng thái hiện tại.

### 5.2. Check trước — commit sau

Điều kiện `count > capacity - reserved` dùng hiệu số không âm để kiểm tra còn đủ chỗ; chỉ sau khi vượt qua guard mới cộng `reserved += count`. Tương tự, `release` kiểm tra trước rồi mới trừ. Vì kết quả sau mỗi thao tác được ràng buộc trong `[0, capacity]`, không có overflow của phép cộng trong phạm vi invariant này.

### 5.3. Phạm vi an toàn của ví dụ

Các thao tác trên **không thread-safe** nếu nhiều threads gọi cùng `SeatPool` đồng thời. Một ứng dụng đặt chỗ thực tế phải bảo vệ đọc–kiểm tra–ghi bằng synchronization, DB constraints/transactions hoặc cơ chế phù hợp. `capacity` là field `final`, nhưng `reserved` là mutable; `final` không tự giải quyết concurrency.

Bài **“Xây dựng lớp tài khoản với tạo mới, nạp tiền và rút tiền”** áp dụng chính tư duy *valid commands và unchanged state on failure* vào bài tập tài khoản có money representation, overflow handling và kiểm thử riêng.

## 6. Constructor/factory là “cửa vào” trạng thái hợp lệ

Một class với invariant không được cho phép tạo object sai ngay từ đầu.

~~~java
record Quantity(int units) {
    Quantity {
        if (units <= 0) {
            throw new IllegalArgumentException("units must be positive");
        }
    }
}
~~~

Đây là **record fragment**. Mọi cách tạo `new Quantity(n)` qua canonical constructor đều phải đi qua validation này.

### 6.1. Constructor không nên chỉ gán fields

Một constructor có nhiệm vụ thiết lập invariant như fields non-null, ranges hợp lệ, liên hệ giữa multiple fields hợp lý. Nếu object mới đã sai, không method nào có thể chắc rằng baseline state đúng.

### 6.2. Static factory giúp đặt tên nghiệp vụ

~~~java
static Order draftFor(CustomerId customerId) { ... }
static Money zero(String currency) { ... }
~~~

Đây là **conceptual signatures**. Tên factory giúp giải thích trạng thái khởi tạo; nhưng validation vẫn phải nằm trong constructor/factory trusted path, tránh API song song bỏ qua validation.

### 6.3. Không để object “nửa khởi tạo” lộ ra

Tránh publish `this` từ constructor qua listener/registry/thread trước khi fields và invariants được thiết lập. Kể cả fields cuối cùng đúng, object bị quan sát quá sớm có thể gặp trạng thái trung gian.

### 6.4. Không dùng constructor chỉ để thực hiện workflow dài

Tạo một domain object khác với gọi payment gateway, network request hay database transaction. Có thể cần application service điều phối external I/O, sau đó domain object ghi nhận kết quả qua method có guard.

## 7. State machine: trạng thái phải chuyển qua những cạnh hợp lệ

Một đơn hàng có thể được mô hình hóa:

~~~text
DRAFT --pay--> PAID --ship--> SHIPPED
  |
  +--cancel--> CANCELLED

PAID --cancel--> CANCELLED
~~~

Các transitions trên chỉ là **một ví dụ chính sách**. Domain khác có thể yêu cầu refund trước cancel hoặc không cho cancel sau payment.

Invariant của ví dụ:

- Đơn ở `DRAFT` mới được thêm sản phẩm.
- Chỉ đơn DRAFT **có ít nhất một dòng hàng** mới được thanh toán.
- Chỉ đơn PAID mới được giao.
- `SHIPPED` và `CANCELLED` không sửa items và không tự động “quay lại” DRAFT.
- Thanh toán/giao/hủy sai trạng thái phải bị từ chối **không đổi state**.
- Tổng tiền được suy ra từ lines; không public setter độc lập cho total.

### 7.1. Tại sao enum phù hợp với state?

Enum có tập constants hữu hạn; switch/guard thể hiện các cạnh. Nhưng enum bản thân chỉ định nghĩa tên trạng thái, **không tự ngăn code gán sai** nếu entity vẫn cho `setStatus` tùy ý.

### 7.2. Đặt transitions trong object sở hữu state

`Order.pay()` hiểu items và current status; `Order.ship()` hiểu current state. Controller chỉ yêu cầu hành động, không sửa trực tiếp status field.

## 8. Chương trình hoàn chỉnh 2 — đơn hàng chỉ cho phép transitions hợp lệ

Tệp **`OrderWorkflowDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class OrderWorkflowDemo {
    enum Status {
        DRAFT, PAID, SHIPPED, CANCELLED
    }

    record Line(String sku, int quantity, long unitPriceCents) {
        Line {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("empty SKU");
            }
            if (quantity <= 0 || unitPriceCents < 0) {
                throw new IllegalArgumentException("invalid line");
            }
        }

        long amountCents() {
            return Math.multiplyExact(quantity, unitPriceCents);
        }
    }

    static final class Order {
        private Status status = Status.DRAFT;
        private final List<Line> lines = new ArrayList<>();

        Status status() {
            return status;
        }

        List<Line> lines() {
            return List.copyOf(lines);
        }

        void addLine(Line line) {
            requireStatus(Status.DRAFT);
            if (line == null) {
                throw new IllegalArgumentException("null line");
            }
            lines.add(line);
        }

        long totalCents() {
            long sum = 0;
            for (Line line : lines) {
                sum = Math.addExact(sum, line.amountCents());
            }
            return sum;
        }

        void pay() {
            requireStatus(Status.DRAFT);
            if (lines.isEmpty()) {
                throw new IllegalStateException("empty order");
            }
            totalCents(); // Kiểm tra số học trước thay đổi trạng thái.
            status = Status.PAID;
        }

        void ship() {
            requireStatus(Status.PAID);
            status = Status.SHIPPED;
        }

        void cancel() {
            if (status != Status.DRAFT && status != Status.PAID) {
                throw new IllegalStateException("cannot cancel");
            }
            status = Status.CANCELLED;
        }

        private void requireStatus(Status expected) {
            if (status != expected) {
                throw new IllegalStateException(
                        "expected " + expected + ", was " + status);
            }
        }
    }

    public static void main(String[] args) {
        Order order = new Order();

        try {
            order.ship();
        } catch (IllegalStateException ex) {
            System.out.println("Early ship = " + ex.getMessage());
        }

        order.addLine(new Line("BOOK", 2, 500));
        System.out.println("Total = " + order.totalCents());

        order.pay();
        System.out.println("After payment = " + order.status());

        order.ship();
        System.out.println("After shipping = " + order.status());

        try {
            order.addLine(new Line("PEN", 1, 100));
        } catch (IllegalStateException ex) {
            System.out.println("Late edit = " + ex.getMessage());
        }

        System.out.println("Lines = " + order.lines().size());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 OrderWorkflowDemo.java
java OrderWorkflowDemo
~~~

**Stdout chính xác:**

~~~text
Early ship = expected PAID, was DRAFT
Total = 1000
After payment = PAID
After shipping = SHIPPED
Late edit = expected DRAFT, was SHIPPED
Lines = 1
~~~

### 8.1. Không có public `setStatus`

Các transitions được gói trong `pay`/`ship`/`cancel` với guard phù hợp. Một màn hình không thể chuyển thẳng DRAFT sang SHIPPED chỉ bằng setter.

### 8.2. `lines()` trả snapshot bất biến

`List.copyOf(lines)` trả List không sửa được. Caller không thể trực tiếp thêm hàng vào internal ArrayList và bỏ qua `addLine`. Các Line là immutable records với primitive/String components nên không phát sinh mutable element leak trong demo.

### 8.3. Không tách total thành một field được set độc lập

Nếu vừa có lines vừa có `setTotal` thì rất dễ hai giá trị mâu thuẫn. `totalCents()` tính từ các lines. Nếu phải cache total để hiệu năng, mọi mutation phải cập nhật cả hai fields như một invariant và có tests bảo đảm nhất quán.

### 8.4. Đơn giản hóa về payment

`pay()` ở demo chỉ đổi state nội bộ sau guard, **không gọi ngân hàng hay payment gateway**. Với hệ thống thật, payment success cần được xác nhận từ external system, quản lý idempotency và transaction/outbox. Đừng đánh đồng “đổi status=PAID” với tiền đã được thu.

## 9. Không công khai mutable collections: một lỗ hổng đóng gói thường gặp

Một getter có thể là cửa sau phá invariant:

~~~java
class Team {
    private final List<Member> members = new ArrayList<>();

    public List<Member> getMembers() {
        return members; // Rò mutable reference.
    }
}
~~~

Nếu rule là team tối đa 5 thành viên, caller có thể `team.getMembers().add(member)` hàng chục lần mà không qua kiểm tra limit.

### 9.1. Các lựa chọn an toàn

- Trả snapshot `List.copyOf(members)` nếu elements immutable/được xử lý đúng ownership.
- Trả unmodifiable **view** khi thực sự muốn live view và có thể kiểm soát concurrent modifications; hiểu rằng view thay theo source list và không bảo vệ mutable elements.
- Trả một DTO/summary thay vì expose internal aggregate.
- Chỉ cung cấp business methods như `addMember`/`removeMember` với guards.

### 9.2. Unmodifiable wrapper không đồng nghĩa snapshot

`Collections.unmodifiableList(internal)` ngăn caller sửa list qua wrapper, nhưng khi owner thay `internal`, view phản ánh thay đổi. `List.copyOf(internal)` tạo unmodifiable list từ elements hiện tại (có thể reuse suitable immutable source) và giữ cấu trúc snapshot theo contract.

### 9.3. Mutable elements vẫn nguy hiểm

`List.copyOf` chỉ xử lý cấu trúc List. Nếu List chứa `MutableMember` có public `setRole`, caller vẫn có thể mutate elements. Cần immutable element types, defensive copies sâu thích hợp, hoặc chỉ expose read-only projections.

## 10. Thiết kế thao tác “all-or-nothing” trên nhiều fields

Ví dụ kho cần giữ các quy tắc:

- Tồn kho mỗi SKU luôn `>= 0`.
- Đặt chỗ phải yêu cầu quantity dương.
- Nếu bất kỳ SKU nào thiếu, **không trừ SKU nào**.
- Không public setters cho quantity để caller âm thầm đặt -99.

Một implementation sai:

~~~java
for (RequestLine request : requestLines) {
    stock.put(request.sku(), stock.get(request.sku()) - request.qty());
    if (stock.get(request.sku()) < 0) {
        throw new IllegalStateException("not enough");
    }
}
~~~

Đây là **anti-pattern fragment**. Nó mutate trước khi validate. Nếu SKU thứ hai thiếu, SKU thứ nhất đã bị trừ; object rơi vào trạng thái cập nhật một phần.

### 10.1. Chuẩn bị trước, commit sau

Một thiết kế an toàn hơn trong single-thread context:

1. Validate request input toàn bộ: SKU, qty, duplicates.
2. Build một `proposed` map hoặc copy trạng thái.
3. Kiểm tra kho đủ cho tất cả entries.
4. Chỉ khi mọi guard pass, commit thay đổi vào state.
5. Thông báo lỗi đủ ý nghĩa cho caller.

### 10.2. Validate toàn bộ input trước mutation

Nếu một operation xử lý 10 sản phẩm, lỗi ở sản phẩm thứ 10 không nên làm 9 sản phẩm trước bị trừ nếu contract tuyên bố nguyên tử.

### 10.3. “Prepare-then-commit” không tự giải quyết threads/database

Nếu một thread khác có thể sửa stock sau bước validate nhưng trước commit, operation vẫn có race. Phải kết hợp với lock, immutable state replacement/atomic CAS hoặc database transaction tùy boundary. Bài demo ban đầu cố ý single-threaded; phần sau có ví dụ lock.

## 11. Chương trình hoàn chỉnh 3 — giữ tồn kho hợp lệ khi reserve nhiều SKU

Tệp **`InventoryReservationDemo.java`**:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeMap;

public class InventoryReservationDemo {
    static final class Inventory {
        private final Map<String, Integer> onHand = new TreeMap<>();

        void addStock(String sku, int qty) {
            requireSku(sku);
            requirePositive(qty);
            int next = Math.addExact(onHand.getOrDefault(sku, 0), qty);
            onHand.put(sku, next);
        }

        Map<String, Integer> snapshot() {
            return Map.copyOf(onHand);
        }

        void reserve(Map<String, Integer> request) {
            if (request == null || request.isEmpty()) {
                throw new IllegalArgumentException("empty request");
            }

            Map<String, Integer> proposed = new LinkedHashMap<>();
            for (Map.Entry<String, Integer> entry : request.entrySet()) {
                String sku = entry.getKey();
                Integer qty = entry.getValue();

                requireSku(sku);
                if (qty == null) {
                    throw new IllegalArgumentException("null quantity");
                }
                requirePositive(qty);

                int current = onHand.getOrDefault(sku, 0);
                if (qty > current) {
                    throw new IllegalStateException("insufficient " + sku);
                }
                proposed.put(sku, current - qty);
            }

            // Không mutate onHand cho đến khi toàn bộ request hợp lệ.
            onHand.putAll(proposed);
        }

        int quantity(String sku) {
            return onHand.getOrDefault(sku, 0);
        }

        private static void requireSku(String sku) {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("empty SKU");
            }
        }

        private static void requirePositive(int qty) {
            if (qty <= 0) {
                throw new IllegalArgumentException("qty must be positive");
            }
        }
    }

    public static void main(String[] args) {
        Inventory inventory = new Inventory();
        inventory.addStock("BOOK", 4);
        inventory.addStock("PEN", 2);

        try {
            inventory.reserve(Map.of("BOOK", 2, "PEN", 3));
        } catch (IllegalStateException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }

        System.out.println("After failure BOOK = "
                + inventory.quantity("BOOK"));
        System.out.println("After failure PEN = "
                + inventory.quantity("PEN"));

        inventory.reserve(Map.of("BOOK", 2, "PEN", 1));
        System.out.println("After success BOOK = "
                + inventory.quantity("BOOK"));
        System.out.println("After success PEN = "
                + inventory.quantity("PEN"));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 InventoryReservationDemo.java
java InventoryReservationDemo
~~~

**Stdout chính xác:**

~~~text
Rejected = insufficient PEN
After failure BOOK = 4
After failure PEN = 2
After success BOOK = 2
After success PEN = 1
~~~

### 11.1. Tại sao lỗi chắc là PEN?

BOOK có 4, yêu cầu 2 — hợp lệ. PEN có 2, yêu cầu 3 — không hợp lệ. Dù `Map.of` không hứa iteration order, lỗi duy nhất của request là PEN; method cuối cùng vẫn throw trước `putAll`, nên output ổn định.

### 11.2. Vì sao tồn kho không đổi khi thất bại?

Method xây proposed map riêng, không thay `onHand` trong validation loop. Nếu có một entry thiếu, exception xảy ra **trước** commit.

### 11.3. Một giả định của demo

`reserve` không sửa `request`; caller phải không sửa concurrent map giữa validation và xử lý nếu không có synchronization. Demo dùng Map.of immutable. Production implementation cần snapshot input/lock nếu caller có thể cung cấp mutable concurrent state.

### 11.4. Phần commit có thể lỗi không?

Với in-memory `TreeMap`/`Integer` trong điều kiện bình thường và input đã được validate, `putAll` dùng keys/values hợp lệ; nhưng **không có general Java guarantee rằng mọi arbitrary mutation batch vào mutable structures có transaction rollback** nếu runtime gặp unchecked failure (ví dụ resource exhaustion). Nếu thật sự cần atomic state swap trong bộ nhớ và readers khác, xây một immutable snapshot rồi thay một reference dưới synchronization có thể rõ hơn; với database thì dùng transaction.

## 12. Các kiểu lỗi: input sai, trạng thái không cho phép và hạ tầng

Thiết kế thao tác nên phân biệt lỗi để caller xử lý nhất quán.

| Nhóm | Ví dụ | Cách biểu diễn thường gặp |
| --- | --- | --- |
| Invalid argument | Số lượng 0, SKU rỗng, thời gian end <= start | `IllegalArgumentException` hoặc validation error |
| Illegal business state | Giao hàng khi chưa thanh toán | `IllegalStateException` hoặc domain-specific exception |
| Business rejection | Không đủ số dư, hết chỗ | Domain result/exception cụ thể |
| Infrastructure failure | Database/network unavailable | Exception ở adapter/application service |
| Concurrency conflict | Version đã đổi do request khác | Conflict result, retry/cancellation strategy |
| Programming bug | Null dereference không mong đợi | Fail fast, log, sửa code |

### 12.1. Exception hay result type?

Không có một lựa chọn đúng tuyệt đối. Dùng exceptions khi operation hợp lệ về loại nhưng không thể thực hiện theo contract; dùng một `Result`/sealed outcome khi business rejection thường xuyên là nhánh xử lý dự kiến.

### 12.2. Đừng catch Exception rồi trả false cho mọi lỗi

Nếu mọi lỗi từ DB đến bug đều thành false, caller không biết vì sao không thực hiện được và có thể retry sai. Bảo toàn phân loại failure trong API, log và monitoring.

### 12.3. Lỗi validation nên đến trước mutation

Nhiều domain methods có thể fail fast. Nhưng nếu một action yêu cầu kiểm tra hết các trường để trả danh sách lỗi UX, có thể thu thập errors trước commit. Điều quan trọng là **không mutate partial state trong khi còn đang thu thập lỗi**.

## 13. Chương trình hoàn chỉnh 4 — đăng ký khóa học và kết quả nghiệp vụ

Tệp **`CourseEnrollmentDemo.java`**:

~~~java
import java.util.LinkedHashSet;
import java.util.Set;

public class CourseEnrollmentDemo {
    enum EnrollmentResult {
        ENROLLED, ALREADY_ENROLLED, FULL
    }

    static final class Course {
        private final int capacity;
        private final Set<String> studentIds = new LinkedHashSet<>();

        Course(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity must be positive");
            }
            this.capacity = capacity;
        }

        EnrollmentResult enroll(String studentId) {
            if (studentId == null || studentId.isBlank()) {
                throw new IllegalArgumentException("invalid student ID");
            }

            if (studentIds.contains(studentId)) {
                return EnrollmentResult.ALREADY_ENROLLED;
            }
            if (studentIds.size() >= capacity) {
                return EnrollmentResult.FULL;
            }

            studentIds.add(studentId);
            return EnrollmentResult.ENROLLED;
        }

        int enrolledCount() {
            return studentIds.size();
        }

        Set<String> roster() {
            return Set.copyOf(studentIds);
        }
    }

    public static void main(String[] args) {
        Course course = new Course(2);

        System.out.println(course.enroll("s1"));
        System.out.println(course.enroll("s1"));
        System.out.println(course.enroll("s2"));
        System.out.println(course.enroll("s3"));
        System.out.println("Enrolled = " + course.enrolledCount());
        System.out.println("Has s3 = " + course.roster().contains("s3"));
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 CourseEnrollmentDemo.java
java CourseEnrollmentDemo
~~~

**Stdout chính xác:**

~~~text
ENROLLED
ALREADY_ENROLLED
ENROLLED
FULL
Enrolled = 2
Has s3 = false
~~~

### 13.1. Vì sao return enum thay vì throw ở mọi rejected signup?

`ALREADY_ENROLLED` và `FULL` là những kết quả nghiệp vụ bình thường trong nhiều hệ thống đăng ký. Caller có thể hiển thị thông báo và không coi đó là bug. `invalid student ID` vẫn được từ chối bằng IllegalArgumentException vì caller vi phạm input contract.

### 13.2. Hai invariants đồng thời

- `studentIds.size() <= capacity`.
- Mỗi studentId chỉ xuất hiện tối đa một lần.

`LinkedHashSet` giúp uniqueness, `enroll` bảo vệ capacity. Sử dụng Set không tự bảo vệ capacity; cần business method.

### 13.3. Vì sao kiểm tra duplicate trước full?

Một sinh viên đã đăng ký gửi lại request khi lớp đã đủ chỗ sẽ nhận `ALREADY_ENROLLED` thay vì `FULL`. Đây là một **lựa chọn chính sách/idempotent-ish semantics** có ích. Domain khác có thể muốn trả lỗi theo thứ tự khác, nhưng phải định nghĩa rõ.

### 13.4. Đồng thời nhiều threads vẫn cần đồng bộ

Hai threads có thể cùng thấy size=1 khi capacity=2 rồi cùng add hai studentIds mới, vượt capacity. Single-thread invariant của method không đủ trong concurrent context; cần lock/database unique+capacity constraints.

## 14. Một thao tác nên để object có thể dùng tiếp khi thất bại

Xét method:

~~~java
void updateLimits(int low, int high) {
    this.low = low;
    if (low > high) {
        throw new IllegalArgumentException();
    }
    this.high = high;
}
~~~

Đây là **anti-pattern fragment**: field low bị gán trước validation. Nếu low > high, exception xảy ra nhưng object vẫn giữ một nửa cập nhật.

Sửa:

~~~java
void changeRange(int low, int high) {
    if (low > high) {
        throw new IllegalArgumentException("low > high");
    }
    this.low = low;
    this.high = high;
}
~~~

Với single-thread observer và assignments primitive đơn giản, thao tác giữ invariant tốt hơn. Với nhiều threads, cần cùng lock hoặc atomic snapshot để readers không quan sát tổ hợp fields trung gian.

### 14.1. Strong exception guarantee

Một mục tiêu thiết kế có ích là: **nếu operation thất bại vì business validation, observable object state giữ nguyên**. Đây thường gọi là failure atomicity/strong exception safety theo ngữ cảnh. Không có nghĩa Java tự cung cấp rollback cho mọi method.

### 14.2. Side effects phải được phân tích riêng

Nếu một method đã gửi email rồi sau đó ném exception, bạn không thể “undo email” chỉ bằng khôi phục fields. Nếu charge payment gateway rồi update database thất bại, cần compensation/idempotency/outbox/process design, không chỉ một try/catch trong entity.

## 15. Giá trị bất biến làm invariant dễ bảo vệ

Các value objects có thể giúp loại trừ data sai ngay từ khi được tạo. Ví dụ Money:

- Currency code không rỗng.
- Amount có 2 chữ số thập phân theo demo.
- Amount không âm (trong business scope của ví dụ).
- Chỉ cộng hai amounts có cùng currency.
- Mọi phép cộng trả **Money mới**, không mutate existing Money.

### 15.1. Tại sao dùng record?

Record phù hợp cho value carrier nhỏ với components final. Nhưng constructor vẫn cần validation; record không tự chứng minh amount/currency hợp lệ.

### 15.2. BigDecimal và scale

`BigDecimal` tránh nhiều vấn đề của binary floating-point khi biểu diễn số thập phân, nhưng scale/rounding/currency semantics vẫn phải được quyết định. Demo dùng `setScale(2, RoundingMode.UNNECESSARY)` để **từ chối** input cần rounding thay vì âm thầm làm tròn.

### 15.3. Không làm lộ một “setter amount” của Money

Nếu Money là immutable value object, cộng tiền nên trả Money mới. Một Account entity có thể sở hữu Money balance và cập nhật reference thông qua business operations có guards.

## 16. Chương trình hoàn chỉnh 5 — Money bảo vệ currency và amount

Tệp **`MoneyInvariantDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public class MoneyInvariantDemo {
    record Money(BigDecimal amount, String currency) {
        Money {
            Objects.requireNonNull(amount, "amount");
            Objects.requireNonNull(currency, "currency");

            if (currency.isBlank()) {
                throw new IllegalArgumentException("empty currency");
            }

            amount = amount.setScale(2, RoundingMode.UNNECESSARY);
            if (amount.signum() < 0) {
                throw new IllegalArgumentException("negative money");
            }
        }

        Money plus(Money other) {
            Objects.requireNonNull(other);
            if (!currency.equals(other.currency)) {
                throw new IllegalArgumentException("different currency");
            }
            return new Money(amount.add(other.amount), currency);
        }
    }

    public static void main(String[] args) {
        Money first = new Money(new BigDecimal("10.00"), "USD");
        Money second = new Money(new BigDecimal("2.50"), "USD");

        Money sum = first.plus(second);

        System.out.println("Sum = " + sum.amount()
                + " " + sum.currency());
        System.out.println("Original = " + first.amount());

        try {
            first.plus(new Money(new BigDecimal("1.00"), "EUR"));
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }

        try {
            new Money(new BigDecimal("-1.00"), "USD");
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 MoneyInvariantDemo.java
java MoneyInvariantDemo
~~~

**Stdout chính xác:**

~~~text
Sum = 12.50 USD
Original = 10.00
Rejected = different currency
Rejected = negative money
~~~

### 16.1. Constructor normalization giữ invariant thật

Compact record constructor normalize parameter `amount` sang scale 2 trước khi Java gán vào final component field. Default record accessor, equals/hashCode/toString sau đó đều thấy normalized field; không chỉ custom accessor đưa ra một “view đẹp” nhưng storage còn raw.

### 16.2. Kiểm tra currency trước khi cộng

`Money.plus` từ chối cộng USD với EUR. Đây không phải một phép cộng đúng nghĩa nghiệp vụ nếu không có exchange rate/context. Không để type BigDecimal làm ta quên đơn vị.

### 16.3. Rounding policy không được chọn bừa

Một hệ thống tiền thật cần xem decimals theo currency, exchange rate, tax, accounting rounding, negative amounts, refunds. Bài chỉ mô hình hóa giá trị không âm và scale 2 để minh họa invariant. Domain có thể thay đổi chính sách, nhưng vẫn phải giữ những rules có thể kiểm chứng.

## 17. Invariant giữa nhiều objects: thiết kế aggregate boundary

Khi một rule liên quan nhiều objects, cần xác định **ai có quyền quyết định và cập nhật**.

Ví dụ Order chứa OrderLines:

~~~text
Order (aggregate root)
  |
  +-- Line A: sku, qty, unit price
  |
  +-- Line B: sku, qty, unit price

Invariant:
  order.status == SHIPPED => lines không được sửa
  total == sum(line amounts)
~~~

Nếu caller có thể lấy `order.getLines()` và sửa từng Line tùy ý, Order không còn bảo vệ invariant. Cho Order sở hữu collection và chỉ nhận commands như `addLine/removeLine` trong trạng thái cho phép.

### 17.1. Đặt quy tắc nơi có đủ dữ liệu để kiểm tra

Một `Line` biết qty/price hợp lệ. `Order` biết có bao nhiêu lines và status. Vì vậy Line constructor bảo vệ line-level invariant; Order methods bảo vệ order-level invariant.

### 17.2. Không làm aggregate quá lớn

Nếu tất cả business invariants của toàn hệ thống được gom trong một root object duy nhất, lock/transaction/complexity trở nên quá lớn. Chọn boundary nhỏ nhưng **đủ** để bảo vệ strong consistency rules. Quy tắc xuyên aggregate có thể phải xử lý bằng application services và eventual consistency.

### 17.3. Một invariant có thể vừa ở domain vừa ở database

Ví dụ số dư >=0 có thể có DB check constraint; student enrollment uniqueness có thể có unique index. Domain checks cho lỗi sớm và model rõ; DB constraints bảo vệ persistent state trước concurrent/external writers. Hai tầng bổ sung nhau, không thay thế nhau.

## 18. Chương trình hoàn chỉnh 6 — đối tượng giữ dữ liệu, snapshot và chuyển trạng thái

Tệp **`TeamMembershipDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class TeamMembershipDemo {
    record Member(String id) {
        Member {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("invalid ID");
            }
        }
    }

    static final class Team {
        private final int capacity;
        private final List<Member> members = new ArrayList<>();
        private boolean locked;

        Team(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("invalid capacity");
            }
            this.capacity = capacity;
        }

        void add(Member member) {
            if (locked) {
                throw new IllegalStateException("team locked");
            }
            if (member == null) {
                throw new IllegalArgumentException("null member");
            }
            if (members.contains(member)) {
                throw new IllegalStateException("duplicate member");
            }
            if (members.size() == capacity) {
                throw new IllegalStateException("team full");
            }
            members.add(member);
        }

        void lock() {
            locked = true;
        }

        List<Member> members() {
            return List.copyOf(members);
        }
    }

    public static void main(String[] args) {
        Team team = new Team(2);
        team.add(new Member("a"));

        List<Member> snapshot = team.members();
        team.add(new Member("b"));

        System.out.println("Snapshot size = " + snapshot.size());
        System.out.println("Current size = " + team.members().size());

        try {
            team.add(new Member("c"));
        } catch (IllegalStateException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }

        team.lock();

        try {
            team.add(new Member("c"));
        } catch (IllegalStateException ex) {
            System.out.println("Locked = " + ex.getMessage());
        }

        System.out.println("Final size = " + team.members().size());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 TeamMembershipDemo.java
java TeamMembershipDemo
~~~

**Stdout chính xác:**

~~~text
Snapshot size = 1
Current size = 2
Rejected = team full
Locked = team locked
Final size = 2
~~~

### 18.1. Snapshot giúp tránh việc caller lách guards

`members()` trả List.copyOf, không phải internal ArrayList. Caller không thể dùng `snapshot.add(new Member(...))` để vượt capacity.

### 18.2. Snapshot cũ không biến thành live view

Sau khi thêm member b, snapshot lấy trước đó vẫn có size 1, còn snapshot mới của Team có size 2. Đây là hành vi đúng với structural snapshot.

### 18.3. Member là record có invariant riêng

Team kiểm tra capacity, uniqueness và locked; Member constructor kiểm tra ID. Phân chia trách nhiệm giúp mỗi lớp bảo vệ điều nó sở hữu.

### 18.4. Tại sao duplicate detection dùng `contains` đáng tin?

Record Member có generated value equality theo component id. `new Member("a")` bằng nhau về giá trị với Member("a") khác. Với mutable member objects, equality/hashCode semantics cần được thiết kế rõ hơn.

## 19. Thread safety: invariant đơn luồng chưa đủ

Xét:

~~~java
void withdraw(long amount) {
    if (amount > balance) {
        throw new IllegalStateException();
    }
    balance -= amount;
}
~~~

Một thread thấy balance = 100; thread khác cũng thấy balance = 100; cả hai rút 80. Nếu updates được xen kẽ không đồng bộ, account có thể debit sai hoặc lost update. **Check-then-act là một đơn vị cần đồng bộ**, không chỉ mỗi phép gán field.

### 19.1. Volatile không làm một chuỗi thao tác thành atomic

`volatile long balance` cung cấp visibility/ordering semantics cho field access theo Java memory model, nhưng không biến `if (balance >= amount) balance -= amount` thành atomic transaction. Dùng lock, CAS loop hoặc serialized executor phù hợp.

### 19.2. Dùng một lock chung bảo vệ state

Với một Account, `synchronized` trên methods có thể bảo vệ cùng monitor. Với chuyển tiền giữa hai Account, cần phối hợp cả hai sides dưới một concurrency boundary đáng tin; khóa từng Account riêng mà không có ordering có thể deadlock.

### 19.3. Demo dùng global lock có chủ đích

Ví dụ tiếp theo dùng một lock chung cho toàn bộ ngân hàng **để chứng minh correctness dễ dàng**. Nó tạo bottleneck nếu nhiều accounts/transactions; production system có thể dùng deterministic lock ordering theo account ID, transaction store hoặc database isolation.

### 19.4. Concurrent operations phải linearizable theo contract khi cần

Một transfer nên xuất hiện như một cập nhật logic nguyên tử với observers có cùng synchronization. Nếu một reader có thể quan sát after-debit nhưng before-credit, nó có thể thấy tổng tiền giảm tạm thời; điều này có thể vi phạm observable invariant dù final state đúng.

## 20. Chương trình hoàn chỉnh 7 — chuyển tiền in-memory dưới một lock

Tệp **`ConcurrentTransferDemo.java`**:

~~~java
public class ConcurrentTransferDemo {
    static final class Account {
        private long balanceCents;

        Account(long initialBalance) {
            if (initialBalance < 0) {
                throw new IllegalArgumentException("negative balance");
            }
            balanceCents = initialBalance;
        }
    }

    static final class Bank {
        private final Object mutex = new Object();

        void transfer(Account from, Account to, long amount) {
            if (from == null || to == null || from == to) {
                throw new IllegalArgumentException("invalid accounts");
            }
            if (amount <= 0) {
                throw new IllegalArgumentException("invalid amount");
            }

            synchronized (mutex) {
                if (from.balanceCents < amount) {
                    throw new IllegalStateException("insufficient funds");
                }

                long targetNext =
                        Math.addExact(to.balanceCents, amount);

                from.balanceCents -= amount;
                to.balanceCents = targetNext;
            }
        }

        long balance(Account account) {
            synchronized (mutex) {
                return account.balanceCents;
            }
        }

        long total(Account first, Account second) {
            synchronized (mutex) {
                return Math.addExact(
                        first.balanceCents, second.balanceCents);
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Bank bank = new Bank();
        Account a = new Account(2_000);
        Account b = new Account(2_000);

        Thread first = new Thread(() -> {
            for (int i = 0; i < 1_000; i++) {
                bank.transfer(a, b, 1);
            }
        });

        Thread second = new Thread(() -> {
            for (int i = 0; i < 1_000; i++) {
                bank.transfer(b, a, 1);
            }
        });

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("A = " + bank.balance(a));
        System.out.println("B = " + bank.balance(b));
        System.out.println("Total = " + bank.total(a, b));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ConcurrentTransferDemo.java
java ConcurrentTransferDemo
~~~

**Stdout chính xác:**

~~~text
A = 2000
B = 2000
Total = 4000
~~~

### 20.1. Vì sao kết quả không phụ thuộc scheduling?

Mỗi thread thực hiện 1000 transfers của 1 cent theo hai hướng đối nhau. Ban đầu mỗi tài khoản có 2000, nên ngay cả khi một thread thực hiện toàn bộ trước, tài khoản nguồn vẫn không thiếu số dư. Mỗi transfer được thực hiện trọn dưới mutex; cả hai threads đã join trước khi in.

### 20.2. Vì sao targetNext tính trước mutation?

Nếu cộng vào to account gây long overflow, `Math.addExact` ném exception trước khi debit from account. Như vậy không có case “đã trừ người gửi nhưng chưa cộng người nhận” do overflow.

### 20.3. Vì sao balance()/total() cũng khóa?

Nếu chỉ transfer khóa mà getters không dùng cùng synchronization policy, readers có thể quan sát dữ liệu không nhất quán hoặc visibility không bảo đảm. Demo gom reads vào cùng monitor.

### 20.4. Giới hạn của một Bank object

Mutex nằm trong Bank. Nếu cùng hai accounts được thao tác bởi **hai Bank instances khác nhau**, chúng dùng hai mutex khác nhau và không được bảo vệ chung. Production design cần một owner/concurrency boundary duy nhất hoặc persistent transaction, không chỉ copy-paste Bank class.

### 20.5. Đây không phải database transaction

Nếu account balances được lưu trong DB, Java synchronized chỉ bảo vệ threads trong một JVM/Bank object, không chặn processes/instances khác. Cần DB isolation, lock/version checks và transaction boundaries.

## 21. Optimistic locking và version numbers

Với hệ thống lưu dữ liệu, hai requests có thể đọc cùng state version. Nếu cả hai update mà không detect conflict, một thay đổi có thể ghi đè thay đổi của request khác.

Một pattern phổ biến:

~~~text
Read aggregate:
  id=7, version=4, balance=1000

Request A:
  calculate candidate version=5

Update database:
  UPDATE accounts
  SET balance=..., version=5
  WHERE id=7 AND version=4

Affected rows = 1
  -> A đã commit.

Affected rows = 0
  -> Có conflict; đọc lại/decide retry hoặc reject.
~~~

Đây là **SQL pseudocode/transaction pattern**, không phải Java example cần chạy.

### 21.1. Version check bảo vệ điều gì?

Nó phát hiện state đã thay đổi kể từ khi người gọi đọc version. Nhờ vậy không âm thầm ghi đè concurrent updates.

### 21.2. Retry phải theo nghiệp vụ

Không phải mọi conflict đều nên tự retry vô hạn. Nếu giá, inventory, user authorization hoặc business decision đã thay, có thể cần trả conflict cho client. Với operation idempotent, retry strategy có thể khác.

### 21.3. Uniqueness phải được bảo vệ tại database khi có nhiều writers

Ví dụ Course registration có thể check student chưa có, nhưng hai requests đồng thời cùng enroll. Unique index theo (course_id, student_id) có thể bảo vệ persistent uniqueness; application code vẫn cần xử lý constraint violation và preserve capacity.

## 22. Thiết kế operation có nhiều external side effects

Một phương thức như:

~~~text
reserve inventory
charge payment gateway
save order
send confirmation email
~~~

trông như một operation nghiệp vụ đơn lẻ, nhưng **không phải tất cả tác động có thể rollback bằng Java exception**.

### 22.1. Tách quyết định nghiệp vụ và điều phối hạ tầng

- Domain entity/value objects bảo vệ local invariants và state transitions.
- Application service điều phối use case, load/save aggregates, gọi gateway và transaction boundary.
- Infrastructure adapters thực hiện persistence, messaging, payment API.
- Khi operations vượt một database, cân nhắc idempotency keys, compensating actions, saga/outbox hoặc trạng thái trung gian hợp lệ.

### 22.2. Đừng “pay trước rồi validate”

Nếu trạng thái đơn không thể được thanh toán, code phải phát hiện trước khi charge khi có thể. Nhưng ngay cả khi validate trước, concurrent state change hoặc network failure vẫn có thể xảy ra. External operation cần cơ chế xác thực/commit phù hợp, không chỉ `if`.

### 22.3. Domain event không là transaction commit

Một domain event `OrderPaid` có thể mô tả chuyển trạng thái hợp lệ. Nhưng publish event trước khi DB commit có thể khiến downstream xử lý một state chưa tồn tại. Outbox/transactional messaging là các patterns giải quyết consistency giữa state và message.

### 22.4. Không gọi trạng thái tạm là “sai” nếu domain cho phép

Nếu cần `PAYMENT_PENDING`, `RESERVATION_PENDING` hoặc `COMPENSATION_REQUIRED`, hãy mô hình hóa chúng là các trạng thái nghiệp vụ hợp lệ có hành vi xử lý rõ. Invariant không có nghĩa chỉ được phép trạng thái cuối cùng.

## 23. Khoảng thời gian không chồng lấn: đặt thao tác thay vì sửa start/end tự do

Một hệ thống đặt phòng có thể yêu cầu:

- Start trước end.
- Cùng một phòng không có hai lịch đặt chồng lấn.
- Dùng interval dạng **[start, end)**: đầu gồm, cuối không gồm.
- Hai lịch `[09:00,10:00)` và `[10:00,11:00)` **không chồng lấn**.

Nếu cho phép `setStart` và `setEnd` tự do trên từng booking, caller có thể tạo khoảng thời gian đảo ngược hoặc xung đột mà không được kiểm tra.

### 23.1. Tách immutable interval value và BookingBook owner

- `TimeSlot` record validate start < end.
- `RoomSchedule` kiểm tra overlap trên danh sách reservations hiện có.
- `book(slot)` chỉ thêm khi không overlap.
- Không expose mutable List nội bộ.

### 23.2. Overlap formula

Hai half-open intervals A=[aStart,aEnd) và B=[bStart,bEnd) chồng lấn khi:

~~~text
aStart < bEnd  AND  bStart < aEnd
~~~

Với LocalDateTime, dùng `isBefore` cho so sánh strictly less. Các trường hợp start trùng end thuộc “touching boundary” nên không overlap.

## 24. Chương trình hoàn chỉnh 8 — lịch đặt không chồng lấn

Tệp **`BookingInvariantDemo.java`**:

~~~java
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

public class BookingInvariantDemo {
    record Slot(LocalDateTime start, LocalDateTime end) {
        Slot {
            if (start == null || end == null || !start.isBefore(end)) {
                throw new IllegalArgumentException("invalid interval");
            }
        }

        boolean overlaps(Slot other) {
            return start.isBefore(other.end)
                    && other.start.isBefore(end);
        }
    }

    static final class Schedule {
        private final List<Slot> bookings = new ArrayList<>();

        boolean book(Slot candidate) {
            if (candidate == null) {
                throw new IllegalArgumentException("null slot");
            }
            for (Slot existing : bookings) {
                if (existing.overlaps(candidate)) {
                    return false;
                }
            }
            bookings.add(candidate);
            return true;
        }

        int count() {
            return bookings.size();
        }
    }

    static LocalDateTime at(int hour, int minute) {
        return LocalDateTime.of(2026, 1, 1, hour, minute);
    }

    public static void main(String[] args) {
        Schedule schedule = new Schedule();

        System.out.println("First = " + schedule.book(
                new Slot(at(9, 0), at(10, 0))));

        System.out.println("Overlap = " + schedule.book(
                new Slot(at(9, 30), at(10, 30))));

        System.out.println("Touching = " + schedule.book(
                new Slot(at(10, 0), at(11, 0))));

        System.out.println("Bookings = " + schedule.count());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 BookingInvariantDemo.java
java BookingInvariantDemo
~~~

**Stdout chính xác:**

~~~text
First = true
Overlap = false
Touching = true
Bookings = 2
~~~

### 24.1. Vì sao 09:30–10:30 bị từ chối?

Khoảng mới [09:30,10:30) chồng với [09:00,10:00). Hàm `overlaps` trả true nên Schedule không thêm booking.

### 24.2. Vì sao 10:00–11:00 hợp lệ?

Hai intervals chạm nhau ở 10:00 nhưng half-open convention loại trừ endpoint cuối của lịch đầu, nên không overlap.

### 24.3. Đoạn mã chưa xử lý timezone/DST và concurrency

Demo dùng LocalDateTime trong một context giả định đồng nhất. Hệ thống thực có thể cần ZonedDateTime/Instant, chính sách timezone/DST và database locking/unique exclusion constraint để tránh hai requests đồng thời đặt trùng.

### 24.4. Vì sao business method tốt hơn setStart/setEnd?

`book` kiểm tra toàn bộ set of existing slots trước commit. Một setter trên một booking đơn lẻ không đủ thông tin để giữ schedule-wide no-overlap invariant.

## 25. Validation ở boundary và validation trong domain khác nhau như thế nào?

REST/API/UI thường phải kiểm tra cú pháp và trải nghiệm:

- JSON thiếu trường.
- Date string không parse được.
- Số điện thoại sai định dạng.
- Form cần hiển thị nhiều errors một lần.

Domain phải bảo vệ những luật vẫn đúng dù dữ liệu tới từ UI, batch import, message consumer hay internal API:

- Amount dương.
- Không rút quá số dư.
- Chỉ ship một đơn đã paid.
- Không vượt capacity.
- Không có lịch đặt chồng lấn.

### 25.1. Duplicate validation có phải lãng phí?

Không nhất thiết. Boundary validation giúp UX và chống input bất hợp lệ sớm. Domain validation giữ object nhất quán nếu boundary khác bị quên; database constraints giữ persistent invariant trước concurrent writers. Mỗi tầng có trách nhiệm khác nhau.

### 25.2. Nếu rule thuộc policy cấu hình, object nào kiểm tra?

Bạn có thể truyền `WithdrawalPolicy`/`PricingPolicy` vào domain operation thay vì hard-code. Nhưng khi policy có thể thay đổi theo thời gian, operation cần rõ policy version/time và đảm bảo state commit theo kết quả đã xác nhận.

### 25.3. Không làm Entity phụ thuộc trực tiếp framework

Một entity đơn giản có thể dùng constructors, standard exceptions và value objects. Không cần HTTP status code, servlet request hay DB connection bên trong method `withdraw`. Application layer map domain failures sang transport responses.

## 26. Invariant khó phá nhờ types

Một cách mạnh để giảm lỗi là tạo **kiểu dữ liệu mô tả giá trị hợp lệ**, thay vì truyền primitive/String khắp nơi.

Ví dụ:

~~~java
record StudentId(String value) {
    StudentId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("blank student id");
        }
    }
}

record PositiveQuantity(int value) {
    PositiveQuantity {
        if (value <= 0) {
            throw new IllegalArgumentException("qty <= 0");
        }
    }
}
~~~

Đây là **record declaration fragments**. Một method `reserve(Sku sku, PositiveQuantity qty)` không cần nhận arbitrary negative integer theo typed API, vì PositiveQuantity constructor từ chối.

### 26.1. Types giảm số lần kiểm tra nhưng không thay domain state guards

Một PositiveQuantity bảo đảm qty>0, nhưng Inventory vẫn phải kiểm tra current stock >= qty. Kiểu value object bảo vệ rule về **giá trị**, còn aggregate operation bảo vệ rule về **mối quan hệ giữa trạng thái và hành động**.

### 26.2. Enum không tự giữ state transitions

`enum Status {DRAFT, PAID, SHIPPED}` chỉ tạo constants. Nếu object có public setStatus, trạng thái trái quy trình vẫn xuất hiện được. Cần methods có transition guards hoặc một typestate API nếu complexity xứng đáng.

### 26.3. Sealed result types có thể biểu diễn outcomes

Ví dụ (conceptual):

~~~java
sealed interface ReservationResult
        permits Reserved, Rejected {
}

record Reserved(String confirmationId)
        implements ReservationResult {
}

record Rejected(String reason)
        implements ReservationResult {
}
~~~

Những record values có thể làm kết quả nghiệp vụ rõ hơn boolean, khi caller cần lý do và payload. Tuy nhiên không dùng sealed hierarchy rườm rà nếu enum nhỏ là đủ.

## 27. Idempotency: lặp lệnh có làm sai trạng thái không?

Một operation idempotent thỏa ý tưởng: thực hiện lại cùng ý định không tạo thêm side effect mới ngoài lần đầu theo contract.

Ví dụ `close()` thường được **thiết kế** idempotent trong các custom resources; `markDelivered(orderId)` có thể được thiết kế trả cùng kết quả nếu đã giao, tùy domain. Nhưng không phải mọi `AutoCloseable.close` implementation bắt buộc idempotent, và “lặp giao dịch chuyển tiền” chắc chắn cần phân biệt request IDs để tránh trừ tiền hai lần.

### 27.1. Duplicate request trên network

Client timeout có thể retry vì không biết server đã xử lý chưa. Một `transfer` không có idempotency key có thể thực hiện hai lần nếu cả hai requests tới server. Domain/API layer cần kiểm tra và lưu operation IDs trong transactional boundary.

### 27.2. Set membership và idempotency

`Course.enroll("s1")` ở ví dụ trả ALREADY_ENROLLED khi gọi lại. Nó không thêm bản ghi trùng nên state-change idempotent, dù return value của lần đầu và lần sau khác nhau. Hãy mô tả chính xác semantics của kết quả.

### 27.3. Không “swallow” errors để giả idempotent

Nếu một thao tác fail do DB outage, âm thầm trả success chỉ vì status hiện có gần đúng có thể che sự cố. Idempotency phải có durable record/version/identity phù hợp khi đi qua nhiều processes.

## 28. Testing: chứng minh invariant qua chuỗi thao tác, không chỉ happy path

Một bộ test tốt gồm:

1. Constructor nhận input hợp lệ.
2. Constructor từ chối input bất hợp lệ.
3. Các business operations thành công và tạo postcondition đúng.
4. Các precondition violations bị từ chối.
5. State **không đổi** sau một rejected operation.
6. Các transitions không hợp lệ (ví dụ ship trước pay) bị chặn.
7. Collections trả ra không cho caller bypass invariant.
8. Value objects validate amount/quantity/currency.
9. Multiple-field operations thất bại không để partial mutation.
10. Concurrent operations không làm mất update hoặc phá tổng/limit.
11. Persistence conflicts và rollback giữ DB invariants.
12. External side effects có idempotency và failure handling.

### 28.1. Test dạng “Given–When–Then”

~~~text
Given:
  balance = 1000 cents

When:
  withdraw(1200)

Then:
  IllegalStateException (insufficient funds)
  balance vẫn = 1000
~~~

Đây là **test specification**, không phải Java source.

### 28.2. Test state transitions dạng ma trận

| Trạng thái hiện tại | Lệnh | Kết quả kỳ vọng |
| --- | --- | --- |
| DRAFT | addLine | Hợp lệ |
| DRAFT có lines | pay | → PAID |
| DRAFT trống | pay | Reject, vẫn DRAFT |
| DRAFT | ship | Reject |
| PAID | ship | → SHIPPED |
| PAID | addLine | Reject |
| SHIPPED | cancel | Reject |
| CANCELLED | pay | Reject |

Một bảng trạng thái giúp phát hiện nhánh “được phép nhưng quên cấm” dễ hơn chỉ viết test cho happy path.

### 28.3. Property-based tests

Với Account:

- Tạo số dư ban đầu không âm.
- Sinh chuỗi deposit/withdraw input ngẫu nhiên.
- Sau mỗi successful operation, assert balance>=0.
- Nếu operation bị reject, assert balance unchanged.
- Với transfer, assert total balance bảo toàn khi cả hai accounts thuộc một operation.

Với Inventory, assert mọi SKU quantity>=0 sau chuỗi additions/reservations.

### 28.4. Mutation testing

Nếu xóa guard `amount <= balance` mà tests vẫn pass, test suite có lỗ hổng. Mutation testing có thể phát hiện thiếu negative-path checks và invariants không được kiểm thử.

### 28.5. Concurrency tests không chỉ “chạy nhiều threads cho may”

Kết quả flaky không chứng minh algorithm đúng hoặc sai hoàn toàn. Nên dùng stress tests với deterministic invariants, concurrency testing tools, code review theo Java memory model và database isolation tests tương ứng.

## 29. Chương trình hoàn chỉnh 9 — bảng kiểm thử invariants đơn giản không cần JUnit

Tệp **`InvariantContractTestDemo.java`**:

~~~java
public class InvariantContractTestDemo {
    static final class Counter {
        private final int max;
        private int value;

        Counter(int max) {
            if (max <= 0) {
                throw new IllegalArgumentException("invalid maximum");
            }
            this.max = max;
        }

        void increment() {
            if (value >= max) {
                throw new IllegalStateException("limit reached");
            }
            value++;
        }

        void decrement() {
            if (value <= 0) {
                throw new IllegalStateException("already zero");
            }
            value--;
        }

        int value() {
            return value;
        }
    }

    static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        Counter counter = new Counter(2);

        require(counter.value() == 0, "initial");
        counter.increment();
        counter.increment();
        require(counter.value() == 2, "after increment");

        try {
            counter.increment();
            throw new AssertionError("expected exception");
        } catch (IllegalStateException ex) {
            require(counter.value() == 2, "failed increment changed state");
        }

        counter.decrement();
        require(counter.value() == 1, "after decrement");

        System.out.println("All invariant checks passed");
        System.out.println("Final value = " + counter.value());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 InvariantContractTestDemo.java
java InvariantContractTestDemo
~~~

**Stdout chính xác:**

~~~text
All invariant checks passed
Final value = 1
~~~

### 29.1. Vì sao không dùng từ khóa assert?

Java `assert` statements có thể bị disable khi không bật `-ea`. Demo dùng explicit `require` ném AssertionError khi test invariant fail, nên kết quả kiểm thử không phụ thuộc JVM assertion flag.

### 29.2. Verify failure atomicity, không chỉ exception

Sau lần increment thứ ba bị reject, demo xác nhận `counter.value()==2`. Chỉ assert exception được ném là chưa đủ: một implementation tệ có thể tăng lên 3 rồi mới ném.

### 29.3. Vì sao không dùng setter?

Counter chỉ có increment/decrement, làm rõ invariant `0 <= value <= max`. Public setter cho arbitrary value sẽ làm nhiều test case lỗi hơn và trao trách nhiệm bảo vệ state cho caller.

## 30. Những lỗi thiết kế phổ biến và cách sửa

1. **Fields private nhưng mở setters vô điều kiện.** Đóng gói vẫn bị phá qua API; thay bằng business commands với guards.
2. **Validation chỉ ở controller.** Đặt invariant quan trọng trong domain owner; controller vẫn validate UX.
3. **Gán fields rồi mới kiểm tra.** Validate candidate state trước commit.
4. **Mutate từng mục trước khi biết cả batch hợp lệ.** Dùng prepare-then-commit/transaction.
5. **Trả mutable internal List/Map.** Trả snapshot/projection hoặc chỉ cho business methods.
6. **List.copyOf chứa mutable elements vẫn có thể bị mutate.** Xem object ownership/deep copy khi cần.
7. **Tổng tiền là field được set độc lập với order lines.** Derived value hoặc cập nhật atomic theo invariant.
8. **Status enum nhưng vẫn có setStatus công khai.** Dùng state transition methods.
9. **Chấp nhận số dư âm vì nghĩ database tự chặn.** Domain check để API luôn bảo vệ semantics; DB constraint là defense in depth.
10. **Dùng double cho tiền mà không hiểu rounding.** Dùng cents/BigDecimal/Money value object có currency policy.
11. **Không kiểm tra arithmetic overflow.** `Math.addExact`/`multiplyExact` hoặc BigDecimal theo domain.
12. **Invalid constructor cho tạo object rồi yêu cầu caller sửa sau.** Validate từ construction; dùng factory/builder nếu creation nhiều bước.
13. **Dùng builder tạo incomplete object có thể dùng ở ngoài.** Builder có thể mutable tạm thời, nhưng `build()` phải reject invalid final state.
14. **Catch mọi Exception rồi return false.** Mất thông tin business vs infrastructure/bug.
15. **Tùy ý quăng checked exceptions từ getter để che invalid state.** Nên ngăn invalid state từ construction/operation.
16. **Cho cùng object cập nhật từ nhiều threads mà không đồng bộ check+update.** Dùng lock/CAS/serialization theo policy.
17. **Chỉ lock setter, getter đọc không lock.** Readers có thể thấy state trung gian/visibility sai.
18. **Một lock per service instance nhưng state dùng chung giữa services.** Cần real concurrency boundary.
19. **Dùng Java lock để thay DB transaction.** Không bảo vệ các writers ở process khác.
20. **Cho transaction gồm nhiều external services nhưng hứa rollback tuyệt đối.** Cần saga/outbox/idempotency/compensation semantics.
21. **Nhầm business rejection với invalid parameter.** Chọn error/result types rõ.
22. **Tự động retry lệnh không idempotent.** Có thể trừ tiền hai lần.
23. **Không xử lý duplicate request.** Dùng operation identity/unique constraints khi cần.
24. **Không bảo vệ null fields/mutable alias.** Tạo value object, requireNonNull, defensive copy phù hợp.
25. **Làm aggregate quá lớn.** Mọi command phải khóa một “God Object”, khó scale.
26. **Đặt tất cả rule trong service còn entity chỉ chứa public setters.** Làm rõ aggregate owner để entity tự giữ local invariants.
27. **Nhầm getter-only API là immutable deep.** Referent vẫn có thể mutable.
28. **Thiếu test negative-path.** Một trạng thái invalid có thể tồn tại dù happy path pass.
29. **Test có exception nhưng không assert state unchanged.** Có thể bỏ sót partial mutation.
30. **Phát event trước khi persistence commit.** Consumer có thể thấy event không có committed data.
31. **Không định nghĩa chính sách thay đổi/trạng thái trung gian.** Code chuyển trạng thái tùy tiện không thể review đầy đủ.
32. **Để collection duplicate entries làm sai rule.** Dùng Set/unique key nhưng vẫn cần capacity/state guards.
33. **Tự normalize input trong getter khiến equals/toString dùng raw state.** Normalize tại constructor khi đó là data invariant.
34. **Dùng mutable entity làm HashMap key.** Thay đổi fields ảnh hưởng equals/hashCode có thể phá lookup.
35. **Thiết kế methods đặt tên chung `update`/`process` mà không có contract.** Chia thành các hành động nghiệp vụ rõ và testable.

## 31. Quy trình ra quyết định khi thêm một thao tác nghiệp vụ

Khi muốn viết method mới trong một entity/aggregate, tự trả lời:

**Bước 1 — Mô tả ý định:** Method thực hiện điều gì trong ngôn ngữ của domain? `approve`, `reserve`, `cancel`... thay vì `setFlag(true)`.

**Bước 2 — Xác định owner:** Object/aggregate nào có đủ state để xác thực rule? Rule có cần DB/service bên ngoài không?

**Bước 3 — Liệt kê preconditions:** Input type, bounds, current state, permission/context, version.

**Bước 4 — Liệt kê invariants:** Những quan hệ giữa fields nào phải vẫn đúng? Có multi-entity invariants không?

**Bước 5 — Xây candidate:** Tính state mới trước khi gán; xác định các failure paths.

**Bước 6 — Commit có kiểm soát:** Mutate nội bộ dưới concurrency/transaction boundary thích hợp.

**Bước 7 — Xử lý side effects:** Events, emails, gateways theo outbox/idempotency/compensation policy nếu cần.

**Bước 8 — Thiết kế result/errors:** Thành công trả gì, lỗi nghiệp vụ có loại nào, có retry được không?

**Bước 9 — Viết tests:** Happy path, rejection, unchanged-on-failure, concurrency, persistence, external failures.

**Bước 10 — Review public escape hatches:** Có exposed collections/setters/reflection mappers cho bypass rules không?

## 32. Câu hỏi ôn tập có đáp án

**Câu 1.** Invariant của đối tượng là gì?

**Đáp án:** Điều kiện phải đúng trong mọi trạng thái hợp lệ của object/aggregate, ví dụ balance>=0.

**Câu 2.** Invariant có nghĩa fields không được thay đổi không?

**Đáp án:** Không; state có thể thay đổi miễn điều kiện invariant tiếp tục đúng.

**Câu 3.** Có đủ nếu mọi field là private nhưng có setBalance(long) không kiểm tra?

**Đáp án:** Không. Setter vẫn cho phá invariant từ public API.

**Câu 4.** Vì sao withdraw có ý nghĩa hơn setBalance?

**Đáp án:** Nó biểu diễn hành động nghiệp vụ, biết amount và current balance, có thể validate và bảo vệ postcondition.

**Câu 5.** Constructor cần kiểm tra gì?

**Đáp án:** Inputs/invariants ban đầu, tránh tạo instance không hợp lệ.

**Câu 6.** Nếu withdraw thiếu tiền, điều gì phải xảy ra?

**Đáp án:** Reject theo contract và giữ balance unchanged.

**Câu 7.** Vì sao dùng Math.addExact khi cộng long cents?

**Đáp án:** Bắt overflow trước khi gán state mới.

**Câu 8.** Một enum Status có tự giới hạn transitions không?

**Đáp án:** Không; nó chỉ định nghĩa constants. Entity methods phải bảo vệ các cạnh hợp lệ.

**Câu 9.** Tại sao không dùng public setStatus?

**Đáp án:** Cho phép bypass các điều kiện như pay trước ship.

**Câu 10.** Order lines và total phải liên hệ thế nào?

**Đáp án:** Total suy ra hoặc được cập nhật nhất quán với lines; tránh setter riêng tạo mâu thuẫn.

**Câu 11.** Nếu Order trả ArrayList nội bộ qua getter, nguy cơ gì?

**Đáp án:** Caller có thể thêm/xóa lines không qua guards và phá state invariant.

**Câu 12.** List.copyOf có luôn deep-copy elements không?

**Đáp án:** Không; chỉ tạo unmodifiable structural representation, mutable elements vẫn cần ownership policy.

**Câu 13.** Một inventory.reserve với ba SKU nên check thế nào?

**Đáp án:** Validate toàn bộ request và stock đủ trước khi commit batch.

**Câu 14.** Failure atomicity trong domain method là gì?

**Đáp án:** Nếu operation bị reject/fail theo contract, object không bị bỏ lại trong trạng thái cập nhật một phần.

**Câu 15.** Java exception tự rollback field assignments không?

**Đáp án:** Không.

**Câu 16.** Constructor của Quantity record giúp gì?

**Đáp án:** Reject non-positive quantity từ thời điểm tạo value object.

**Câu 17.** Money.plus USD với EUR nên làm gì nếu không có tỷ giá?

**Đáp án:** Reject hoặc yêu cầu conversion policy rõ ràng, không âm thầm cộng.

**Câu 18.** BigDecimal tự quyết định chính sách thuế/làm tròn không?

**Đáp án:** Không. Domain phải chọn scale/rounding/currency semantics.

**Câu 19.** Course capacity invariant là gì?

**Đáp án:** enrolledCount<=capacity cùng uniqueness nếu cần.

**Câu 20.** Set tự giữ capacity invariant không?

**Đáp án:** Không, Set chỉ giúp uniqueness; enroll phải check capacity.

**Câu 21.** Vì sao Course.enroll trả ALREADY_ENROLLED trước FULL?

**Đáp án:** Cho retries cùng student không bị báo FULL khi đã đăng ký; đây là policy có chủ đích.

**Câu 22.** Một method đúng ở single thread có chắc đúng với nhiều threads không?

**Đáp án:** Không; check-then-act có thể race.

**Câu 23.** Volatile có làm withdraw check+subtract atomic không?

**Đáp án:** Không.

**Câu 24.** synchronized bảo vệ phạm vi nào trong ví dụ Bank?

**Đáp án:** Những operations dùng chung một Bank.mutex; nó không tự bảo vệ các processes hoặc Bank objects khác.

**Câu 25.** Vì sao transfer phải tính số dư người nhận mới trước debit?

**Đáp án:** Để overflow không gây debit một phần.

**Câu 26.** Nếu database có nhiều writers, synchronized trong một JVM đủ không?

**Đáp án:** Không; cần database transaction/isolation/constraints.

**Câu 27.** Optimistic locking thường dùng gì?

**Đáp án:** Version check/conditional update để phát hiện concurrent conflict.

**Câu 28.** Phát email rồi ném exception có rollback email được bằng khôi phục field không?

**Đáp án:** Không; external side effects cần idempotency/compensation/process design.

**Câu 29.** Booking interval [09:00,10:00) và [10:00,11:00) chồng lấn không?

**Đáp án:** Không theo half-open interval convention.

**Câu 30.** Ai giữ invariant không chồng lịch: Booking hay Schedule?

**Đáp án:** Booking/Slot validate start<end; Schedule biết các bookings khác nên bảo vệ no-overlap rule.

**Câu 31.** Validation ở controller có thay domain validation không?

**Đáp án:** Không; controller phục vụ input/UX, domain bảo vệ invariant bất kể entry point.

**Câu 32.** Database unique constraint có thay business logic không?

**Đáp án:** Không hoàn toàn; nó bổ sung bảo vệ persistent state/concurrency.

**Câu 33.** Idempotency quan trọng với transfer vì sao?

**Đáp án:** Network retries có thể thực hiện cùng yêu cầu hai lần nếu không nhận diện operation ID.

**Câu 34.** Test chỉ assert exception, không assert state unchanged có đủ không?

**Đáp án:** Không; implementation có thể mutate rồi ném exception.

**Câu 35.** Bảo vệ invariant có nghĩa không bao giờ dùng generic setter cho DTO không?

**Đáp án:** Không; object đơn thuần vận chuyển dữ liệu có thể dùng setters, còn domain behavior cần guards phù hợp.

**Câu 36.** “Fail fast” và “atomic failure” có giống nhau không?

**Đáp án:** Không. Fail fast từ chối sớm; atomic failure còn yêu cầu không để state bị cập nhật một phần nếu fail.

**Câu 37.** Bất biến nội bộ của một entity và consistency xuyên aggregates giống nhau không?

**Đáp án:** Không; cross-aggregate rules có thể cần transactions/sagas và policy khác.

**Câu 38.** Vì sao có thể cần snapshot List?

**Đáp án:** Để caller không mutate internal collection và bypass business checks.

**Câu 39.** Có thể dùng sealed result type cho outcomes không?

**Đáp án:** Có khi cần phân biệt success/failure variants với payload rõ ràng.

**Câu 40.** Quy tắc nhớ lâu nhất của bài?

**Đáp án:** **Chỉ công khai hành động có ý nghĩa nghiệp vụ; kiểm tra trước khi commit; giữ invariant đúng sau thành công và giữ state unchanged khi bị từ chối; bảo vệ collection aliases và concurrency/persistence boundaries.**

## 33. Bài tập thực hành

### Bài 1 — sửa anemic BankAccount

Cho class có `getBalance/setBalance`, chuyển sang `deposit/withdraw`. Áp dụng validation amount>0, balance>=0, Math.addExact. Viết tests cho số dư, negative inputs, insufficient funds và unchanged-on-failure.

### Bài 2 — state machine đơn hàng

Thiết kế enum DRAFT, PAID, SHIPPED, CANCELLED. Viết methods addLine/pay/ship/cancel theo state guards và bảng chuyển trạng thái. Test tất cả invalid transitions. Không để public setStatus.

### Bài 3 — inventory batch reservation

Nhận Map<Sku,Quantity> để reserve. Nếu bất kỳ SKU thiếu, không trừ SKU nào. Dùng prepare-then-commit, tests với lỗi ở đầu và cuối request, overflow, empty input.

### Bài 4 — Course capacity

Mỗi Course có capacity và Set<StudentId>. Đăng ký trùng trả ALREADY_ENROLLED, đủ chỗ trả FULL, thành công trả ENROLLED. Thêm concurrent test và phân tích cần lock/DB constraints ở đâu.

### Bài 5 — immutable Money

Tạo record Money(BigDecimal, Currency) với invariant amount nonnegative, scale và cùng currency khi plus. Test invalid amount, different currency và equality/value semantics.

### Bài 6 — defensive copy

Tạo class Team có mutable List<ImmutableMember>. Không expose internal List; trả snapshot. Thử caller.add vào snapshot và xác nhận không thể vượt capacity.

### Bài 7 — hai accounts và concurrency

Thực hiện chuyển tiền đa luồng, assert tổng bảo toàn và balances không âm sau mỗi operation theo synchronization strategy. Sau đó phân tích vì sao cùng code không bảo vệ nhiều JVM instances.

### Bài 8 — lịch đặt phòng

Tạo TimeSlot(start,end) validate start<end, RoomSchedule.book validate no-overlap với half-open intervals. Test các khoảng chạm mép và overlap, cùng mô hình database conflict khi hai bookings đến đồng thời.

### Bài 9 — external payment use case

Mô hình trạng thái PAYMENT_PENDING/PAID/PAYMENT_FAILED, idempotency key và sự khác nhau giữa domain decision và payment gateway call. Phác thảo outbox/compensation strategy thay vì hứa rollback một email hoặc external charge.

## 34. Checklist cuối bài

1. Mỗi object có các invariants được mô tả rõ chưa?
2. Constructors/factories có tạo trạng thái hợp lệ không?
3. Public API có các business methods thay arbitrary setters chưa?
4. Mỗi operation có precondition và postcondition cụ thể không?
5. Có validate toàn bộ input/candidate trước mutation không?
6. Failure paths có bảo toàn old state không?
7. Có arithmetic overflow hoặc rounding risk không?
8. Các derived fields có thể mất nhất quán với source fields không?
9. State machine có bảo vệ toàn bộ transitions không?
10. Có điều kiện trùng lặp/capacity/uniqueness không?
11. Collections có bị lộ mutable references không?
12. Value objects/components có immutable/defensive copies phù hợp không?
13. Có aggregate root đủ thông tin để kiểm tra invariant không?
14. Business rules có bị rải khắp UI/controller không?
15. Errors có phân biệt validation, business rejection và infrastructure không?
16. Có concurrency race giữa check và update không?
17. Readers có nhìn được inconsistent intermediate state không?
18. Có lock/atomic snapshot/DB transaction phù hợp không?
19. Có optimistic version hoặc unique constraint khi persistent concurrent writers không?
20. External calls có idempotency/compensation/outbox strategy không?
21. Có tests cho rejected operation giữ nguyên state không?
22. Có tests toàn bộ state transitions không?
23. Có property-based tests cho nhiều chuỗi operations không?
24. Có audit/logging cho business actions có nghĩa không?
25. Có ownership policy khi trạng thái liên quan listeners, resource pools hoặc collections không?
26. Có tránh “God Aggregate” quá lớn không?
27. Có dùng immutable value objects cho các đại lượng đặc biệt không?
28. Có document rule assumptions: currency, timezone, concurrency, refund, capacity không?
29. Có test với boundary values: zero, max, empty, duplicate, null không?
30. Có thể giải thích với người nghiệp vụ tại sao method bị từ chối và invariant nào được bảo vệ không?

## 35. Kết luận

Một class chỉ có **private fields và public setters** chưa đủ để bảo vệ mô hình nghiệp vụ. Thiết kế hướng đối tượng tốt phải đưa **trạng thái, quy tắc hợp lệ và những thao tác được phép** vào cùng một boundary có trách nhiệm. Thay `setBalance` bằng `deposit/withdraw`, thay `setStatus` bằng `pay/ship/cancel`, thay sửa map kho trực tiếp bằng `reserve`, thay chỉnh danh sách lớp bằng `enroll` là cách biến business rules từ lời hứa thành các preconditions/postconditions có thể kiểm chứng.

Nguyên tắc thực thi cơ bản là **validate trước, tính candidate, rồi commit**; khi một thao tác bị từ chối, trạng thái vẫn hợp lệ và lý tưởng là không đổi. Đừng để caller bỏ qua các quy tắc qua mutable collections hoặc setters quá tổng quát. Dùng value objects để loại bỏ giá trị sai từ đầu, state machines để giới hạn transitions, và aggregate roots để giữ các fields liên quan nhất quán.

Cuối cùng, phạm vi đảm bảo phải nói rõ: code đúng đơn luồng chưa chắc thread-safe; synchronized trong một JVM không thay database transaction; sửa fields không rollback được email/gateway calls. Khi invariants đi qua nhiều objects, threads, processes hoặc external systems, bổ sung concurrency control, versioning, constraints, idempotency và transaction/outbox/compensation patterns tương ứng.

**Thông điệp cốt lõi:** hãy khiến hành động đúng trở thành API tự nhiên nhất, hành động sai bị từ chối tại nơi sở hữu trạng thái, và mọi state transition đều giữ các quy tắc hợp lệ của đối tượng.
