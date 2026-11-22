# Quy tắc mức truy cập của constructor trong record chính thức (Java 16+)

> Bài học thuộc phần khởi tạo record của Java. `record` từng xuất hiện dưới dạng preview ở Java 14/15 nhưng đã là tính năng **chính thức từ Java 16**. Các quy tắc và ví dụ bên dưới dùng cú pháp record ổn định, còn áp dụng trong Java hiện đại (có thể biên dịch với JDK 17+), không sử dụng hướng dẫn preview đã lỗi thời.

## 1. Canonical constructor là gì và vì sao mức truy cập bị ràng buộc?

Với khai báo `record Point(int x, int y) {}`, Java xác định hai **record component** là `x` và `y`. Record có một **canonical constructor** với danh sách tham số tương ứng các component theo thứ tự và kiểu dữ liệu. Constructor đó chịu trách nhiệm khởi tạo các component của record. Nếu không tự khai báo, trình biên dịch tạo canonical constructor ngầm định; nếu muốn kiểm tra hoặc chuẩn hóa đầu vào, có thể khai báo constructor tường minh.

**Quy tắc cốt lõi của Java chính thức:** canonical constructor khai báo tường minh phải có mức truy cập **ít nhất bằng mức truy cập của chính record**. Điều này áp dụng như nhau cho hai hình thức: **normal canonical constructor** có danh sách tham số đầy đủ và **compact canonical constructor** dạng `RecordName { ... }`.

Ví dụ `public record Ticket(String code) {}` hứa cho mã bên ngoài có thể nhìn thấy loại `Ticket` và có đường tạo đối tượng theo các component. Vì thế một canonical constructor `private Ticket(...)` hoặc `Ticket { ... }` không có `public` là không hợp lệ trong một `public record`.

### Bảng quy tắc mức truy cập

| Mức truy cập của record | Mức truy cập hợp lệ của canonical constructor tường minh | Mức không hợp lệ |
|---|---|---|
| `public record` | **`public`** | `protected`, package-private (không ghi modifier), `private` |
| `protected record` (chỉ dùng ở vị trí member thích hợp trong một class) | **`protected` hoặc `public`** | package-private, `private` |
| `record` package-private (không ghi modifier) | **package-private, `protected` hoặc `public`** | `private` |
| `private record` (record member trong class) | **`private`, package-private, `protected` hoặc `public`** | Không có mức nào hẹp hơn `private` |

**Đừng nhầm mức của type và mức của constructor.** Một constructor được khai báo `public` bên trong một record lồng `private` không tự làm record đó trở nên truy cập được từ bên ngoài lớp chứa. Để tạo record từ một vị trí khác, mã gọi phải được phép truy cập **cả kiểu record lẫn constructor** (và còn chịu các quy tắc module/package nếu áp dụng).

**Phạm vi khai báo:** top-level record chỉ có thể là `public` hoặc package-private; `protected`/`private` không hợp lệ ở top-level. Các mức `protected` và `private` trong bảng áp dụng cho **member record** được khai báo bên trong class, nơi những modifier đó được phép. Member record là nested class có tính chất `static` ngầm định.

## 2. Constructor ngầm định có quyền truy cập nào?

Khi record không khai báo canonical constructor tường minh, trình biên dịch cung cấp một canonical constructor với mức truy cập tương ứng record (với record package-private thì constructor cũng có quyền package-private). Không cần tự viết constructor chỉ để có thể khởi tạo record.

```java
// Tệp UserId.java, đặt ở package phù hợp.
public record UserId(String value) { }
```

Trong trường hợp này, lời gọi `new UserId("A17")` được phép từ nơi nhìn thấy `public UserId`: trình biên dịch đã tạo canonical constructor `public UserId(String value)` về mặt hành vi và quyền truy cập. Record component tạo ra private final field và public accessor `value()`; mức `private` của field **không** làm canonical constructor thành `private`.

Với record package-private:

```java
record InternalKey(String value) { }
```

Canonical constructor ngầm định của `InternalKey` có mức package-private; mã trong cùng package có thể gọi `new InternalKey("A17")`, còn mã ngoài package bị hạn chế bởi việc truy cập kiểu `InternalKey`.

Record **không tự có** constructor không tham số giống class thông thường: `record Pair(int x, int y) {}` có canonical constructor nhận hai tham số. `new Pair()` không hợp lệ trừ khi tự định nghĩa một constructor bổ sung `Pair() { this(0, 0); }`. Với `record Empty() {}`, canonical constructor vốn có danh sách tham số rỗng.

## 3. Normal canonical constructor: phải khai báo quyền truy cập đủ rộng

Normal canonical constructor lặp lại đầy đủ tên và kiểu tham số tương ứng component trong record header. Ví dụ `public record Account(String owner, int level)` có normal canonical constructor `public Account(String owner, int level)`.

```java
import java.util.Objects;

public record Account(String owner, int level) {
    public Account(String owner, int level) {
        this.owner = Objects.requireNonNull(owner, "owner").trim();
        if (level < 0) {
            throw new IllegalArgumentException("level must be non-negative");
        }
        this.level = level;
    }
}
```

Đây là **toàn bộ ví dụ của tệp `Account.java`**. Khai báo `public Account` hợp lệ vì record là `public`. Với normal canonical constructor, lập trình viên khởi tạo các field thành phần theo quy tắc definite assignment; không thể bỏ quên một field của record. Khi dữ liệu không hợp lệ, constructor được phép ném ngoại lệ không kiểm tra (`IllegalArgumentException`) như trên.

Không được đổi tên tham số canonical thành `String name, int value` khi header là `String owner, int level`: tham số của normal canonical constructor phải có **cùng tên và kiểu** tương ứng các component. Canonical constructor cũng không được khai báo `throws` clause hoặc tự gọi `this(...)`/`super(...)`; phần mềm có thể dùng exception không kiểm tra cho lỗi kiểm tra dữ liệu. Các ràng buộc này là quy tắc constructor của record, độc lập với mức truy cập.

## 4. Compact canonical constructor: cú pháp ngắn nhưng cùng quy tắc truy cập

Compact constructor bỏ danh sách tham số và để trình biên dịch tự gán các component field sau khi thân constructor hoàn thành bình thường. Nó **vẫn là canonical constructor**, không phải constructor khác.

```java
import java.util.Objects;

public record Product(String code, int quantity) {
    public Product {
        code = Objects.requireNonNull(code, "code").trim();
        if (code.isEmpty()) {
            throw new IllegalArgumentException("code is empty");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
    }
}
```

Đây là **tệp độc lập `Product.java`**. Viết `public Product { ... }` là bắt buộc vì `Product` là public record. Tham số `code` và `quantity` được trình biên dịch cung cấp ngầm; có thể gán lại **tham số** `code = code.trim()` để chuẩn hóa. Sau thân compact constructor, Java tự gán giá trị cuối cùng của các tham số vào các field record.

Cố gắng gán `this.code = ...` trực tiếp trong compact constructor là lỗi biên dịch; nếu muốn tự khởi tạo component fields, hãy dùng normal canonical constructor. Compact constructor không có danh sách tham số, không có `throws` clause, không dùng `return` và không có lệnh gọi constructor tường minh. Chỉ được có **một canonical constructor**: không thể khai báo đồng thời normal canonical và compact canonical trong cùng record.

**Điểm thường bị quên:** modifier trước compact constructor chính là modifier của canonical constructor. `Product { ... }` trong `public record Product` **không** tự thừa hưởng `public`; nếu đã viết khai báo tường minh thì phải ghi `public Product { ... }`.

## 5. Constructor bổ sung (non-canonical) được phép `private`

Không phải constructor nào trong record cũng là canonical. Một constructor có danh sách tham số khác chữ ký canonical là **non-canonical constructor**. Ràng buộc “ít nhất rộng bằng record” nêu ở trên **chỉ áp dụng cho canonical constructor**; non-canonical constructor có thể dùng mức truy cập hẹp hơn, bao gồm `private`, miễn tuân thủ quy tắc truy cập constructor thông thường.

```java
public record Coordinate(int x, int y) {
    public Coordinate {
        if (x < 0 || y < 0) {
            throw new IllegalArgumentException("coordinates must be non-negative");
        }
    }

    private Coordinate(int same) {
        this(same, same); // Chuyển việc khởi tạo tới canonical constructor.
    }

    public static Coordinate onDiagonal(int value) {
        return new Coordinate(value); // Phương thức trong record gọi được constructor private.
    }
}
```

Đây là **tệp độc lập `Coordinate.java`**. `new Coordinate(1, 2)` có thể gọi bên ngoài nơi record public được nhìn thấy; `new Coordinate(3)` **không thể** gọi trực tiếp từ mã bên ngoài vì constructor một tham số là `private`, nhưng `Coordinate.onDiagonal(3)` hợp lệ. Constructor bổ sung phải ủy quyền qua một lời gọi constructor khác của record (`this(...)`), cuối cùng dẫn tới canonical constructor; ví dụ đặt `this(...)` đầu thân nên tương thích JDK 17+.

**Hệ quả cho thiết kế API:** không thể khai báo `public record R(...)` rồi biến canonical constructor thành `private` chỉ để ép mọi client dùng factory. Một public record có canonical constructor public theo quy tắc của ngôn ngữ. Bạn vẫn có thể cung cấp factory tĩnh để tạo thuận tiện, xác thực giá trị ở canonical constructor và giấu các constructor **bổ sung** không muốn lộ. Nếu yêu cầu nghiệp vụ thật sự cấm client gọi constructor đại diện mọi component, hãy cân nhắc dùng class thông thường thay cho public record.

## 6. Record lồng trong class và việc chọn `protected` / `private`

Trong một class, member record có thể mang các modifier truy cập mà top-level record không cho phép. Mức của canonical constructor cần tương ứng với mức của **record lồng**, không phải tự động tương ứng với class chứa.

```java
public class Catalogue {
    public record PublicCode(String code) {
        public PublicCode { }
    }

    protected record ProtectedCode(String code) {
        protected ProtectedCode { }
    }

    record PackageCode(String code) {
        PackageCode { }
    }

    private record PrivateCode(String code) {
        private PrivateCode { }
    }
}
```

Đây là **tệp minh họa độc lập `Catalogue.java`**. Cả bốn khai báo đều hợp lệ. Với `private record PrivateCode`, có thể viết constructor rộng hơn như `public PrivateCode { }`, nhưng điều đó không thay đổi mức `private` của kiểu record. Với `protected record ProtectedCode`, constructor `protected` hoặc `public` hợp lệ; constructor package-private hay `private` là lỗi.

Record thành viên trong một `interface` là member type **ngầm định `public static`**; vì thế khi khai báo canonical constructor tường minh trong record đó, cũng phải tuân thủ yêu cầu của public record. Còn muốn kiểm soát truy cập ở ranh giới package/module, phải xem cả quyền truy cập của lớp chứa và cơ chế export package, ngoài modifier trên constructor.

## 7. Ví dụ hoàn chỉnh: bốn mức truy cập và constructor bổ sung

Tạo một tệp duy nhất tên `RecordConstructorAccessDemo.java` với chương trình dưới đây. Mọi record nằm trong class chứa để các ví dụ `protected` và `private` đều ở vị trí Java cho phép.

```java
public class RecordConstructorAccessDemo {
    public record PublicOrder(String code, int count) {
        public PublicOrder {
            if (code == null || code.isBlank()) {
                throw new IllegalArgumentException("code is required");
            }
            if (count <= 0) {
                throw new IllegalArgumentException("count must be positive");
            }
            code = code.trim();
        }

        private PublicOrder(String code) {
            this(code, 1);
        }

        public static PublicOrder one(String code) {
            return new PublicOrder(code);
        }
    }

    record PackageOrder(String code) {
        PackageOrder {
            code = code.trim();
        }
    }

    protected record ProtectedOrder(String code) {
        protected ProtectedOrder {
            code = code.trim();
        }
    }

    private record PrivateOrder(String code) {
        private PrivateOrder {
            code = code.trim();
        }
    }

    public record FullOrder(String code) {
        public FullOrder(String code) {
            this.code = java.util.Objects.requireNonNull(code).trim();
        }
    }

    public static void main(String[] args) {
        System.out.println(new PublicOrder("  A-12  ", 2));
        System.out.println(PublicOrder.one("B-3"));
        System.out.println(new PackageOrder(" C-4 "));
        System.out.println(new ProtectedOrder(" P-5 "));
        System.out.println(new PrivateOrder(" S-6 "));
        System.out.println(new FullOrder(" X-7 "));

        try {
            new PublicOrder("BAD", 0);
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+ (không cần `--enable-preview`):

```bash
javac -encoding UTF-8 RecordConstructorAccessDemo.java
java RecordConstructorAccessDemo
```

**Stdout chính xác:**

```text
PublicOrder[code=A-12, count=2]
PublicOrder[code=B-3, count=1]
PackageOrder[code=C-4]
ProtectedOrder[code=P-5]
PrivateOrder[code=S-6]
FullOrder[code=X-7]
count must be positive
```

Giải thích: `PublicOrder` có **public compact canonical constructor** để kiểm tra và chuẩn hóa dữ liệu. Constructor một tham số `private` chỉ được gọi trong record thông qua factory `one`. `PackageOrder`, `ProtectedOrder` và `PrivateOrder` chứng minh các constructor cùng mức với nested record đều hợp lệ. `FullOrder` dùng **normal canonical constructor** public và gán field trực tiếp. Khi `count = 0`, constructor kiểm tra bất biến và ném ngoại lệ; vì vậy không tạo đối tượng chứa dữ liệu sai.

## 8. Mẫu sai thường gặp (các đoạn cố ý không biên dịch)

**Sai 1 — bỏ `public` trên compact constructor của public record:**

```java
public record BadTicket(String code) {
    BadTicket { // LỖI: canonical constructor package-private hẹp hơn public record.
        code = code.trim();
    }
}
```

**Sửa:** `public BadTicket { ... }`, hoặc bỏ hẳn constructor nếu không cần kiểm tra/chuẩn hóa.

**Sai 2 — khai báo canonical constructor `private` trong public record:**

```java
public record BadId(String value) {
    private BadId(String value) { // LỖI: canonical constructor không thể private.
        this.value = value;
    }
}
```

**Sửa:** đổi thành `public BadId(String value)` hoặc `public BadId { ... }`. Việc muốn ẩn cách tạo record không cho phép thu hẹp canonical constructor của public record.

**Sai 3 — record package-private nhưng canonical constructor private:**

```java
record InternalRecord(int id) {
    private InternalRecord { // LỖI: record package-private không cho canonical private.
        if (id < 0) throw new IllegalArgumentException("id");
    }
}
```

**Sửa:** dùng `InternalRecord { ... }` (package-private), `protected InternalRecord { ... }`, hoặc `public InternalRecord { ... }` tùy chủ đích.

**Sai 4 — tưởng overload một tham số là canonical khi record có hai component:**

```java
public record BadPoint(int x, int y) {
    private BadPoint(int x) {
        this.x = x; // LỖI: constructor bổ sung phải ủy quyền, không tự khởi tạo field.
        this.y = x;
    }
}
```

**Sửa:** `private BadPoint(int x) { this(x, x); }`. Overload này có thể `private` vì nó **không** trùng chữ ký canonical. Trường hợp này là lỗi ủy quyền constructor, không phải vi phạm mức truy cập của canonical constructor.

**Sai 5 — dùng đồng thời cả compact và normal canonical:**

```java
public record BadPair(int left, int right) {
    public BadPair { }
    public BadPair(int left, int right) {
        this.left = left;
        this.right = right;
    } // LỖI: hai khai báo cùng là canonical constructor.
}
```

**Sửa:** chọn một trong hai dạng canonical; nếu muốn thêm cách tạo khác, constructor đó phải có chữ ký khác và ủy quyền qua `this(...)`.

## 9. Checklist khi thiết kế constructor của record

1. **Xác định record là public, protected, package-private hay private.** Nếu là top-level, chỉ chọn public/package-private; protected/private là các trường hợp nested member phù hợp.
2. **Xác định constructor có phải canonical không.** Signature normal canonical dựa trên danh sách component; compact constructor luôn chính là canonical.
3. **Nếu canonical khai báo tường minh, đảm bảo quyền truy cập không hẹp hơn record.** Public record bắt buộc public canonical; protected record cần protected/public; package-private không được private; private record cho phép tất cả.
4. **Nếu không cần logic kiểm tra hay chuẩn hóa, cân nhắc để canonical constructor ngầm định.** Nó được trình biên dịch sinh ra với quyền truy cập đúng.
5. **Nếu cần nhiều cách tạo, dùng constructor bổ sung hoặc factory.** Constructor bổ sung có thể private nhưng phải chuyển việc khởi tạo tới constructor khác của record (`this(...)`).
6. **Giữ bất biến dữ liệu ở canonical constructor.** Public record không thể giấu canonical constructor; phải chặn dữ liệu không hợp lệ ngay tại đường tạo này.
7. **Kiểm tra từ vị trí mã gọi thực tế.** Một public constructor trong private nested record vẫn không mở quyền truy cập tới type; ngược lại, method bên trong lớp chứa có thể truy cập các member private hợp lệ.
8. **Dùng JDK mục tiêu hiện đại.** Code trong bài dành cho record chính thức từ Java 16, nên biên dịch bằng JDK 17+ mà không cần preview flags. Không sao chép tùy chọn hoặc quy tắc thử nghiệm của Java 14/15.

## Tài liệu tham khảo chính thức

- Java Language Specification, §8.10.4 *Record Constructor Declarations* (quy tắc access của canonical và compact constructor): https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.4
- Java Language Specification, §8.10 *Record Classes*: https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10
- Oracle, *Record Classes* (cú pháp record ổn định và cách dùng): https://docs.oracle.com/en/java/javase/17/language/records.html
- Oracle, *Java Language Changes* (record trở thành tính năng chính thức ở Java 16): https://docs.oracle.com/en/java/javase/17/language/java-language-changes.html
