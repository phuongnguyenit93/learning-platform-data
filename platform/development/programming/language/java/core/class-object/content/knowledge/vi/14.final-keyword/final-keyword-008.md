# Khi nào nên dùng `final` để diễn đạt ý định thiết kế trong Java

**`final`** là một trong những từ khóa quan trọng nhất để viết Java có **hợp đồng thiết kế rõ ràng**. Không chỉ để compiler ngăn một phép gán hay một lần ghi đè method, `final` còn truyền đạt cho người đọc rằng: *giá trị hoặc hành vi này đã được xác định ở một ranh giới nhất định, và code khác không nên thay nó theo cách trái với thiết kế*.

Nhưng ý nghĩa chính xác phụ thuộc vào nơi bạn đặt từ khóa:

- **Final field:** field được gán theo các quy tắc khởi tạo của Java, không được gán lại tùy ý sau đó.
- **Final local variable / parameter:** biến cục bộ hoặc tham số không được gán lại sau khi đã được gán hợp lệ.
- **Final instance method:** subclass không được **override** method ấy.
- **Final class:** không thể khai báo subclass mở rộng class ấy.
- **`static final` field:** field gắn với class và không được gán lại theo quy tắc `final`; thường dùng cho constants, nhưng **không phải mọi `static final` reference đều trỏ đến dữ liệu bất biến**.

Bài này giải thích **khi nào nên sử dụng và khi nào không nên sử dụng `final`**, dựa trên Java 17+, theo góc nhìn lập trình hướng đối tượng: bảo vệ *invariants*, ổn định identity, làm rõ quyền sở hữu, hạn chế điểm mở rộng, thiết kế API, hiệu ứng của mutable references và concurrency. Các ví dụ độc lập có hướng dẫn chạy và stdout để kiểm tra.

## 1. Đọc đúng ý nghĩa của `final` theo vị trí

| Khai báo | Ý định thể hiện | `final` **không** tự đảm bảo |
| --- | --- | --- |
| `private final String id;` | Field identity không bị gán lại sau khởi tạo | Nội dung không null hoặc đúng nghiệp vụ nếu constructor không validate |
| `private final List<Item> items;` | Field luôn giữ cùng một tham chiếu sau khởi tạo | List và Item bên trong không bị sửa |
| `final int count = 3;` | Local `count` không được gán lại | Mọi phép tính liên quan đều đúng |
| `void send(final Request request)` | Parameter `request` không bị gán lại trong body | Method không sửa object Request |
| `public final void process()` | Subclass không override `process()` | Mọi implementation khác trong hệ thống đều không thể có hành vi khác |
| `public final class Money` | Không được `extends Money` | Object Money là immutable hay thread-safe nếu có mutable fields |
| `public static final int MAX = 10;` | Giá trị gắn với class, có quyền gán bị giới hạn | Value luôn phù hợp nhu cầu phiên bản khác của API |

Vì vậy, **final là ràng buộc của ngôn ngữ, còn bất biến nghiệp vụ là ràng buộc của thiết kế**. Hai việc bổ trợ nhưng không thay thế nhau.

Ví dụ:

~~~java
class Customer {
    private final String id;
    private String displayName;

    Customer(String id, String displayName) {
        this.id = java.util.Objects.requireNonNull(id, "id");
        this.displayName =
                java.util.Objects.requireNonNull(displayName, "displayName");
    }

    String id() {
        return id;
    }

    void rename(String nextName) {
        if (nextName == null || nextName.isBlank()) {
            throw new IllegalArgumentException("Tên trống");
        }
        displayName = nextName;
    }
}
~~~

Đây là **đoạn khai báo class**, chưa có `main`. `id` được thiết kế là **identity ổn định** của Customer, còn `displayName` được phép thay đổi theo hành vi `rename`. Không cần `final` cho mọi field để được coi là hướng đối tượng đúng.

## 2. Dùng `final` cho trạng thái phải ổn định sau khi tạo object

Trường hợp rõ ràng nhất là một giá trị **được xác lập một lần khi tạo object** và không có use case hợp lệ để thay nó:

- ID của đơn hàng, giao dịch hoặc entity.
- Thời điểm tạo object (*createdAt*) nếu hợp đồng xác định đây là thời điểm bất biến.
- Loại tiền tệ gắn với một amount value object.
- Cấu hình ban đầu đã chụp snapshot cho một request.
- Dependency mà instance sử dụng trong suốt vòng đời.
- Khóa phân loại hoặc thông tin cấu trúc không được đổi.

Ví dụ:

~~~java
import java.time.Instant;
import java.util.Objects;

class Invoice {
    private final String invoiceId;
    private final Instant createdAt;
    private long balanceDue;

    Invoice(String invoiceId, Instant createdAt, long balanceDue) {
        this.invoiceId = Objects.requireNonNull(invoiceId, "invoiceId");
        this.createdAt = Objects.requireNonNull(createdAt, "createdAt");
        if (balanceDue < 0) {
            throw new IllegalArgumentException("Số dư âm");
        }
        this.balanceDue = balanceDue;
    }

    String invoiceId() {
        return invoiceId;
    }
}
~~~

`String` và `Instant` là immutable types nên trả chúng không làm caller sửa nội dung instance đã lưu. `balanceDue` lại là state của hóa đơn có thể thay đổi theo các giao dịch, nên không nhất thiết final.

### 2.1. Không tạo setter cho final identity

Nếu `invoiceId` thực sự là identity, không nên tạo `setInvoiceId(...)`. Việc thay identity có thể làm sai:

- Các tham chiếu nghiệp vụ tới invoice.
- Các keys trong map hoặc dữ liệu liên kết.
- Audit log hay đường dẫn truy cập của một resource.
- Ý nghĩa của `equals/hashCode` nếu identity có tham gia.

Tuy vậy, `final` không tự xây dựng mô hình equality. Một entity vẫn cần định nghĩa quy tắc bằng nhau phù hợp với domain, còn `final` chỉ ngăn reassign field trên các đường code Java hợp lệ.

### 2.2. Chọn thời điểm khóa giá trị

`final` có thể khai báo cùng initializer:

~~~java
private final int maxRetries = 3;
~~~

hoặc là **blank final** gán trong constructor:

~~~java
private final int maxRetries;

Config(int maxRetries) {
    if (maxRetries < 0) {
        throw new IllegalArgumentException("Số lần thử âm");
    }
    this.maxRetries = maxRetries;
}
~~~

Cách thứ hai diễn đạt rằng **mỗi Config instance có giá trị cấu hình do caller lựa chọn**, nhưng giá trị đó không đổi sau khi instance được tạo thành công. Khác với một `static final` chung cho mọi Config objects.

## 3. Field `final` vẫn cần constructor validation

Compiler xác minh các quy tắc final/definite assignment, **không tự xác minh domain invariants**.

~~~java
class WrongUser {
    final String email;

    WrongUser(String email) {
        this.email = email; // Có thể null/blank/sai định dạng
    }
}
~~~

Hợp lệ về ngôn ngữ, nhưng không nhất thiết hợp nghiệp vụ. Một class bảo vệ invariant tốt hơn:

~~~java
class User {
    private final String email;

    User(String email) {
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("Email trống");
        }
        this.email = email.trim();
    }

    String email() {
        return email;
    }
}
~~~

**`final` hỗ trợ bất biến bằng cách chặn reassign field**, còn **validation bảo đảm giá trị được gán đúng hợp đồng**. Không nên chuyển một validation thành “đã final nên chắc chắn hợp lệ”.

### 3.1. Khi constructor có nhiều nhánh

Một blank final field phải được gán **đúng một lần trên mọi đường khởi tạo hoàn tất bình thường**, theo quy tắc definite assignment/definite unassignment. Có thể dùng `if/else`:

~~~java
class Channel {
    private final String endpoint;

    Channel(boolean secure) {
        if (secure) {
            endpoint = "https://example.org";
        } else {
            endpoint = "http://example.org";
        }
    }
}
~~~

Hoặc tính vào local rồi gán final một lần:

~~~java
class Channel {
    private final String endpoint;

    Channel(boolean secure) {
        String protocol = secure ? "https" : "http";
        this.endpoint = protocol + "://example.org";
    }
}
~~~

Nếu một constructor ném exception trước khi hoàn tất, đường đó không tạo object thành công. Không cần gán tất cả final fields trước khi ném; nhưng **một đường kết thúc bình thường mà field chưa được gán sẽ bị compiler từ chối**.

## 4. Dùng `final` để bảo vệ cấu trúc của object, không phải mọi dữ liệu mutable

Trong một aggregate, bạn có thể muốn **giữ nguyên tham chiếu tới collection nội bộ** nhưng cho phép thêm/xóa items theo API có kiểm soát.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

class ShoppingCart {
    private final List<String> items = new ArrayList<>();

    void addItem(String item) {
        String checked = Objects.requireNonNull(item, "item");
        if (checked.isBlank()) {
            throw new IllegalArgumentException("Mặt hàng trống");
        }
        items.add(checked);
    }

    List<String> items() {
        return List.copyOf(items);
    }
}
~~~

`final` trên field `items` ngăn class gán lại `items = new ArrayList<>()` sau khi được khởi tạo. Nhưng `items.add(...)` vẫn hợp lệ: nó sửa **List object**, không reassign field. API `addItem` kiểm soát nội dung, còn `items()` trả list không sửa được qua API.

**Khi nên dùng cách này:** vòng đời aggregate giữ cùng một collection object, nhưng phần tử có thể thay đổi có chủ đích. Nếu muốn snapshot hoàn toàn bất biến, cân nhắc dùng immutable data và tạo object mới thay vì sửa.

### 4.1. `final List` khác immutable List

~~~java
private final List<String> values =
        new java.util.ArrayList<>();
~~~

Reference `values` là final; List vẫn mutable.

~~~java
private final List<String> values =
        List.of("A", "B");
~~~

Ở đây List không sửa được qua API nhờ `List.of`, không phải nhờ keyword `final`. Với immutable String elements, trạng thái tổng thể dễ suy luận hơn.

### 4.2. Defensive copy vẫn cần thiết với input mutable

Nếu caller đưa một mảng vào constructor:

~~~java
class Scores {
    private final int[] marks;

    Scores(int[] input) {
        this.marks = input.clone();
    }

    int[] marks() {
        return marks.clone();
    }
}
~~~

Constructor clone input, getter clone output. Vì thế caller không thể thay mảng nội bộ qua alias của mảng đầu vào hoặc mảng nhận từ getter. `final` chỉ chặn **thay field tham chiếu**; clone mới chặn **chia sẻ mutable array** không mong muốn.

Nếu `input == null`, ví dụ ném NPE ở `clone()`; API thực tế nên nêu rõ hoặc validate null theo contract. Với mảng chứa mutable object references, `clone()` chỉ là **shallow copy**, không copy sâu các object phần tử.

## 5. Ví dụ hoàn chỉnh: `final` cho identity, không `final` cho state được phép thay đổi

Tạo tệp **`FinalFieldDesignDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class FinalFieldDesignDemo {
    static final class Account {
        private final String accountId;
        private final List<String> history = new ArrayList<>();
        private long balance;

        Account(String accountId, long openingBalance) {
            this.accountId = Objects.requireNonNull(
                    accountId, "accountId");
            if (accountId.isBlank()) {
                throw new IllegalArgumentException("ID trống");
            }
            if (openingBalance < 0) {
                throw new IllegalArgumentException("Số dư âm");
            }
            this.balance = openingBalance;
            history.add("OPEN:" + openingBalance);
        }

        String id() {
            return accountId;
        }

        long balance() {
            return balance;
        }

        void deposit(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("Số tiền sai");
            }
            long next = Math.addExact(balance, amount);
            balance = next;
            history.add("DEPOSIT:" + amount);
        }

        List<String> history() {
            return List.copyOf(history);
        }
    }

    public static void main(String[] args) {
        Account account = new Account("ACC-7", 100);

        account.deposit(40);
        System.out.println("ID = " + account.id());
        System.out.println("Balance = " + account.balance());
        System.out.println("History = " + account.history());

        try {
            account.deposit(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }

        System.out.println("Final balance = " + account.balance());
        System.out.println("Events = " + account.history().size());

        try {
            account.history().add("FAKE");
        } catch (UnsupportedOperationException ex) {
            System.out.println("History read-only");
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 FinalFieldDesignDemo.java
java FinalFieldDesignDemo
~~~

**Stdout chính xác:**

~~~text
ID = ACC-7
Balance = 140
History = [OPEN:100, DEPOSIT:40]
Rejected = Số tiền sai
Final balance = 140
Events = 2
History read-only
~~~

**Phân tích thiết kế:**

1. `accountId` là final: identity đã xác định khi tạo Account, không được gán lại.
2. `history` cũng là final reference: class giữ cùng một List nội bộ, nhưng có thể thêm event thông qua method `deposit`.
3. `balance` **không final** vì phải thay đổi sau những giao dịch hợp lệ.
4. `deposit` validate và dùng `Math.addExact` để tránh tràn số khi tính balance.
5. `history()` trả bản sao cấu trúc không sửa được, tránh caller tự chèn sự kiện. Ở đây phần tử là String immutable.
6. `account.history().add("FAKE")` ném `UnsupportedOperationException`; ví dụ bắt lỗi để có stdout ổn định.
7. Các final fields **không làm Account tự thread-safe** nếu nhiều thread đồng thời gọi `deposit`. Cần synchronization hoặc transaction model phù hợp trong ứng dụng thật.

**Thông điệp:** một class có thể **kết hợp final và non-final state một cách có chủ đích**. Đó thường là thiết kế tốt hơn việc gắn `final` cho toàn bộ fields mà không xem chúng thuộc loại state nào.

## 6. Dùng `final` cho dependencies không nên thay trong vòng đời đối tượng

Một object thường phụ thuộc vào một service, clock, repository hoặc strategy. Nếu dependency được cung cấp khi tạo object và **không được thay về sau**, final field diễn đạt rõ quyết định đó:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

class AuditService {
    private final Clock clock;

    AuditService(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    Instant occurredAt() {
        return clock.instant();
    }
}
~~~

Điều này phù hợp với **constructor injection**:

- Bắt buộc cung cấp dependency khi tạo.
- Không tồn tại public setter cho phép thay clock bất ngờ giữa hai lời gọi.
- Test có thể truyền `Clock.fixed(...)` để có thời gian xác định.
- Mỗi AuditService instance có thể sử dụng một clock khác nhau.

`final Clock clock` không có nghĩa Clock implementation là immutable hoặc thread-safe trong mọi trường hợp; nó chỉ cam kết field `clock` **không đổi tham chiếu** sau khi khởi tạo hợp lệ.

### 6.1. Khi dependency cần đổi

Nếu ứng dụng thực sự hỗ trợ thay strategy/configuration ở runtime, một field non-final với protocol đồng bộ rõ ràng có thể hợp lý. Hoặc giữ một final reference tới **một provider object** có API trả current configuration:

~~~java
interface ConfigurationProvider {
    String currentRegion();
}

class Client {
    private final ConfigurationProvider provider;

    Client(ConfigurationProvider provider) {
        this.provider = java.util.Objects.requireNonNull(provider);
    }

    String region() {
        return provider.currentRegion();
    }
}
~~~

`provider` không bị gán lại, nhưng **kết quả của `currentRegion()` có thể thay đổi theo thời gian**. Điều này phân biệt ổn định dependency reference với ổn định dữ liệu được dependency cung cấp.

Nếu provider state thay đổi đồng thời, phải xem chính hợp đồng thread-safety của provider; `final` ở Client không thay thế điều đó.

## 7. `final` cho local variables: khóa một phép gán khi giúp người đọc

Trong method:

~~~java
void send(String raw) {
    final String normalized = raw.trim();
    System.out.println(normalized);
}
~~~

`normalized` được gán một lần. Từ khóa `final` nói rằng giá trị local này là **kết quả đã tính xong**, không phải biến tiếp tục biến đổi qua nhiều bước.

Điều này có giá trị khi:

- Một local lưu **kết quả validation/normalization** cần dùng nhất quán ở nhiều dòng.
- Method dài, có nhiều nhánh, và việc reassign một biến vô tình sẽ khó phát hiện.
- Bạn muốn nhấn mạnh một biến là **binding ổn định** trong một khối code quan trọng.
- Trong codebase có quy ước dùng `final` cho locals ở những ranh giới logic rõ.

Nhưng không phải mọi local đều bắt buộc final:

~~~java
long sum = 0;
for (int item : numbers) {
    sum += item;
}
~~~

`sum` là **accumulator** hợp lý phải cập nhật. Ép mọi local thành final sẽ đẩy code sang nhiều wrapper hoặc biểu thức phức tạp không cần thiết. Có thể thay bằng streams nếu phù hợp, nhưng **không nên thay đổi cách viết chỉ để loại một phép gán**.

### 7.1. `final` không khiến giá trị được tính đúng hơn

~~~java
final long total = price * quantity;
~~~

Nếu `price` và `quantity` là `long`, biểu thức này vẫn có thể bị tràn số theo arithmetic rules của Java; final không kiểm tra overflow. Nếu cần phát hiện tràn, dùng `Math.multiplyExact`:

~~~java
final long total = Math.multiplyExact(price, quantity);
~~~

Ý nghĩa: **final khóa binding**, còn **logic tính toán và validation** quyết định correctness.

## 8. `final` cho parameters: khi cần khẳng định không gán lại tên tham số

Method parameter cũng có thể khai báo final:

~~~java
void register(final Customer customer) {
    // customer = new Customer(...); // Không hợp lệ: gán lại parameter
    System.out.println(customer.id());
}
~~~

Với parameter kiểu tham chiếu, final **không ngăn sửa object**:

~~~java
static void add(final List<String> names) {
    names.add("Java"); // Có thể hợp lệ nếu list mutable
    // names = new ArrayList<>(); // Không hợp lệ
}
~~~

Đây là fragment cần `import java.util.List;` hoặc tên đầy đủ.

Java **luôn truyền tham số theo giá trị**, kể cả tham chiếu. `final` không thay đổi pass-by-value thành pass-by-reference, không copy object, không làm parameter thread-safe. Nó chỉ ngăn code trong method **gán lại chính biến parameter**.

### 8.1. Vì sao có lúc nên dùng parameter final?

Một method phức tạp có thể vô tình dùng lại tên parameter cho một giá trị trung gian:

~~~java
void process(String name) {
    name = name.trim();
    // Dùng name đã thay...
}
~~~

Nếu việc giữ nguyên raw input quan trọng, có thể viết:

~~~java
void process(final String rawName) {
    final String name = rawName.trim();
    // rawName không bị gán lại; name là giá trị normalized
}
~~~

Hai tên biến truyền đạt hai vai trò: **raw input** và **normalized value**. Đây là ưu điểm về readability; không có yêu cầu phải đặt final trên mọi tham số trong Java.

### 8.2. Khi nào không nên dùng tràn lan?

Nếu method ngắn và không gán lại parameter, `final` có thể tăng lượng chữ mà không tăng nhiều thông tin. Nhóm phát triển nên chọn style nhất quán và ưu tiên **thể hiện thiết kế thực sự** hơn thay đổi cú pháp máy móc.

## 9. Lambda capture: final hoặc *effectively final*

Một local variable được lambda capture phải là **final hoặc effectively final** (không bị gán lại theo quy tắc Java).

~~~java
import java.util.function.IntUnaryOperator;

class Calculator {
    static IntUnaryOperator plus(int amount) {
        return input -> input + amount;
    }
}
~~~

`amount` không khai báo final nhưng **effectively final** vì không bị gán lại; lambda có thể sử dụng nó. Điều đó không chứng minh phải thêm keyword final.

Ví dụ không hợp lệ:

~~~java
int offset = 1;
offset++;
// java.util.function.IntUnaryOperator f = x -> x + offset;
// Lỗi: offset không còn effectively final.
~~~

Nếu cần một giá trị ổn định cho lambda, tạo một binding mới:

~~~java
int offset = 1;
offset++;

final int captured = offset;
java.util.function.IntUnaryOperator f = x -> x + captured;
~~~

Ở đây local `captured` được gán một lần sau khi hoàn tất tính toán. Việc này giúp lambda quan sát giá trị 2 đã được chốt, không phải một local mutable variable sau đó có thể đổi.

**Cẩn thận với mutable object:** một final reference đến mutable List vẫn có thể được lambda dùng để thêm/xóa phần tử. Effectively final chỉ nói về **binding của biến local**, không yêu cầu object referent immutable.

## 10. Ví dụ hoàn chỉnh: local `final`, parameter `final` và effectively final

Tạo tệp **`FinalLocalDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.IntUnaryOperator;

public class FinalLocalDemo {
    static int normalized(final int input) {
        final int safe = Math.max(input, 0);
        return safe;
    }

    static IntUnaryOperator plus(final int amount) {
        return value -> value + amount;
    }

    static void append(final List<String> values, final String item) {
        values.add(item);
        // values = new ArrayList<>(); // Lỗi: parameter final
    }

    public static void main(String[] args) {
        final String title = "Java";
        final List<String> topics = new ArrayList<>();

        append(topics, title);
        append(topics, "OOP");

        int offset = 3; // Effectively final, không gán lại
        IntUnaryOperator op = value -> value + offset;

        System.out.println("Title = " + title);
        System.out.println("Topics = " + topics);
        System.out.println("Safe = " + normalized(-5));
        System.out.println("Plus = " + plus(10).applyAsInt(2));
        System.out.println("Captured = " + op.applyAsInt(7));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 FinalLocalDemo.java
java FinalLocalDemo
~~~

Stdout chính xác:

~~~text
Title = Java
Topics = [Java, OOP]
Safe = 0
Plus = 12
Captured = 10
~~~

`title` không bị gán lại; `topics` là final reference nhưng List vẫn nhận thêm phần tử. `offset` không ghi keyword final mà vẫn được capture vì effectively final. Parameter final trong `append` không chặn `values.add(item)` khi List mutable.

Chủ đích ở đây là **giới hạn reassign và diễn đạt vai trò của biến**, không phải tạo immutable deep object hoặc một cơ chế truyền tham số khác.

## 11. Dùng `final` cho method khi subclass không được thay hợp đồng ấy

Một **final instance method** ngăn subclass **override**. Đây là công cụ quan trọng khi một method thực thi **quy trình bắt buộc**, bảo vệ invariant hoặc duy trì một contract mà mọi subclass phải tôn trọng.

~~~java
abstract class Operation {
    public final String execute(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("Input trống");
        }
        return perform(input.trim());
    }

    protected abstract String perform(String input);
}
~~~

Một subclass có thể tùy chỉnh bước `perform`, nhưng không override `execute` để bỏ qua validation. Đây là dạng **template method**: final entry point + controlled extension hook.

### 11.1. Không thể override final method

~~~java
class ChildOperation extends Operation {
    @Override
    protected String perform(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }

    // @Override
    // public String execute(String input) { return input; }
    // Sai: execute trong superclass là final.
}
~~~

Những dòng sai được comment để đoạn class hợp lệ. Nếu bỏ comment method `execute` trong subclass, compiler báo lỗi vì không được override final method.

**Khi nên dùng:** một entry point phải áp dụng validation, audit, transaction lifecycle hoặc điều kiện bất biến thống nhất, trong khi subclass chỉ được cung cấp chiến lược cho một số bước.

**Giới hạn:** final trên một method không chứng minh toàn bộ code đều an toàn. Nếu method final gọi một hook `protected abstract perform` có side effect bất thường, subclass vẫn có thể làm hỏng state nếu API không định nghĩa rõ hook contract và kiểm soát nguồn dữ liệu.

### 11.2. Ví dụ hoàn chỉnh về extension point có kiểm soát

Tạo tệp **`FinalMethodDemo.java`**:

~~~java
import java.util.Locale;

public class FinalMethodDemo {
    static abstract class Processor {
        public final String process(String raw) {
            if (raw == null || raw.isBlank()) {
                throw new IllegalArgumentException("Input trống");
            }
            String checked = raw.trim();
            return transform(checked);
        }

        protected abstract String transform(String text);
    }

    static final class UpperProcessor extends Processor {
        @Override
        protected String transform(String text) {
            return text.toUpperCase(Locale.ROOT);
        }
    }

    static final class WrappedProcessor extends Processor {
        @Override
        protected String transform(String text) {
            return "[" + text + "]";
        }
    }

    public static void main(String[] args) {
        Processor upper = new UpperProcessor();
        Processor wrapped = new WrappedProcessor();

        System.out.println("Upper = " + upper.process("  java  "));
        System.out.println("Wrapped = " + wrapped.process("  oop "));

        try {
            upper.process(" ");
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 FinalMethodDemo.java
java FinalMethodDemo
~~~

**Stdout chính xác:**

~~~text
Upper = JAVA
Wrapped = [oop]
Rejected = Input trống
~~~

Chú ý:

1. `process` là final, nên subclasses không thay toàn bộ validation pipeline.
2. `transform` là protected abstract, cho phép mỗi subclass hiện thực một bước tùy biến.
3. `UpperProcessor` và `WrappedProcessor` đều final vì ví dụ không cần tầng kế thừa tiếp theo.
4. Method final vẫn gọi dynamic dispatch đối với hook `transform`; `final` chỉ ngăn override **method process**, không vô hiệu hóa mọi polymorphism bên trong body.

**Không dùng final method trên tất cả methods như một thói quen** nếu class được thiết kế có extension points phong phú. Lựa chọn nên dựa trên hợp đồng mở rộng, không phải suy nghĩ “càng nhiều final càng an toàn”.

## 12. Khi nào nên khai báo một class là `final`?

Dùng `final class` khi **không muốn class được kế thừa** như một phần hợp đồng API.

Một số tình huống hợp lý:

- **Value object** có representation/invariant do chính class kiểm soát, không cần subclasses.
- **Implementation detail** không được thiết kế cho extension.
- **Helper class** hoặc class có semantics cụ thể, dễ bị phá nếu subclass override behavior.
- Một class **không cần là base class**; mở inheritance khi chưa có contract extension rõ có thể tạo phụ thuộc khó xử lý.
- Bạn muốn đảm bảo class có tập implementation instance behavior không bị thay bởi subclasses tùy ý.

~~~java
public final class Money {
    private final long cents;
    private final String currency;

    public Money(long cents, String currency) {
        this.cents = cents;
        this.currency =
                java.util.Objects.requireNonNull(currency, "currency");
    }

    public long cents() {
        return cents;
    }

    public String currency() {
        return currency;
    }
}
~~~

Đây là class minh họa đặt trong tệp `Money.java`. `Money` không thể được mở rộng bằng `class SpecialMoney extends Money`; compiler từ chối. Nhưng đây chưa phải money model hoàn chỉnh: cần xét miền giá trị, quy tắc currency, rounding, equality và arithmetic.

### 12.1. `final class` không tự làm instance immutable

~~~java
final class Box {
    int value;

    void update(int next) {
        value = next;
    }
}
~~~

Class `Box` là final nhưng `value` vẫn mutable. Không ai được subclass Box; điều đó **khác** việc không ai được thay state của Box object.

### 12.2. Khi không nên final class

Đừng khai báo class final nếu **kế thừa là extension point chủ đích** và đã có hợp đồng ổn định:

- Base class của một framework yêu cầu implementer `extends`.
- Abstract class cung cấp template/hook để subclass tùy chỉnh.
- Library API cam kết client có thể tạo subclasses và override những methods được chỉ định.

Nếu class là `abstract` để có subclasses, nó **không thể đồng thời `final`**:

~~~java
// abstract final class Bad {} // Không hợp lệ
~~~

Ngược lại, có thể làm **một số methods final** trong abstract class mà vẫn để các methods khác là abstract/overridable, như ví dụ `Processor` ở trên.

## 13. `final` hay thiết kế bằng interface, composition?

`final` không phải câu trả lời duy nhất cho bài toán kiểm soát sự mở rộng.

Ví dụ, thay vì để client `extends PaymentService` để thay một dependency, ta có thể đưa ra interface:

~~~java
interface PaymentGateway {
    boolean charge(long amount);
}

final class PaymentService {
    private final PaymentGateway gateway;

    PaymentService(PaymentGateway gateway) {
        this.gateway =
                java.util.Objects.requireNonNull(gateway, "gateway");
    }

    boolean pay(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount phải dương");
        }
        return gateway.charge(amount);
    }
}
~~~

`PaymentService` final: API không hỗ trợ subclass trực tiếp. Nhưng behavior vẫn có thể cấu hình thông qua **PaymentGateway interface**. Các implementations khác nhau, test doubles và strategies đều được inject tường minh.

**Thiết kế này thường thích hợp khi cần “đổi hành vi phụ thuộc”, không phải “đổi danh tính của service class”**. Composition giúp kiểm soát extension points rõ hơn so với cho subclass override bất kỳ method nào.

### 13.1. `final` không loại bỏ polymorphism

Một final class vẫn có thể **implement interface** và được sử dụng polymorphically qua interface type:

~~~java
interface Formatter {
    String format(String text);
}

final class LowerFormatter implements Formatter {
    @Override
    public String format(String text) {
        return text.toLowerCase(java.util.Locale.ROOT);
    }
}
~~~

`LowerFormatter` không được subclass, nhưng object của nó vẫn có thể được giữ trong biến `Formatter`. Runtime dispatch qua interface vẫn hoạt động. **Final ngăn kế thừa class đó; không ngăn class đó triển khai interface và tham gia polymorphism.**

## 14. `static final` cho constants có ý nghĩa ổn định

Một công dụng điển hình:

~~~java
class Protocol {
    static final int MAX_PACKET_BYTES = 1_024;
    static final String VERSION = "1";
}
~~~

Dùng `static` vì các giá trị thuộc class, không thuộc từng object. Dùng `final` vì binding không nên bị gán lại.

Nếu giá trị cần công khai cho caller ngoài package/class, cân nhắc visibility phù hợp:

~~~java
public final class Limits {
    public static final int MAX_ITEMS = 100;

    private Limits() {
    }
}
~~~

Đây là utility class có public constant; code dùng `Limits.MAX_ITEMS` mà không tạo instance. Nhưng **public constants là một phần API**: đổi tên, loại, ý nghĩa hoặc giá trị có thể ảnh hưởng client code.

### 14.1. Compile-time constants và vấn đề inlining

Với `static final` primitive hoặc String có initializer là constant expression phù hợp, Java có khái niệm **constant variable**. Compiler client có thể **inline giá trị** vào bytecode client.

Ví dụ thư viện:

~~~java
public final class ApiConstants {
    public static final int PAGE_SIZE = 20;
}
~~~

Nếu thư viện thay `PAGE_SIZE` thành 50 rồi phát hành version mới, **client đã biên dịch từ version cũ có thể tiếp tục dùng giá trị 20** cho đến khi biên dịch lại. Vì vậy, tránh công bố compile-time constant cho giá trị **có thể thay đổi theo deployment/version** nếu bạn cần client luôn tra cứu giá trị runtime mới.

Khi cần giá trị có thể thay đổi theo môi trường:

~~~java
public final class Settings {
    private Settings() {
    }

    public static int pageSize() {
        return Integer.getInteger("app.page.size", 20);
    }
}
~~~

Đoạn trên là ví dụ API tính giá trị tại thời điểm gọi, không phải static final compile-time constant. Cần validate property và tính nhất quán nếu dùng trong production.

### 14.2. `static final` reference không nhất thiết là compile-time constant

~~~java
static final java.time.Instant STARTED_AT =
        java.time.Instant.now();
~~~

`Instant.now()` được thực hiện khi class được khởi tạo và trả object; đây không phải một compile-time constant. Tương tự `static final List<String> TAGS = List.of(...)` có final reference nhưng không phải constant variable kiểu primitive/String theo quy tắc JLS.

## 15. Tránh dùng `public static final` cho mutable singleton object không kiểm soát

Ví dụ gây hiểu nhầm:

~~~java
import java.util.ArrayList;
import java.util.List;

class Registry {
    public static final List<String> USERS = new ArrayList<>();
}
~~~

Dù `USERS` là static final, mọi code có quyền truy cập vẫn có thể gọi:

~~~java
Registry.USERS.add("Lan");
Registry.USERS.clear();
~~~

Tức là **global mutable state** có thể bị sửa bởi các caller không được kiểm soát. Từ khóa final không ngăn những thay đổi ấy.

Thiết kế nếu dữ liệu thật sự là hằng bất biến:

~~~java
import java.util.List;

final class Registry {
    static final List<String> DEFAULT_USERS =
            List.of("Guest", "Admin");
}
~~~

Còn nếu đây là registry động, nên thiết kế API quản lý concurrency, ownership, validation, lifecycle, và không trả trực tiếp mutable collection dùng chung.

### 15.1. Không dùng constant interface chỉ để kế thừa constants

Một cách viết kiểu:

~~~java
interface Constants {
    int LIMIT = 10;
}

class Service implements Constants {
}
~~~

làm `Service` “nhận” constant thông qua interface mà bản thân Service không thực hiện một hợp đồng hành vi nào. Trong thiết kế hiện đại, **tránh lạm dụng constant interface pattern**. Thường rõ ràng hơn nếu dùng `Limits.LIMIT` của utility class hoặc enum/value object phù hợp.

## 16. `final`, immutable object và record trong Java 17

Để một object thực sự **immutable theo hợp đồng**, thường cần hơn `final`:

1. Không có API thay state sau tạo.
2. Các fields đại diện state không được gán lại tùy ý.
3. Không làm lộ mutable representation thông qua getter.
4. Nếu nhận mutable input, phòng vệ bằng copy hoặc chuyển sang immutable representation.
5. Tránh để subclass phá invariant thông qua override/hiding, hoặc thiết kế extension contract an toàn.
6. Không cho `this` escape trong quá trình khởi tạo.

Một class immutable có thể dùng final class + private final fields, nhưng phải xét **cả trạng thái object con**.

### 16.1. Record: cú pháp cô đọng cho dữ liệu ít thay đổi

Trong Java 17:

~~~java
record Coordinate(int x, int y) {
    Coordinate movedBy(int dx, int dy) {
        return new Coordinate(
                Math.addExact(x, dx),
                Math.addExact(y, dy));
    }
}
~~~

Record `Coordinate` là **implicitly final**, các component fields tương ứng là private final và có accessors `x()`, `y()`; không tự tạo setters. `movedBy` trả một object mới, giữ object cũ không đổi.

Nhưng record không tự **deep immutable** khi component là mutable reference:

~~~java
import java.util.List;

record Tags(List<String> values) {
    Tags {
        values = List.copyOf(values);
    }
}
~~~

Compact constructor chuẩn hóa/copy `values`; do các phần tử là String immutable, đây là cách xây dựng record có state dễ kiểm soát hơn. Nếu là `List<MutableItem>`, `List.copyOf` không deep-copy từng object phần tử.

### 16.2. Không phải mọi entity nên là immutable record

Một đơn hàng phải trải qua nhiều trạng thái có thể nên là mutable entity có **final identity + controlled commands**. Ép toàn bộ state vào một final immutable class rồi tạo object mới sau mỗi hành động có thể phù hợp hoặc không, tùy hệ thống. Cân nhắc object identity, persistence model, concurrent access và yêu cầu lịch sử.

## 17. `final` và Java Memory Model: có lợi nhưng không phải phép màu

Final fields có những quy tắc **đặc biệt khi object được xây dựng đúng cách** trong Java Memory Model. Những quy tắc này giúp bảo đảm visibility của giá trị final fields dưới các điều kiện phù hợp, kể cả một số tình huống chia sẻ reference không có synchronization thường gặp.

Tuy nhiên:

- Một **final reference** có thể trỏ tới **mutable object**; final không khiến những thay đổi sau này trên object ấy thread-safe.
- Một class chứa final field và những non-final mutable fields vẫn có thể bị data races.
- Việc **công bố `this` quá sớm** trong constructor có thể làm code khác quan sát object trước khi hoàn tất khởi tạo.
- Các invariant gồm **nhiều fields** có thể vẫn cần synchronization hoặc immutable snapshot khi nhiều thread đọc/ghi.
- `final` không tương đương `volatile`, `synchronized`, `AtomicInteger` hoặc lock.

Ví dụ không an toàn về publication:

~~~java
class Unsafe {
    static Unsafe current;

    final String id;

    Unsafe(String id) {
        current = this; // Làm lộ object trước khi gán id
        this.id = id;
    }
}
~~~

Đây là đoạn minh họa **nên tránh**. Field `id` được constructor gán đúng theo definite assignment nếu hoàn tất bình thường, nhưng object có thể bị thread khác đọc từ static field trước lúc khởi tạo xong.

### 17.1. `final` trên một counter tham chiếu không thay thế atomic operations

~~~java
class Metrics {
    private final java.util.concurrent.atomic.AtomicInteger count =
            new java.util.concurrent.atomic.AtomicInteger();

    int record() {
        return count.incrementAndGet();
    }
}
~~~

`final` ngăn thay object AtomicInteger được lưu ở field, còn `incrementAndGet` bảo đảm thao tác tăng nguyên tử theo hợp đồng AtomicInteger. Hai tính chất khác nhau và cùng có ích.

Nếu dùng `final int count`, bạn không thể tăng field bằng `count++` sau khi khởi tạo. **Chọn cơ chế theo nghiệp vụ:** counter cần thay đổi thì field/value của counter phải có cách thay phù hợp; `final` không phải dấu hiệu chất lượng bắt buộc trên mọi field.

## 18. Khi nào `final` làm thiết kế khó mở rộng không cần thiết?

### 18.1. Library base classes

Nếu class được công bố như một **base class cho người dùng thư viện kế thừa**, việc thêm `final` vào class là thay đổi **phá vỡ source/binary compatibility** với subclasses đang tồn tại. Tương tự, đổi một overridable method thành final có thể khiến implementations/subclasses khác không còn hợp lệ.

Trước khi dùng final trong public/protected API, hãy hỏi:

- Class này có extension contract rõ ràng hay chỉ là implementation cụ thể?
- Subclass có được phép override method nào?
- Có cần cho third-party clients tùy chỉnh behavior bằng kế thừa?
- Có thể cung cấp interface/composition để mở rộng có kiểm soát mà không cần subclass trực tiếp?

### 18.2. Test doubles và mocking

Một số test framework tạo subclass để mock class/method, nên `final` có thể ảnh hưởng cách mock của **một số công cụ/cấu hình**. Nhưng không nên tự động bỏ final khỏi domain/API thiết kế tốt chỉ để hỗ trợ một công cụ cụ thể.

Các lựa chọn:

- Mock/inject qua interface.
- Dùng fake implementation của dependency.
- Dùng constructor injection.
- Dùng mock framework phù hợp với final classes/methods nếu framework/version thực sự hỗ trợ.
- Kiểm thử behavior qua public API thay vì override private implementation details.

**Không được khẳng định mọi mocking framework đều không mock được final class**; khả năng hỗ trợ phụ thuộc phiên bản và cấu hình.

### 18.3. Serialization, ORM, proxies

Một số framework sinh proxy/subclass hoặc yêu cầu constructor/field access đặc biệt. Final class/final method có thể xung đột với một cách proxy cụ thể, nhưng yêu cầu khác nhau theo framework và phiên bản.

Hãy xem hợp đồng framework trước khi quyết định mở class hoặc bỏ final. Nếu persistence concerns buộc domain model mở hơn mong muốn, có thể cân nhắc tách domain model, DTO và persistence mapping, khi hợp lý.

## 19. Khi nào không cần `final` trên method/class?

Không phải mọi class đều cần final. Những tình huống **chủ đích hỗ trợ overriding/inheritance**:

~~~java
abstract class Notifier {
    public final void notifySafely(String message) {
        if (message == null || message.isBlank()) {
            throw new IllegalArgumentException("message trống");
        }
        deliver(message);
    }

    protected abstract void deliver(String message);
}
~~~

Class `Notifier` phải được subclass để hiện thực `deliver`. Nó **không thể** final class, nhưng `notifySafely` có thể final để bảo vệ bước validate.

Một method cần cho subclass override theo contract thì **không** final:

~~~java
protected abstract void deliver(String message);
~~~

**Thiết kế tốt thường kết hợp**: khóa entry point có invariant bắt buộc, và để mở những hooks được mô tả rõ.

### 19.1. `private final` method thường không mang nhiều giá trị mở rộng

Một private instance method không thể được subclass override như một inherited method. Thêm `final` vào private method thường không bổ sung khả năng bảo vệ overriding hữu ích. Java cho phép một số tổ hợp modifier hợp lệ, nhưng **đừng dùng final một cách trang trí** nếu tính chất ấy đã được bảo đảm bởi phạm vi truy cập hoặc cú pháp khác.

### 19.2. Constructor không thể khai báo final

Constructor không được override như instance method, nên không có ý nghĩa dùng `final` trên constructor:

~~~java
class Example {
    // final Example() {} // Sai cú pháp modifier constructor
    Example() {
    }
}
~~~

Tương tự, class `final` không thể kết hợp `abstract` để bắt buộc subclass; mục tiêu của hai modifiers mâu thuẫn nhau.

## 20. Lưu ý về compiler và khả năng tối ưu

Không nên chọn `final` chỉ vì kỳ vọng “chắc chắn nhanh hơn”. JVM/JIT có nhiều kỹ thuật inlining và devirtualization dựa trên runtime profiling, class hierarchy và những điều kiện riêng; một method không final **vẫn có thể được tối ưu**, còn final **không cam kết hiệu năng cụ thể**.

Chọn final chủ yếu vì:

- Nó làm **contract** rõ ràng.
- Nó giúp compiler bắt lỗi reassign/override/subclass trái ý định.
- Nó hỗ trợ **bất biến và reasoning**.
- Nó có những ngữ nghĩa nhất định trong **Java Memory Model** khi sử dụng đúng.

Nếu performance thực sự quan trọng, benchmark theo cách đáng tin (ví dụ JMH phù hợp) thay vì giả định gắn final sẽ tạo một mức cải thiện cố định.

## 21. So sánh `final` với `private`, `static`, `volatile` và `synchronized`

| Từ khóa/cơ chế | Trả lời câu hỏi chính | Không thay thế được |
| --- | --- | --- |
| `private` | Ai được truy cập member? | Final/immutability |
| `final` field | Field có bị gán lại sau khởi tạo không? | Deep immutability, validation |
| `static` | Member thuộc class hay instance? | Finality hoặc thread safety |
| `volatile` | Visibility/ordering của truy cập field đồng thời ra sao? | Atomic compound updates, invariant |
| `synchronized` | Đường thực thi nào phải có monitor và happens-before liên quan? | Immutable design, business validation |
| `AtomicInteger` | Read-modify-write atomic cho integer state? | Tính đúng của toàn bộ aggregate |
| `List.copyOf` | Cung cấp unmodifiable snapshot về cấu trúc? | Deep copy mọi mutable element |
| `final class` | Có được extends class này không? | Thread safety, non-null state |

Không nên ghép từ khóa mà không hiểu ý nghĩa. Ví dụ, một final field **không được thiết kế để tiếp tục gán giá trị mới như volatile mutable state**. Một `private static final` reference tới mutable HashMap vẫn cần concurrency protocol phù hợp.

## 22. Quy tắc chọn `final` theo trách nhiệm của đối tượng

| Tình huống | Quyết định thường hợp lý | Lý do |
| --- | --- | --- |
| Order ID bất biến | `private final String orderId` | Identity không đổi sau khởi tạo |
| Tên hiển thị được phép đổi | Non-final field + `rename(...)` | Thay đổi có kiểm soát |
| Dependency của service ổn định | `private final Repository repository` | Constructor injection, không reassign |
| Danh sách nội bộ thay đổi phần tử | `private final List<Item> items` + commands | Reference không đổi nhưng nội dung có thể thay |
| Giá trị bất biến nhỏ | `final class` hoặc `record` + immutable fields | Không cần subclass, value semantics |
| Counter tăng liên tục | Non-final primitive/atomic state; có thể final reference tới atomic object | State phải thay đổi |
| Public validation pipeline | `public final process()` + protected hook | Không cho override bỏ validation |
| Base class mở rộng bằng kế thừa | Không final class | Có hợp đồng extension |
| Constant thật sự cố định | `static final` primitive/String/immutable data | Giá trị dùng chung |
| Runtime configuration thay đổi | Provider, method hoặc mutable state có kiểm soát | Không dùng compile-time constant sai mục đích |
| Local kết quả đã chốt | `final` local nếu tăng clarity | Tránh reassign không chủ đích |
| Local accumulator | Non-final local | Cần cập nhật qua vòng lặp |
| Lambda capture | Final hoặc effectively final | Tuân thủ luật capture |
| DTO/framework proxy | Theo yêu cầu cụ thể của framework | Không biến final thành luật tuyệt đối |

**Không có một “tỷ lệ field final chuẩn” cho mọi dự án.** Số lượng final nên xuất phát từ **invariants và quyền thay đổi hợp lệ**, không phải một chỉ tiêu máy móc.

## 23. Các lỗi thường gặp khi dùng `final`

1. **“Mọi field nên final để code tốt hơn.”** Sai. State có nghiệp vụ thay đổi hợp lệ không cần bị khóa reassign; hãy thiết kế commands/validation phù hợp.
2. **“`final List` là List bất biến.”** Sai. Final chỉ ngăn gán lại reference, không cấm `add/remove` trên mutable List.
3. **“`final Customer c` làm object Customer không đổi.”** Sai với local/parameter: không được gán lại `c`, nhưng object có thể mutable.
4. **“Final reference luôn non-null.”** Sai. `null` vẫn có thể được gán một lần nếu type là reference và contract không cấm.
5. **“Final field đã tự validate input.”** Sai. Compiler kiểm tra gán, không biết domain rules.
6. **“Final class không thể implement interface.”** Sai. Nó không thể bị subclass, nhưng vẫn có thể implement interface.
7. **“Final method ngăn mọi polymorphism.”** Sai. Các overridable hooks khác hoặc interface dispatch vẫn hoạt động.
8. **“Càng nhiều final method càng dễ mở rộng.”** Không. Final đóng một extension point; cần cân nhắc khách hàng có được override theo API không.
9. **“Mọi test framework đều không hỗ trợ final.”** Sai. Khả năng phụ thuộc framework/version/configuration.
10. **“Final chắc chắn làm code chạy nhanh hơn.”** Không có bảo đảm; nên chọn final vì semantics.
11. **“`static final` luôn là compile-time constant.”** Sai. Chỉ những constant variables đủ điều kiện primitive/String và constant expression phù hợp.
12. **“Đổi một public static final primitive ở thư viện, client cũ tự đọc giá trị mới.”** Không nhất thiết; có thể bị inline vào client bytecode.
13. **“Một public static final mutable collection an toàn cho cả ứng dụng.”** Sai. Caller vẫn có thể sửa object nếu API cho phép.
14. **“Thêm final vào dependency ngăn mọi cấu hình runtime thay đổi.”** Sai. Provider object được giữ ổn định nhưng có thể cung cấp dữ liệu thay đổi.
15. **“Final loại bỏ nhu cầu thread synchronization.”** Sai với mutable state, publication protocol và object con.
16. **“Final param thay đổi cách truyền tham số.”** Sai. Java vẫn pass-by-value.
17. **“Phải viết `final` trước mọi biến lambda capture.”** Không. Effectively final là đủ.
18. **“Final constructor là cách cấm override constructor.”** Không hợp lệ. Constructors không override.
19. **“`abstract final class` vừa không cho kế thừa vừa yêu cầu kế thừa.”** Mâu thuẫn, compiler từ chối.
20. **“`private final` trên mọi helper luôn cần.”** Thường thừa nếu method private vốn không overridable từ subclass.

## 24. Bài tập tự kiểm tra có đáp án

**Câu 1.** Với `private final String id` và `private String name`, cách phân chia này diễn đạt điều gì?

**Đáp án:** `id` là một binding ổn định sau khởi tạo; `name` có thể được thay qua những hành vi hợp lệ. Class vẫn phải validate cả hai theo contract.

**Câu 2.** Một field `final List<String> items` có thể gọi `items.add("A")` không?

**Đáp án:** Có nếu List object mutable và code có quyền truy cập. `final` không làm List trở thành immutable.

**Câu 3.** Một final field có thể nhận `null` trong constructor không?

**Đáp án:** Có về mặt ngôn ngữ. Nhưng nếu contract yêu cầu non-null thì constructor phải từ chối null riêng.

**Câu 4.** `final List<String> items` có giúp constructor tránh defensive copy input không?

**Đáp án:** Không. Nếu constructor giữ tham chiếu đầu vào mutable, caller có thể sửa List bên ngoài. `List.copyOf` hoặc copy phù hợp giúp bảo vệ structure.

**Câu 5.** Khi nào nên khai báo class final?

**Đáp án:** Khi class không được thiết kế làm base class/extension point, ví dụ implementation cụ thể hoặc value object cần ổn định contract. Không sử dụng nếu inheritance là yêu cầu rõ ràng.

**Câu 6.** Final class có thể tham gia polymorphism qua interface không?

**Đáp án:** Có. Nó có thể implement interface; chỉ không cho subclass kế thừa class ấy.

**Câu 7.** Vì sao một template method có thể là final trong abstract class?

**Đáp án:** Để mọi subclasses phải đi qua quy trình kiểm tra/điều phối bắt buộc; subclass chỉ được tùy biến hooks được mở rõ ràng.

**Câu 8.** Final method có ngăn gọi một overridable method bên trong body của nó không?

**Đáp án:** Không. Final ngăn override chính method final; lời gọi tới instance hooks khác vẫn có thể dispatch theo runtime object.

**Câu 9.** `static final int PAGE_SIZE = 20` có thể khiến client bytecode giữ 20 sau khi thư viện đổi thành 50 không?

**Đáp án:** Có, nếu giá trị được compiler client inline như compile-time constant. Cần cân nhắc public API và recompilation.

**Câu 10.** Một service có `private final Clock clock` có thể đọc “giờ hiện tại” thay đổi theo thời gian không?

**Đáp án:** Có. Reference tới Clock không bị gán lại, nhưng `clock.instant()` có thể trả các Instant khác nhau theo thời gian và implementation.

**Câu 11.** `final Parameter p` có chặn gọi method làm đổi state của object p không?

**Đáp án:** Không. Nó chỉ ngăn gán lại biến parameter `p`, không đóng băng object.

**Câu 12.** Lambda có bắt buộc capture variable khai báo với keyword final không?

**Đáp án:** Không. Effectively final là đủ khi local/parameter không bị gán lại theo quy tắc Java.

**Câu 13.** `final int count` có phù hợp cho bộ đếm thay đổi nhiều lần không?

**Đáp án:** Không nếu bạn định cập nhật chính field `count`. Có thể dùng mutable field với synchronization/atomic operations hoặc final reference tới atomic counter, tùy thiết kế.

**Câu 14.** Dùng `final` cho một field có tạo ra Java Memory Model safe publication vô điều kiện không?

**Đáp án:** Không. Final fields có ngữ nghĩa khởi tạo đặc biệt khi object được xây dựng đúng; tránh `this` escape và vẫn kiểm soát mutable state/concurrency riêng.

**Câu 15.** Một class abstract có nên được khai báo final không?

**Đáp án:** Không. `abstract` đòi hỏi cơ chế subclassing để hoàn chỉnh implementation, còn `final` cấm subclass; tổ hợp này không hợp lệ.

**Câu 16.** Tại sao `private static final List<String> TAGS = List.of("A")` diễn đạt tốt hơn một mutable `public static final ArrayList` dùng làm constant?

**Đáp án:** Nó giấu reference khỏi caller ngoài class và dùng một List không sửa được về cấu trúc; dữ liệu String immutable. Public mutable ArrayList cho bên ngoài sửa global state dù field final.

## 25. Checklist khi quyết định có nên thêm `final`

Trước khi dùng keyword, hãy đặt câu hỏi về **ý định**, không chỉ cú pháp:

1. **Field này đại diện cho identity hay cấu trúc ổn định?** Nếu có, cân nhắc final.
2. **Giá trị cần được chọn lúc khởi tạo rồi giữ nguyên?** Dùng blank final + constructor validation nếu phù hợp.
3. **Field có mutable reference không?** Final không thay cho defensive copy, read-only exposure hoặc deep immutability.
4. **State này có nghiệp vụ thay đổi hợp lệ không?** Nếu có, không ép final trên chính giá trị cần reassign; mở commands có kiểm soát.
5. **Dependency có nên được thay trong vòng đời object không?** Nếu không, final constructor injection là lựa chọn tốt.
6. **Local/parameter có được gán lại không?** Có thể dùng final nếu nó cải thiện rõ ràng, không cần áp dụng máy móc.
7. **Biến sẽ được lambda capture?** Chỉ cần final hoặc effectively final.
8. **Method có đại diện cho một quy trình bắt buộc không thể bypass bằng override?** Final method có thể phù hợp.
9. **Class có phải extension point công khai không?** Nếu có, đừng final class; hãy tài liệu hóa hooks và protected APIs.
10. **Có thể dùng interface/composition thay vì inheritance không?** Cân nhắc mở rộng hành vi thông qua dependency.
11. **Public static final value có thật sự cố định qua các phiên bản?** Nếu không, nghĩ đến accessor/configuration để tránh constant inlining và coupling.
12. **Static final reference có trỏ object mutable không?** Không công khai global mutable collection một cách vô kiểm soát.
13. **Có yêu cầu ORM/proxy/test framework cụ thể không?** Kiểm tra compatibility trước khi chọn final class/method.
14. **Có multi-threading không?** Final không thay mutex/atomic/visibility cho những thay đổi state sau khởi tạo.
15. **Có đang thêm final chỉ vì “performance” hoặc “style mọi thứ final” không?** Ưu tiên contract; đo hiệu năng nếu thật sự cần.
16. **Với constructor:** bảo đảm blank final được gán đúng một lần trên mọi đường hoàn tất bình thường, và tránh làm lộ `this` khi chưa khởi tạo xong.

## Kết luận

`final` có giá trị lớn nhất khi nó **diễn đạt một quyết định thiết kế có chủ đích**:

- **Final field** bảo vệ identity, dependencies và những bindings không nên gán lại sau khởi tạo.
- **Final local/parameter** ngăn reassign khi điều đó làm ý nghĩa code rõ hơn.
- **Final method** bảo vệ một phần hợp đồng không được subclass override.
- **Final class** đóng inheritance khi class không được thiết kế để kế thừa.
- **Static final** diễn đạt dữ liệu chung có binding cố định, đặc biệt với constants được thiết kế cẩn thận.

Hãy nhớ điều `final` **không làm**: nó không tự validate dữ liệu, không bảo đảm reference khác null, không đóng băng mutable object bên trong, không tự tạo thread safety và không chứng minh API luôn đúng nghiệp vụ. **Chọn `final` dựa trên ai sở hữu dữ liệu, điều gì được phép thay đổi và ranh giới nào phải ổn định** — đó là cách dùng từ khóa này để tăng khả năng hiểu, sửa và bảo trì Java class trong dài hạn.
