# Nhiều giới hạn với `<T extends A & B>` trong Java Generics

Một tham số kiểu generic thường được khai báo đơn giản là `<T>`. Nhưng trong nhiều API, việc “`T` có thể là bất kỳ kiểu tham chiếu nào” là quá rộng: thuật toán có thể cần một đối tượng vừa kế thừa một lớp nền, vừa triển khai interface cung cấp tên và interface hỗ trợ kiểm toán. **Multiple bounds** (nhiều giới hạn kiểu) giải quyết trường hợp này bằng cú pháp `<T extends A & B>`: đối số kiểu hợp lệ phải thỏa mãn **đồng thời tất cả giới hạn**.

Ví dụ `<T extends Identified & Named & Auditable>` cho phép mã dùng các thành viên được hợp đồng của `Identified`, `Named` và `Auditable` công bố, mà không ép kiểu thủ công. Đây là một dạng **intersection type** ở mức tham số kiểu: `T` phải thuộc giao của các tập kiểu mà giới hạn mô tả.

Bài học tập trung vào cú pháp, điều kiện hợp lệ của giới hạn, thứ tự giới hạn lớp/interface, cách compiler kiểm tra và suy luận kiểu, thiết kế lớp/phương thức dùng nhiều bounds, những lỗi dễ gặp và ảnh hưởng của *type erasure*.

## 1. Từ một giới hạn đến nhiều giới hạn

Khai báo không có giới hạn tường minh:

```java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }
}
```

Ở đây `T` không có yêu cầu đặc biệt nào ngoài những điều kiện của Java Generics. Bạn không thể gọi `value.name()` hoặc `value.audit()` từ khai báo này, vì compiler không biết mọi kiểu `T` đều có các phương thức đó.

Một giới hạn:

```java
interface Named {
    String name();
}

class NamedBox<T extends Named> {
    private final T value;

    NamedBox(T value) {
        this.value = value;
    }

    String name() {
        return value.name();
    }
}
```

`T extends Named` yêu cầu đối số kiểu triển khai `Named`. Dù `Named` là **interface**, cú pháp giới hạn tham số kiểu **vẫn dùng từ khóa `extends`**, không dùng `implements`.

Nếu thuật toán cần thêm khả năng kiểm toán:

```java
interface Auditable {
    void audit();
}

class NamedAuditedBox<T extends Named & Auditable> {
    private final T value;

    NamedAuditedBox(T value) {
        this.value = value;
    }

    void showAndAudit() {
        System.out.println(value.name());
        value.audit();
    }
}
```

Ở đây `T` phải đồng thời thỏa `Named` **và** `Auditable`. Lời gọi `name()` và `audit()` hợp lệ vì compiler biết cả hai hợp đồng áp dụng cho `T`.

Ba nhóm khai báo ở phần này là **đoạn mã minh họa** có thể đặt vào một tệp Java với quy tắc tên lớp thích hợp; các mục tiếp theo cung cấp chương trình `main` độc lập để chạy.

## 2. Cú pháp chuẩn của nhiều giới hạn

Mẫu tổng quát của một tham số kiểu:

```java
<T extends FirstBound & SecondBound & ThirdBound>
```

Đây là **mẫu cú pháp**, không phải câu lệnh Java độc lập.

Ý nghĩa:

- `T` là tên **tham số kiểu** được khai báo.
- `extends` giới thiệu danh sách giới hạn trên (*upper bounds*).
- `&` nối các giới hạn. Ở đây `&` **không phải phép AND bitwise/boolean đang được tính toán**, mà là dấu phân cách trong một *intersection bound* của kiểu.
- Mọi giới hạn đều phải đúng **cùng lúc**, không phải “thỏa A **hoặc** B”.
- Danh sách giới hạn áp dụng cho **một** tham số kiểu `T`; nó khác việc khai báo nhiều tham số độc lập `<T, U>`.

Các hình thức hợp lệ:

```java
<T extends Named & Auditable>
<T extends Identified & Named>
<T extends Identified & Named & Auditable>
<T extends Number & Comparable<T>>
```

Chúng là **mẫu khai báo**, cần được đặt trong ngữ cảnh khai báo lớp, interface, constructor hoặc phương thức generic phù hợp.

Một số quy tắc bắt buộc:

1. **Tối đa một lớp cụ thể hoặc abstract làm class bound**. Nếu có class bound cùng các interface, **class bound phải đứng đầu tiên**.
2. Những giới hạn còn lại có thể là các interface hợp lệ; Java không cho một lớp kế thừa đồng thời hai lớp không liên quan như một cách “đa kế thừa lớp”.
3. Các giới hạn có thể chứa đối số generic, chẳng hạn `Comparable<T>`.
4. Cần tránh lặp cùng interface theo những kiểu tham số hóa xung đột, vì hệ phân cấp Java không cho một kiểu cùng kế thừa hai cách tham số hóa khác nhau của cùng generic interface.
5. Compiler chỉ chấp nhận tập giới hạn có thể tồn tại cùng nhau theo các quy tắc kế thừa/chữ ký của Java.

**Đặc biệt:** nếu chỉ dùng interface, interface có thể đứng đầu tiên mà không cần thêm `Object`. Ví dụ `<T extends Named & Auditable>` hoàn toàn hợp lệ.

## 3. Một class bound và các interface bổ sung

Với `<T extends BaseEntity & Named & Auditable>`, `BaseEntity` là **class bound** nên phải đứng đầu; `Named` và `Auditable` là các **interface bounds**. Compiler cho phép gọi những member truy cập được do cả ba hợp đồng cung cấp:

```java
static <T extends BaseEntity & Named & Auditable>
void process(T entity) {
    System.out.println(entity.id());
    System.out.println(entity.name());
    entity.audit();
}
```

Đoạn này là **method minh họa**: `BaseEntity`, `Named`, `Auditable` phải được khai báo với các method tương ứng và method phải nằm trong class hợp lệ. Nếu chỉ cần các khả năng `name()` và `audit()`, có thể viết `<T extends Named & Auditable>` mà không bắt buộc một class bound.

Bài học ở đây là **kết hợp nhiều hợp đồng để giải quyết một thuật toán**. Các luật cấu trúc nâng cao—thứ tự class, bound final, methods xung đột, trùng generic interface sau erasure—phải được xem xét trước khi công bố public API, không suy ra rằng mọi danh sách bounds đều hợp lệ.

## 4. Ví dụ Java 17 hoàn chỉnh: ràng buộc lớp và hai interface

Lưu toàn bộ chương trình thành **`MultipleBoundsDemo.java`**:

```java
public class MultipleBoundsDemo {
    static abstract class Identified {
        private final String id;

        Identified(String id) {
            this.id = id;
        }

        public String id() {
            return id;
        }
    }

    interface Named {
        String name();
    }

    interface Auditable {
        void audit();
    }

    static final class Customer extends Identified
            implements Named, Auditable {
        private final String name;

        Customer(String id, String name) {
            super(id);
            this.name = name;
        }

        @Override
        public String name() {
            return name;
        }

        @Override
        public void audit() {
            System.out.println("audit:" + id());
        }
    }

    static <T extends Identified & Named & Auditable>
    String process(T value) {
        value.audit();
        return value.id() + "|" + value.name();
    }

    public static void main(String[] args) {
        Customer customer = new Customer("C-17", "An");
        System.out.println(process(customer));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 MultipleBoundsDemo.java
java MultipleBoundsDemo
```

Kết quả chính xác (`stdout`):

```text
audit:C-17
C-17|An
```

Đọc ví dụ theo thứ tự:

- `Identified` là lớp nền có phương thức `id()`.
- `Named` và `Auditable` là các interface.
- `Customer extends Identified implements Named, Auditable` **thỏa cả ba điều kiện**.
- `<T extends Identified & Named & Auditable>` ràng buộc một tham số kiểu của **phương thức `process`**, không yêu cầu lớp `MultipleBoundsDemo` trở thành generic.
- Từ một biến `T value`, compiler cho phép gọi `value.id()`, `value.name()` và `value.audit()`.
- Khi gọi `process(customer)`, đối số `Customer` là một ứng viên hợp lệ cho `T`.

Đây là lợi ích chính của multiple bounds: **tránh dùng `Object` rồi tự ép kiểu thành từng interface** mỗi lần cần một hành vi.

## 5. Điều kiện “thỏa đồng thời” khác với một hợp đồng rộng

Giả sử có lớp chỉ triển khai `Named`:

```java
// Đoạn minh họa trong cùng phạm vi có interface Named:
final class ShortLabel implements Named {
    @Override
    public String name() {
        return "Short";
    }
}
```

`ShortLabel` không tự động thỏa `Auditable`. Nếu gọi phương thức:

```java
// process(new ShortLabel()); // Lỗi biên dịch: không thỏa tất cả giới hạn
```

thì compiler từ chối, ngay cả khi đối tượng có phương thức `name()` hoàn toàn hợp lệ. Đối tượng còn phải kế thừa `Identified` và triển khai `Auditable` nếu dùng bản `process` ở ví dụ trước.

Tương tự, nếu một lớp kế thừa `Identified` và triển khai `Auditable` nhưng không triển khai `Named`, nó vẫn không phù hợp.

Multiple bounds không kiểm tra tên phương thức theo kiểu *duck typing*: **thực sự phải có quan hệ kiểu Java** với các giới hạn đã khai báo. Một lớp vô tình có phương thức `name()` nhưng **không `implements Named`** vẫn không thỏa bound `Named`.

Mặt khác, nếu class bound là một lớp abstract, đối số kiểu `T` có thể là lớp con concrete phù hợp. Không cần `T` trùng chính xác với tên lớp trong phần giới hạn.

## 6. Nhiều interface mà không cần class bound

Một trường hợp phổ biến là cần hai năng lực được biểu diễn bằng hai interface:

```java
interface Named {
    String name();
}

interface Coded {
    String code();
}

static <T extends Named & Coded> String format(T item) {
    return item.name() + "#" + item.code();
}
```

Đoạn trên gồm khai báo interface và **một phương thức minh họa đặt trong một lớp**. `T` có thể là bất kỳ lớp hoặc kiểu đáp ứng đồng thời hai interface, không nhất thiết kế thừa lớp nền chung do ứng dụng định nghĩa.

### Chương trình hoàn chỉnh

Tạo tệp **`InterfaceBoundsDemo.java`**:

```java
public class InterfaceBoundsDemo {
    interface Named {
        String name();
    }

    interface Coded {
        String code();
    }

    record Product(String name, String code)
            implements Named, Coded { }

    static <T extends Named & Coded> String format(T item) {
        return item.name() + "#" + item.code();
    }

    public static void main(String[] args) {
        Product product = new Product("Pen", "P01");
        System.out.println(format(product));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 InterfaceBoundsDemo.java
java InterfaceBoundsDemo
```

`stdout`:

```text
Pen#P01
```

Java `record` tự sinh các accessor `name()` và `code()` ở mức `public`, đáp ứng chữ ký của hai interface. Lớp `Product` không cần kế thừa một class bound cụ thể. Đây là cách diễn đạt “có cả hai khả năng” một cách gọn gàng.

Với một thuật toán cần thêm khả năng mới, thường có thể bổ sung interface vào bounds thay vì ép mọi lớp nghiệp vụ vào một cây kế thừa lớp sâu.

## 7. Ràng buộc còn dùng được trong lớp generic và phương thức instance

Multiple bounds không chỉ dành cho phương thức `static`. Có thể ràng buộc tham số kiểu của cả lớp:

```java
interface Named {
    String name();
}

interface Auditable {
    void audit();
}

final class AuditedStore<T extends Named & Auditable> {
    private final T value;

    AuditedStore(T value) {
        this.value = value;
    }

    String describe() {
        value.audit();
        return value.name();
    }

    T get() {
        return value;
    }
}
```

Đây là nhóm khai báo Java minh họa. Khi viết `AuditedStore<Customer>`, kiểu `Customer` phải thỏa cả `Named` và `Auditable`. Constructor nhận `T`, getter trả `T` và phương thức instance được phép gọi cả hai hợp đồng.

Phân biệt hai vị trí giới hạn:

| Khai báo | Phạm vi ràng buộc |
|---|---|
| `class AuditedStore<T extends Named & Auditable>` | Mọi cách dùng `T` hợp lệ trong lớp `AuditedStore`, gồm trường và phương thức instance. |
| `static <T extends Named & Auditable> void audit(T v)` | Chỉ tham số kiểu `T` được khai báo riêng cho phương thức `audit`. |
| `<U extends Named & Auditable> U pick(U a, U b)` | Chỉ tham số kiểu `U` của phương thức instance `pick`. |
| `interface Combined<T extends Named & Auditable>` | Hợp đồng tham số kiểu của giao diện `Combined`. |

Một phương thức `static` trong lớp generic **không được dùng trực tiếp tham số kiểu của lớp**; nếu cần giới hạn kiểu ở static method, hãy khai báo `<U extends ...>` cho phương thức đó.

## 8. Ví dụ kết hợp: generic class và generic static method

Tạo tệp **`StoreBoundsDemo.java`**:

```java
public class StoreBoundsDemo {
    interface Named {
        String name();
    }

    interface Auditable {
        void audit();
    }

    record Entry(String name) implements Named, Auditable {
        @Override
        public void audit() {
            System.out.println("checked:" + name);
        }
    }

    static final class Store<T extends Named & Auditable> {
        private final T value;

        Store(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        String verify() {
            value.audit();
            return value.name();
        }

        static <U extends Named & Auditable> Store<U> of(U value) {
            return new Store<>(value);
        }
    }

    public static void main(String[] args) {
        Store<Entry> store = Store.of(new Entry("invoice"));
        System.out.println(store.verify());
        System.out.println(store.get().name());
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 StoreBoundsDemo.java
java StoreBoundsDemo
```

`stdout`:

```text
checked:invoice
invoice
invoice
```

`T` của `Store<T>` và `U` của `Store.of(...)` là **hai tham số kiểu độc lập**, dù chúng cùng có giới hạn `Named & Auditable`. Factory `of` có thể suy luận `U = Entry` rồi tạo `Store<Entry>`.

Ví dụ cũng cho thấy việc đưa nhiều giới hạn vào lớp có ý nghĩa khi **hầu hết hành vi của cả lớp** đều đòi các năng lực đó; còn đặt chúng vào một phương thức có thể phù hợp hơn khi **chỉ một thuật toán** cần các năng lực kết hợp.

## 9. Giới hạn kiểu dùng interface generic

Một bound bản thân có thể là **interface generic đã được tham số hóa**. Ví dụ `Comparable<T>` diễn đạt khả năng so sánh các đối tượng:

```java
static <T extends Number & Comparable<T>>
T max(T first, T second) {
    return first.compareTo(second) >= 0 ? first : second;
}
```

Đây là **phương thức minh họa**, cần đặt trong lớp hợp lệ. `Number` là class bound và **đứng trước** `Comparable<T>` là interface bound.

Phương thức có thể nhận `Integer` hoặc `Double` vì cả hai kế thừa `Number` và triển khai `Comparable` với kiểu phù hợp. Nhưng kiểu tham số không phải `Number` bất kỳ: `Number` trừu tượng không tự triển khai `Comparable<Number>`.

### Chương trình đầy đủ

Tạo tệp **`NumericBoundsDemo.java`**:

```java
public class NumericBoundsDemo {
    static <T extends Number & Comparable<T>> T max(T a, T b) {
        return a.compareTo(b) >= 0 ? a : b;
    }

    public static void main(String[] args) {
        Integer greatestInt = max(3, 7);
        Double greatestDouble = max(2.5, 1.25);

        System.out.println(greatestInt);
        System.out.println(greatestDouble);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 NumericBoundsDemo.java
java NumericBoundsDemo
```

`stdout`:

```text
7
2.5
```

Không được gọi `max("A", "B")` bằng chữ ký này vì `String` không phải `Number`. Đồng thời, những lời gọi với hai loại số không tương thích có thể khiến suy luận kiểu thất bại; nên biểu diễn hợp đồng rõ thay vì dùng cast hoặc raw type.

### Biến thể linh hoạt hơn với `? super T`

Trong API thực tế, bound `Comparable<? super T>` thường linh hoạt hơn:

```java
static <T extends Comparable<? super T>>
T maxComparable(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

`? super T` cho phép một đối tượng kiểu `T` dùng hợp đồng so sánh với kiểu cha phù hợp. Đây vẫn là **một giới hạn trên tham số kiểu `T`**, có chứa wildcard trong đối số của `Comparable`. Không nhầm wildcard **bên trong** bound với cú pháp nhiều giới hạn `&`.

## 10. Suy luận kiểu và kiểu tĩnh của biểu thức

Compiler kiểm tra multiple bounds dựa trên **kiểu tĩnh**, không chỉ dựa vào kiểu runtime của đối tượng:

```java
interface Named {
    String name();
}

interface Auditable {
    void audit();
}

static <T extends Named & Auditable> void use(T value) {
    System.out.println(value.name());
    value.audit();
}
```

Giả sử `Customer` triển khai cả `Named` và `Auditable`. Khi biến được khai báo là `Customer`:

```java
Customer customer = /* một Customer hợp lệ */;
use(customer);
```

Đây là đoạn minh họa, phần khởi tạo phải được thay bằng constructor thực tế của `Customer`.

Nhưng nếu **chính đối tượng ấy** đang nằm trong biến chỉ có kiểu giao diện `Named`:

```java
Named named = customer;
// use(named); // Lỗi biên dịch: kiểu tĩnh Named chưa bảo đảm Auditable
```

Lỗi là hợp lý: compiler chỉ biết `named` là `Named`; không thể tự suy ra mọi `Named` đều là `Auditable`.

Cách thiết kế tốt hơn là giữ kiểu cụ thể đến điểm cần gọi, hoặc giới thiệu một interface kết hợp có ý nghĩa nghiệp vụ. Nếu dữ liệu đến từ nguồn không tin cậy, cần xác thực trước khi ép kiểu; không nên dùng unchecked cast để “thuyết phục” compiler rằng một đối tượng có những năng lực chưa được chứng minh.

### Một interface kết hợp có thể giúp đơn giản API

```java
interface Named {
    String name();
}

interface Auditable {
    void audit();
}

interface AuditedNamed extends Named, Auditable { }

static <T extends AuditedNamed> void useCombined(T value) {
    System.out.println(value.name());
    value.audit();
}
```

Nhóm mã trên là **ví dụ minh họa**, trong đó phương thức `useCombined` cần nằm trong lớp. Nếu hệ thống có khái niệm nghiệp vụ ổn định “đối tượng vừa có tên vừa kiểm toán được”, việc định nghĩa `AuditedNamed` có thể làm API dễ đọc. Tuy nhiên, Java có phân biệt quan hệ kiểu **danh nghĩa** (*nominal typing*): một lớp chỉ `implements Named, Auditable` không tự động trở thành `AuditedNamed`; muốn dùng với `<T extends AuditedNamed>`, lớp phải triển khai interface kết hợp đó (trực tiếp hoặc qua kế thừa).

Đây là sự khác biệt giữa nhiều bounds (đòi đồng thời các supertype mà không cần khai báo interface kết hợp) và một interface mới được đặt tên.

## 11. Nhiều bounds và intersection type

Một tham số có `<T extends Named & Auditable>` được ràng buộc bởi một **intersection type**. Nghĩa là compiler cho phép sử dụng những thao tác từ tất cả giới hạn theo quy tắc của Java.

Tuy nhiên, **không phải mọi vị trí có kiểu Java đều cho phép viết trực tiếp `A & B`**:

```java
// Đúng: danh sách bounds trong khai báo tham số kiểu.
static <T extends Named & Auditable> void inspect(T value) { }

// Sai: wildcard không hỗ trợ cú pháp nhiều bounds này.
// List<? extends Named & Auditable> items;
```

Đây là những **đoạn khai báo minh họa**, cần đặt phương thức trong lớp và có các interface tương ứng. Nếu muốn nhận danh sách chỉ gồm các giá trị thỏa hai interface, có thể khai báo một phương thức generic:

```java
static <T extends Named & Auditable>
void inspectAll(java.util.List<T> values) {
    for (T value : values) {
        System.out.println(value.name());
        value.audit();
    }
}
```

Phương thức này dùng `T` để giữ đồng thời hai ràng buộc cho phần tử danh sách. Nó không đòi Java hỗ trợ cú pháp `List<? extends Named & Auditable>` vốn không hợp lệ.

Java cũng có cú pháp **intersection cast** như `(Named & Auditable) object` trong những tình huống thích hợp. Cast là kiểm tra/chuyển đổi trong một biểu thức và có thể thất bại lúc chạy nếu đối tượng không thỏa các kiểu được yêu cầu; đó là khái niệm khác với việc ràng buộc tham số kiểu để compiler bảo đảm lời gọi API.

## 12. Tác động của thứ tự bounds tới type erasure

Java Generics chủ yếu được kiểm tra ở **compile time** và sử dụng **type erasure**. Khi một tham số kiểu `T` có nhiều giới hạn, **erasure của `T` là erasure của giới hạn đầu tiên**.

Ví dụ:

```java
static <T extends Number & Comparable<T>> double asDouble(T value) {
    return value.doubleValue();
}
```

Bound đầu là `Number`, nên erasure của `T` là `Number`. Chữ ký ở mức JVM của tham số tương ứng về cơ bản là `Number`, dù compiler ở mã nguồn còn biết thêm yêu cầu `Comparable<T>`.

Nếu chỉ có các interface:

```java
static <T extends Named & Auditable> String label(T value) {
    return value.name();
}
```

erasure của `T` là `Named` vì đây là giới hạn đầu tiên. Nếu viết lại một API thành `<T extends Auditable & Named>`, erasure có thể đổi sang `Auditable`. Điều này ảnh hưởng đến descriptor/khả năng tương thích nhị phân và có thể liên quan đến bridge method khi biên dịch các phân cấp lớp.

### Thứ tự interface bounds không nên đổi tùy tiện trong API công khai

Xét hai khai báo:

```java
<T extends Named & Auditable>
<T extends Auditable & Named>
```

Cả hai có cùng ý định logic “`T` phải thỏa hai interface”, và đều có thể hợp lệ nếu hai interface tương thích. Nhưng **giới hạn đầu tiên khác nhau** nên erasure khác. Trong thư viện đã phát hành, đổi thứ tự có thể tạo khác biệt trong chữ ký JVM của các phương thức dùng `T`, từ đó gây vấn đề khi mã client cũ không được biên dịch lại.

Khi thiết kế API công khai, chọn thứ tự có ý nghĩa, giữ ổn định và xem thay đổi bounds là việc có thể ảnh hưởng tương thích, không chỉ là điều chỉnh thẩm mỹ.

Lưu ý Java vẫn lưu thông tin chữ ký generic trong metadata `Signature` của class file để trình biên dịch và công cụ khác khai thác; “erasure” **không có nghĩa mọi thông tin generic bị xóa hoàn toàn khỏi mọi phần của `.class`**.

## 13. Những giới hạn không thể kết hợp

Multiple bounds không cho phép bất kỳ tổ hợp kiểu nào một cách vô điều kiện.

### 13.1. Hai giới hạn lớp

```java
class ParentA { }
class ParentB { }

// Sai: Java không hỗ trợ hai class bounds.
// class Invalid<T extends ParentA & ParentB> { }
```

Nếu cần năng lực từ nhiều nguồn, sử dụng interface phù hợp hoặc composition thay vì cố mô hình hóa đa kế thừa class.

### 13.2. Class bound không đứng đầu

```java
interface Named {
    String name();
}

class Base { }

// Sai: class bound Base phải đứng đầu.
// class Invalid<T extends Named & Base> { }
```

Đúng là `<T extends Base & Named>`, với điều kiện các giới hạn có thể cùng được đáp ứng.

### 13.3. Hai cách tham số hóa xung đột của cùng generic interface

```java
interface Handler<T> {
    void handle(T value);
}

// Sai: hai cách tham số hóa khác nhau của cùng Handler.
// class Invalid<T extends Handler<String> & Handler<Integer>> { }
```

Một kiểu Java không được đồng thời kế thừa `Handler<String>` và `Handler<Integer>`. Đổi thứ tự hai giới hạn không sửa được lỗi: bản thân quan hệ kế thừa đã mâu thuẫn.

### 13.4. Các hợp đồng phương thức bất tương thích

```java
interface TextResult {
    String result();
}

interface NumberResult {
    Integer result();
}

// Sai: yêu cầu hai phương thức cùng tên/tham số nhưng
// có kiểu kết quả không tương thích.
// class Invalid<T extends TextResult & NumberResult> { }
```

Hai phương thức `result()` có cùng tên và danh sách tham số, nhưng kiểu trả về `String` và `Integer` không có quan hệ trả về covariant phù hợp. Compiler không thể định nghĩa một `T` đáp ứng hợp đồng phương thức của cả hai theo cách hợp lệ.

Các ví dụ ở phần này là **mã minh họa lỗi**, không phải chương trình để chạy. Chỉ bỏ comment khi muốn tự xem thông báo biên dịch.

## 14. Những lỗi cú pháp và cách sửa

| Viết sai hoặc hiểu nhầm | Vấn đề | Cách sửa |
|---|---|---|
| `<T implements A & B>` | Khai báo giới hạn tham số kiểu không dùng `implements`. | `<T extends A & B>`. |
| `<T extends A, B>` khi muốn `T` thỏa cả A và B | Dấu phẩy dùng phân cách **nhiều tham số kiểu**, không dùng nối multiple bounds. | `<T extends A & B>`. |
| `<T extends InterfaceA & ClassB>` | Class bound phải đứng đầu. | `<T extends ClassB & InterfaceA>` nếu các kiểu tương thích. |
| `<T extends ClassA & ClassB>` | Tối đa một class bound. | Dùng một lớp nền + các interface. |
| Nghĩ `A & B` cho phép A **hoặc** B | Đây là giao của hai hợp đồng. | Đối số kiểu phải thỏa **cả hai**. |
| Lớp có đủ phương thức nhưng không `implements¤ interface | Java dùng quan hệ kiểu danh nghĩa, không phải duck typing. | Khai báo đúng các quan hệ `implements`/`extends`. |
| `List<? extends A & B>` | Wildcard bound không cho viết trực tiếp nhiều giới hạn. | Dùng phương thức `<T extends A & B> void f(List<T>)`. |
| Gọi generic method qua biến khai báo chỉ là `A` khi yêu cầu `A & B` | Kiểu tĩnh chưa chứng minh bound `B`. | Giữ kiểu cụ thể, hoặc dùng API hợp đồng phù hợp. |
| Thay đổi thứ tự interface bounds tùy ý trong thư viện | Bound đầu chi phối erasure, có thể ảnh hưởng tương thích nhị phân. | Ổn định thứ tự bounds trong API công khai. |
| Dùng raw type/unchecked cast để né lỗi | Mất bảo vệ kiểu và có thể phát sinh lỗi runtime. | Thiết kế đúng bounds và chọn kiểu hợp lệ. |

## 15. Tình huống thiết kế thực tế: kiểm toán các thực thể có tên

Giả sử ứng dụng có nhiều đối tượng như `Customer`, `Invoice` hoặc `Job`. Không phải loại nào cũng cần cùng một lớp cha, nhưng những thao tác chung như “hiển thị tên” và “ghi nhật ký kiểm toán” là các năng lực có thể định nghĩa bằng interface.

Có ba cách thiết kế hợp lý:

1. **Giới hạn theo hai interface**: `<T extends Named & Auditable> void run(T value)`. Phù hợp khi thuật toán cần cả hai năng lực nhưng không quan tâm một class base cụ thể.
2. **Giới hạn theo lớp + interface**: `<T extends Identified & Named & Auditable> void run(T value)`. Phù hợp khi thuật toán thực sự cần truy cập API của lớp nền `Identified` bên cạnh các interface.
3. **Định nghĩa interface nghiệp vụ kết hợp**: `interface AuditedNamed extends Named, Auditable {}` rồi dùng `<T extends AuditedNamed>`. Phù hợp nếu “đối tượng có tên và có thể kiểm toán” là khái niệm ổn định trong domain và những lớp liên quan có thể công khai triển khai giao diện chung này.

Không nên dùng nhiều bounds chỉ để chứng minh khả năng viết syntax phức tạp. Nếu thuật toán chỉ cần `Named.name()`, hãy dùng một giới hạn `<T extends Named>` hoặc nhận trực tiếp `Named`. Mỗi giới hạn thêm vào **thu hẹp tập kiểu hợp lệ** mà người gọi có thể truyền cho API.

Khi cần thao tác với nhiều phần tử:

```java
static <T extends Named & Auditable> void auditAll(
        java.util.List<T> items) {
    for (T item : items) {
        System.out.println(item.name());
        item.audit();
    }
}
```

Đây là **phương thức minh họa nằm trong một lớp**. Bằng một bound duy nhất trên `T`, compiler kiểm tra mọi phần tử trong danh sách mà không cần cast thành `Named` hoặc `Auditable` riêng lẻ.

## 16. Checklist áp dụng multiple bounds

Khi gặp đề bài “thiết kế `<T extends A & B>`”, thực hiện lần lượt:

1. **Xác định năng lực thật sự cần**: phương thức sẽ gọi API nào từ `A`, từ `B`? Nếu không dùng `B`, có thể bound ấy chưa cần thiết.
2. **Xác định A, B là class hay interface**: nếu có một class bound, đưa nó lên đầu; không cố đưa hai class vào danh sách.
3. **Kiểm tra tính tương thích của hợp đồng**: các giới hạn có thể cùng được một kiểu triển khai hợp pháp hay không? Có xung đột phương thức hoặc generic superinterface không?
4. **Đặt `<T extends ...>` đúng vị trí**: sau tên lớp khi khai báo generic class, hoặc trước kiểu trả về khi khai báo generic method.
5. **Giữ nguyên quan hệ kiểu tại lời gọi**: dùng đối số cụ thể thỏa tất cả giới hạn; tránh đánh mất kiểu thành một interface quá rộng trước khi gọi.
6. **Phân biệt bound với wildcard**: `<T extends A & B>` hợp lệ; `? extends A & B` không phải cú pháp wildcard hợp lệ.
7. **Chú ý erasure ở API công khai**: giới hạn đầu ảnh hưởng kiểu erasure; không tự ý đảo thứ tự ở API đã phát hành.
8. **Biên dịch bằng Java 17+**, kiểm tra cảnh báo `rawtypes`/`unchecked` nếu tích hợp mã cũ, và thử cả trường hợp hợp lệ lẫn lỗi compile-time như một bài tập học tập.

## 17. Tự kiểm tra

**Câu 1.** Trong `<T extends Named & Auditable>`, một kiểu chỉ triển khai `Named` có dùng làm đối số kiểu `T` được không? Vì sao?

**Câu 2.** Đâu là khai báo hợp lệ nếu `Base` là lớp và `Named`, `Auditable` là interface: `<T extends Named & Base & Auditable>` hay `<T extends Base & Named & Auditable>`?

**Câu 3.** Vì sao `<T extends Number & Comparable<T>>` hỗ trợ thuật toán so sánh số, trong khi `<T extends Number>` chưa đủ để gọi `compareTo(T)`?

**Câu 4.** Java có chấp nhận `List<? extends Named & Auditable>` không? Muốn xử lý một danh sách các đối tượng có cả hai năng lực, có thể khai báo phương thức generic thế nào?

**Câu 5.** Trong phương thức `static <T extends Named & Auditable> void f(T value)`, `T` thuộc lớp hay thuộc phương thức?

**Câu 6.** Tại sao đảo thứ tự `Named & Auditable` sang `Auditable & Named` có thể quan trọng ở cấp class file mặc dù cả hai đều yêu cầu cùng hai interface?

**Gợi ý đáp án:** (1) Không, đối số kiểu phải thỏa tất cả giới hạn. (2) Dạng thứ hai, vì bound là lớp phải đứng đầu. (3) `Number` tự nó không khai báo `compareTo`; bound `Comparable<T>` cung cấp hợp đồng so sánh cần thiết. (4) Không; dùng chẳng hạn `static <T extends Named & Auditable> void f(List<T> items)`. (5) `T` thuộc riêng phương thức generic. (6) Erasure của `T` lấy từ giới hạn đầu tiên nên descriptor phương thức có thể thay đổi.

**Ghi nhớ:** Multiple bounds trong Java dùng cú pháp **`<T extends A & B>`**, biểu thị **T phải thỏa đồng thời A và B**. Nếu có giới hạn lớp, nó phải **đứng đầu** và chỉ được có một giới hạn lớp; các giới hạn tiếp theo là interface. Compiler cho phép gọi API của mọi giới hạn trên `T`, đồng thời ngăn kiểu không đáp ứng hợp đồng ngay khi biên dịch. Hãy nhớ thứ tự giới hạn đầu tiên có ý nghĩa đối với type erasure và phân biệt ràng buộc tham số kiểu với wildcard.
