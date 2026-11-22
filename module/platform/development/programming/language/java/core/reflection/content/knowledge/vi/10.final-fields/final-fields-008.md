# Chọn constructor, factory hoặc API cập nhật được thiết kế sẵn cho trường `final`

Trong Java, một trường `final` được gán trong quá trình khởi tạo hợp lệ và không thể được **gán lại bằng mã Java thông thường** sau khi đối tượng đã xây dựng xong. Trong Reflection, việc tìm được `Field` và gọi `setAccessible(true)` không có nghĩa là thao tác sửa field đó luôn được phép, an toàn hay duy trì đúng hành vi chương trình.

Với **Field final**, cách xử lý được ưu tiên là thiết kế rõ vòng đời trạng thái: dùng **constructor** để truyền giá trị tại lúc khởi tạo, **static factory** hoặc **builder** khi cần cách tạo đối tượng có ý nghĩa nghiệp vụ, và **API cập nhật được thiết kế sẵn** khi dữ liệu cần đổi. API cập nhật có thể tạo ra **một đối tượng bất biến mới** hoặc thay đổi field được chủ đích cho phép mutable. Không cần sửa `final` field bằng Reflection để đạt các mục tiêu này.

## 1. Điều `final` bảo đảm và không bảo đảm

```java
final class Account {
    private final String id;
    private final int points;

    Account(String id, int points) {
        this.id = id;
        this.points = points;
    }
}
```

`id` và `points` nhận giá trị khi tạo đối tượng. Sau đó, mã Java thông thường không thể gán `account.points = 20`. Nếu muốn biểu diễn tài khoản với điểm mới, hãy tạo một `Account` khác qua API chính thức, hoặc chọn thiết kế mutable ngay từ đầu.

Phân biệt ba ý quan trọng:

- **Final field:** không thể gán lại bằng mã Java thông thường sau khi khởi tạo.
- **Final reference:** khóa tham chiếu, không tự làm object mà nó trỏ đến trở nên bất biến. Ví dụ `final List<String> tags` vẫn có thể tham chiếu một danh sách có thể sửa.
- **Immutable object:** cần thiết kế toàn bộ trạng thái không thay đổi sau khởi tạo: field phù hợp, không để lộ mutable state, kiểm tra đầu vào và sao chép phòng vệ nếu cần. `List.copyOf(input)` chặn sửa cấu trúc danh sách qua API, nhưng nếu các phần tử tự mutable thì còn phải xét từng phần tử.

Một trường `static final` thường chứa hằng số hoặc tham chiếu dùng chung; không phải chỗ để chứa cấu hình được cập nhật liên tục. Record trong Java 17 dùng field `private final` cho mỗi record component; muốn giá trị component mới thì thông thường tạo record mới.

## 2. Chọn phương án theo nhu cầu

| Tình huống | Giải pháp | Đặc điểm |
| --- | --- | --- |
| Giá trị đã biết khi đối tượng được tạo | Constructor | Đặt field một lần và kiểm tra tính hợp lệ ngay từ đầu |
| Có nhiều cách khởi tạo hoặc tên nghiệp vụ rõ ràng | Static factory | Phương thức như `register`, `of`, `from` trả object đã được khởi tạo đúng |
| Nhiều tùy chọn, tham số dễ nhầm | Builder | Thu thập cấu hình tạm rồi gọi `build()` để tạo object hoàn chỉnh |
| Một giá trị trong immutable object cần thay đổi | Copy/wither | `withName` hoặc `withPoints` trả đối tượng mới, không sửa đối tượng cũ |
| Đối tượng được thiết kế là mutable | Method cập nhật chuyên biệt | Chỉ thay đổi field không `final` và luôn kiểm tra invariant |
| Cập nhật snapshot immutable được nhiều luồng dùng chung | Thay thế tham chiếu an toàn | Ví dụ `AtomicReference`, cơ chế khóa hoặc holder có synchronization |
| Khởi tạo từ JSON, DB hoặc framework | Binding theo constructor/record/factory/builder được hỗ trợ | Dữ liệu đi qua API tạo object đúng contract |
| Muốn sửa `private final` bằng Reflection | Xem lại vòng đời và API | Tránh bypass bất biến và ràng buộc JVM/module |

**Nguyên tắc:** Nếu dữ liệu là **input lúc tạo**, đưa vào constructor/factory/builder. Nếu dữ liệu là **snapshot bất biến mới**, tạo object mới. Nếu object có **trạng thái biến đổi có chủ đích**, dùng phương thức cập nhật được kiểm soát.

## 3. Constructor: khởi tạo đủ dữ liệu và bảo vệ invariant

Constructor có thể gói các quy tắc như mã định danh không rỗng, số lượng phải dương, giá tiền không âm, trạng thái phù hợp với ngày giao hàng. Đưa các kiểm tra này vào điểm khởi tạo chung giúp tránh object “mới xây được một nửa”.

```java
public final class Ticket {
    private final String code;
    private final int seats;

    public Ticket(String code, int seats) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code is required");
        }
        if (seats <= 0) {
            throw new IllegalArgumentException("seats must be positive");
        }
        this.code = code;
        this.seats = seats;
    }

    public String code() { return code; }
    public int seats() { return seats; }
}
```

Đây là **một class minh họa**, không có `main`. Nếu số ghế cần đổi, đừng tìm `Ticket.seats` bằng Reflection rồi cưỡng ép gán. Hãy thiết kế cách tạo `Ticket` mới với số ghế khác, hoặc tạo một loại ticket mutable có update API rõ ràng nếu nghiệp vụ thực sự cần chỉnh cùng instance.

Một constructor tốt còn cần tránh để `this` thoát ra ngoài trước khi hoàn tất khởi tạo. Dữ liệu mutable được nhận vào constructor có thể cần defensive copy để caller không sửa ngầm trạng thái của object về sau.

## 4. Static factory và builder: tạo object có ý nghĩa nghiệp vụ

Static factory có thể dùng constructor `private` để mọi đường tạo object đều tuân thủ cùng một bộ invariant. Ví dụ:

```java
// Đoạn minh họa bên trong lớp Customer:
public static Customer register(String id, String name) {
    return new Customer(id, name, 0);
}

public static Customer restore(String id, String name, int points) {
    return new Customer(id, name, points);
}
```

Đây không phải chương trình chạy độc lập vì phụ thuộc vào constructor của `Customer`. Tên `register` biểu thị quy tắc mới có điểm bằng 0; `restore` minh họa khôi phục từ dữ liệu có điểm. Constructor dùng chung vẫn phải xác thực `id`, `name` và `points`.

Static factory **không bắt buộc** trả instance mới trong mọi thư viện: có factory cache hoặc trả instance sẵn có. Nếu identity quan trọng, cần đọc contract. Factory được ưu tiên khi làm ý nghĩa khởi tạo rõ hơn constructor quá tải, không chỉ để đổi tên `new`.

Với object có nhiều tham số tùy chọn, builder thu thập các lựa chọn rồi gọi `build()`. Builder có thể mutable trong khi chuẩn bị, nhưng **object đầu ra** vẫn được tạo một lần với các field `final`.

```text
Builder nhận các lựa chọn (trạng thái tạm)
                ↓
build() kiểm tra điều kiện nghiệp vụ
                ↓
Constructor/factory tạo object hoàn chỉnh
                ↓
Object có các field final để sử dụng
```

Nếu đối tượng chỉ có 2–3 tham số rõ ràng, constructor hoặc factory đơn giản thường đủ; đừng thêm builder không cần thiết.

## 5. API cập nhật được thiết kế sẵn

### 5.1. Copy/wither: thay đổi trạng thái nhưng giữ đối tượng cũ

Một `Customer` immutable có thể cung cấp:

```java
// Đoạn minh họa nằm trong lớp Customer:
public Customer withDisplayName(String newName) {
    return new Customer(id, newName, points);
}
```

Sau `Customer newer = old.withDisplayName("Binh");`, `old` không bị thay đổi; biến `newer` trỏ tới instance mới. Nếu bỏ qua giá trị trả về thì không có thay đổi trạng thái nào được giữ lại.

Record rất phù hợp cho snapshot:

```java
public record Configuration(String environment, int timeoutSeconds) {
    public Configuration {
        if (environment == null || environment.isBlank()) {
            throw new IllegalArgumentException("environment is required");
        }
        if (timeoutSeconds <= 0) {
            throw new IllegalArgumentException("timeout must be positive");
        }
    }

    public Configuration withTimeoutSeconds(int seconds) {
        return new Configuration(environment, seconds);
    }
}
```

Đây là record minh họa độc lập nhưng không có `main`. Phương thức `withTimeoutSeconds` tạo `Configuration` mới qua canonical constructor và kiểm tra giá trị mới. Record không tự bất biến sâu nếu component trỏ đến object mutable; thiết kế record vẫn phải cân nhắc điều đó.

### 5.2. Method cập nhật: chỉ với trạng thái được chủ ý cho phép mutable

Không phải mọi object đều cần immutable. Ví dụ giỏ hàng có `final id` và `int quantity` có thể cung cấp `changeQuantity(int)` để sửa số lượng, đồng thời kiểm tra lớn hơn 0. Identity không đổi; số lượng thay đổi theo quy tắc nghiệp vụ. Đây là lý do **không nên bỏ `final` khỏi tất cả field** chỉ để có setter.

Nếu nhiều thread cùng cập nhật object mutable, cần giải quyết thread safety và tính nhất quán giữa các field. Một setter đơn giản hoặc thêm `volatile` cho một field không tự khiến toàn bộ thao tác nghiệp vụ trở thành atomic.

## 6. Ví dụ Java 17+ hoàn chỉnh

Lưu tệp đúng tên **`FinalFieldDesignDemo.java`**. Chương trình minh họa factory, immutable copy, record, update method và thay thế snapshot qua `AtomicReference`.

```java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

public class FinalFieldDesignDemo {
    public static void main(String[] args) {
        Customer original = Customer.register("C-01", "An");
        Customer renamed = original.withDisplayName("Binh");
        Customer rewarded = renamed.withPoints(25);

        System.out.println("original=" + original);
        System.out.println("renamed=" + renamed);
        System.out.println("rewarded=" + rewarded);

        Configuration config = new Configuration("prod", 10);
        Configuration next = config.withTimeoutSeconds(20);
        System.out.println("config=" + config);
        System.out.println("next=" + next);

        MutableCart cart = new MutableCart("cart-7", 1);
        cart.changeQuantity(3);
        System.out.println("cart=" + cart);

        AtomicReference<Configuration> current =
                new AtomicReference<>(config);
        current.updateAndGet(old -> old.withTimeoutSeconds(30));
        System.out.println("published=" + current.get());
        System.out.println("sourceStill=" + config);
    }

    static final class Customer {
        private final String id;
        private final String displayName;
        private final int points;

        private Customer(String id, String name, int points) {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(name, "name");
            if (id.isBlank() || name.isBlank() || points < 0) {
                throw new IllegalArgumentException("invalid customer");
            }
            this.id = id;
            this.displayName = name;
            this.points = points;
        }

        static Customer register(String id, String name) {
            return new Customer(id, name, 0);
        }

        Customer withDisplayName(String newName) {
            return new Customer(id, newName, points);
        }

        Customer withPoints(int newPoints) {
            return new Customer(id, displayName, newPoints);
        }

        @Override
        public String toString() {
            return "Customer[id=" + id
                    + ", displayName=" + displayName
                    + ", points=" + points + "]";
        }
    }

    record Configuration(String environment, int timeoutSeconds) {
        Configuration {
            Objects.requireNonNull(environment, "environment");
            if (environment.isBlank() || timeoutSeconds <= 0) {
                throw new IllegalArgumentException("invalid configuration");
            }
        }

        Configuration withTimeoutSeconds(int seconds) {
            return new Configuration(environment, seconds);
        }
    }

    static final class MutableCart {
        private final String id;
        private int quantity;

        MutableCart(String id, int quantity) {
            Objects.requireNonNull(id, "id");
            if (id.isBlank()) {
                throw new IllegalArgumentException("id is required");
            }
            this.id = id;
            changeQuantity(quantity);
        }

        void changeQuantity(int newQuantity) {
            if (newQuantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
            this.quantity = newQuantity;
        }

        @Override
        public String toString() {
            return "MutableCart[id=" + id
                    + ", quantity=" + quantity + "]";
        }
    }
}
```

Biên dịch/chạy từ thư mục chứa tệp:

```bash
javac FinalFieldDesignDemo.java
java FinalFieldDesignDemo
```

Kết quả stdout:

```text
original=Customer[id=C-01, displayName=An, points=0]
renamed=Customer[id=C-01, displayName=Binh, points=0]
rewarded=Customer[id=C-01, displayName=Binh, points=25]
config=Configuration[environment=prod, timeoutSeconds=10]
next=Configuration[environment=prod, timeoutSeconds=20]
cart=MutableCart[id=cart-7, quantity=3]
published=Configuration[environment=prod, timeoutSeconds=30]
sourceStill=Configuration[environment=prod, timeoutSeconds=10]
```

Điểm đáng chú ý: `Customer.register` gán giá trị khởi tạo qua private constructor; `withDisplayName` và `withPoints` trả các object mới, `original` giữ nguyên. Record `Configuration` được sao chép với timeout mới. `MutableCart` cập nhật field `quantity` thông qua API kiểm tra dữ liệu nhưng giữ `id` là `final`.

`AtomicReference.updateAndGet` thay thế tham chiếu đến snapshot mới một cách atomic, **không sửa field `final` trong snapshot cũ**. Lambda cập nhật nên không có side effect vì dưới cạnh tranh giữa các thread nó có thể bị gọi lại. Ví dụ chỉ chạy một luồng nên đầu ra nêu trên là xác định.

## 7. Vì sao tránh cưỡng ép gán `final` field bằng Reflection?

Một đoạn chương trình có thể tra cứu metadata:

```java
java.lang.reflect.Field field =
        Customer.class.getDeclaredField("points");
boolean isFinal = java.lang.reflect.Modifier.isFinal(
        field.getModifiers());
System.out.println(isFinal); // true
```

Đây là **đoạn minh họa**, không độc lập: cần đặt trong ngữ cảnh có lớp `Customer` và xử lý `NoSuchFieldException`. Phát hiện modifier `final` không mang ý nghĩa “có thể sửa an toàn”.

Các rào cản gồm:

1. **Access control và JPMS.** `getDeclaredField` tìm metadata của field `private`, nhưng thao tác `Field.set` còn chịu kiểm tra quyền. `setAccessible(true)` chỉ bật bỏ qua kiểm tra khi JVM/module cho phép; named module không mở package cho caller có thể gây `InaccessibleObjectException` hoặc khiến `trySetAccessible()` trả `false`.
2. **Không phải final field nào cũng được ghi.** Các nhóm không thể sửa qua cơ chế Reflection này bao gồm `static final`, final field trong record và final field của hidden class. Không được giả định bật access override là đủ.
3. **Java Memory Model và invariant.** Final field liên quan đến các đảm bảo khởi tạo đặc biệt khi object được xây dựng đúng. Cưỡng ép sửa sau khi object đã được công bố có thể phá hỏng invariant và dẫn tới kết quả quan sát không mong đợi bởi các thread hoặc mã đã được JVM tối ưu hóa. Thay đổi thành công trong một thử nghiệm không tạo thành API được hỗ trợ cho mọi runtime.
4. **Bảo trì và đóng gói.** Mã phụ thuộc tên field `private` dễ gãy khi refactor, đổi thư viện, đổi phiên bản JDK hoặc thay cấu trúc module; constructor/factory/update API mô tả contract rõ ràng hơn.

Các phiên bản JDK mới có thể siết các thao tác deep reflection lên final field hơn Java 17. Vì vậy, ví dụ thực hành ưu tiên API Java thông thường, không dựa vào kỹ thuật sửa final field bằng Reflection.

## 8. Ứng dụng với framework, lưu trữ và dữ liệu hiện có

Khi nạp từ JSON, database, file cấu hình hoặc một framework, không nên mặc định “tạo object rỗng rồi gán private final field qua Reflection”. Tùy framework và phiên bản, có thể dùng:

- **Constructor binding** cho class bất biến; mapper đưa dữ liệu vào constructor có validation.
- **Record binding** khi thư viện hỗ trợ record components và canonical constructor.
- **Static factory hoặc builder** nếu framework hỗ trợ định cấu hình đường tạo.
- **API nghiệp vụ** để cập nhật mutable entity theo invariant; với immutable object thì tạo instance mới và lưu/thay thế instance đó.

Không giả định mọi serializer/ORM đều hỗ trợ cùng một chế độ; cần xem tài liệu của framework và kiểm chứng bằng test mapping dữ liệu thật. Khi cập nhật database, còn phải xử lý concurrency, transaction, version, cache hoặc identity theo kiến trúc thực tế. Tạo object mới trong bộ nhớ **không tự động** thay đối tượng cũ trong collection, database hay các tham chiếu đã được các thành phần khác giữ.

Đối với cấu hình immutable được nhiều thread đọc chung, holder có `AtomicReference<Configuration>` hoặc cơ chế đồng bộ phù hợp là cách thay thế snapshot. Những thread giữ tham chiếu snapshot cũ vẫn đọc giá trị cũ; caller muốn thấy snapshot mới phải đọc lại từ holder. Đây là hợp đồng nhất quán cần nêu rõ.

## 9. Lỗi phổ biến

| Lỗi | Cách làm phù hợp hơn |
| --- | --- |
| Thiếu setter cho `final` thì dùng `Field.set` | Dùng constructor/factory/copy API, hoặc thiết kế field thật sự mutable có method cập nhật |
| Viết setter định gán lại `final` field | Java không cho gán lại theo cách này; trả object mới nếu immutable |
| Gọi `old.withPoints(10)` nhưng bỏ giá trị trả về | Giữ `newState = old.withPoints(10)` và thay tham chiếu nơi cần dùng |
| Cho rằng `final List` đồng nghĩa danh sách bất biến | Cần defensive copy và kiểm tra tính mutable của phần tử |
| Cho rằng `setAccessible(true)` chắc chắn ghi được `static final` hay field của record | Đây là các nhóm final field bị hạn chế ghi rõ ràng |
| Bỏ `final` khỏi toàn bộ class để framework khởi tạo được | Xem hỗ trợ constructor/record/factory/builder binding trước |
| Factory không validate, constructor validate một kiểu khác | Tập trung invariant trong đường khởi tạo chung |
| Có nhiều thread cập nhật cùng object mutable mà chỉ thêm một setter thường | Chọn đồng bộ hóa/atomic/transaction phù hợp; kiểm tra thao tác nhiều field |
| Thay instance immutable nhưng quên cập nhật cache/repository/state holder | Công bố và lưu tham chiếu instance mới theo contract hệ thống |

## 10. Checklist quyết định khi gặp yêu cầu “sửa final field”

1. **Đó có phải dữ liệu khởi tạo?** Nếu đúng, đưa qua constructor, factory hoặc builder trước khi công bố object.
2. **Có cần giữ nguyên đối tượng cũ không?** Với snapshot bất biến, chọn `withXxx`/copy và sử dụng object mới. Với domain mutable, cân nhắc update method rõ ràng.
3. **Invariant là gì?** Xác định điều kiện hợp lệ của cả dữ liệu khởi tạo và cập nhật.
4. **Có chia sẻ giữa nhiều thread hoặc qua database/cache không?** Xác định cơ chế công bố/lưu trạng thái mới có tính nhất quán.
5. **Framework đã hỗ trợ đường khởi tạo chính thức chưa?** Tìm constructor/record/factory/builder binding trước khi phụ thuộc private field.
6. **Có đang dùng Reflection chỉ để vượt qua lỗi thiết kế?** Nếu có, sửa API ở tầng domain hoặc adapter tích hợp thay vì can thiệp final field.

**Ghi nhớ:** `final` xác định ranh giới gán giá trị trong vòng đời object. Constructor/factory/builder thiết lập trạng thái ban đầu; copy/wither tạo trạng thái bất biến mới; update API có điều kiện quản lý trạng thái mutable. Reflection có thể cung cấp metadata nhưng không nên là đường cập nhật `final` field của ứng dụng.