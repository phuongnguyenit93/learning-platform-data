# Giới hạn trường đối tượng bổ sung và khối khởi tạo trong record

## Mục tiêu

Khi tổ chức phần thân (`body`) của một `record`, bạn cần biết loại thành viên nào có thể đặt vào đó và loại nào bị Java cấm. Sau bài này, bạn có thể:

- Giải thích vì sao **chỉ record header xác định trạng thái instance** của record.
- Phân biệt **component fields được sinh ngầm**, **trường đối tượng bổ sung bị cấm** và **trường static hợp lệ**.
- Phân biệt **instance initializer bị cấm** với **static initializer được phép** và **compact canonical constructor** dùng để kiểm tra/chuẩn hóa từng instance.
- Tổ chức instance method để tính dữ liệu dẫn xuất mà không tạo instance field trái quy tắc.
- Biên dịch, chạy ví dụ Java và chỉ ra lỗi biên dịch ở những khai báo sai.

Đây là các quy tắc **vẫn có hiệu lực trong Java hiện đại**. Record là tính năng chính thức của Java từ phiên bản 16; toàn bộ mã chạy độc lập trong bài dùng **JDK 17+**, không cần bật preview hay dựa vào cơ chế đã lỗi thời.

## 1. Vì sao record hạn chế trạng thái instance?

Ví dụ cơ bản:

```java
record Product(String code, int quantity) {}
```

Header `(String code, int quantity)` mô tả toàn bộ **các thành phần trạng thái (record components)**. Trình biên dịch cung cấp cho mỗi component một field cùng tên và kiểu, với các thuộc tính **`private final` và không phải `static`**; các field đó được **khai báo ngầm**, không cần và không được khai báo lại ở phần thân. Nếu không tự khai báo hợp lệ, accessor `code()` và `quantity()` cũng được sinh.

Về mặt mô hình, một record dành cho nhóm giá trị dữ liệu có **cấu trúc được công bố ngay tại header**. Việc thêm những instance fields khác trong thân sẽ tạo trạng thái không xuất hiện trong mô tả cấu trúc này. Vì thế Java đặt giới hạn trực tiếp lên khai báo phần thân.

**Điểm rất dễ nhầm:** Câu “record không có instance fields” là **sai**. Record *có* những instance fields ngầm ứng với components; Java chỉ **cấm khai báo thêm instance fields trong thân record**.

Ví dụ `new Product("A-10", 3)` lưu `code = "A-10"` và `quantity = 3`. Không có một field bí mật thứ ba được phép tạo chỉ bằng cách khai báo `private int count` hoặc `private final int cache` trong phần thân.

## 2. Bảng phân biệt các khai báo hợp lệ và không hợp lệ

| Nội dung trong thân record | Được phép? | Giải thích |
| --- | --- | --- |
| Component fields do Java tạo từ header | **Có, ngầm định** | Mỗi component tương ứng một field `private final` không static |
| Field tự khai báo như `int cache;` | **Không** | Đây là **non-static field declaration** thêm vào record |
| Field tự khai báo `private final int cache = 0;` | **Không** | Thêm `final` hoặc giá trị khởi tạo không làm nó thành static |
| Field `private static final int LIMIT = 100;` | **Có** | Hằng cấp lớp, chia sẻ cho mọi instance |
| Field `private static AtomicInteger counter;` | **Có** | Trạng thái cấp lớp; cần quản lý đồng thời và vòng đời |
| Khối `{ ... }` trực tiếp trong thân | **Không** | Đó là **instance initializer**, bị cấm |
| Khối `static { ... }` | **Có** | Static initializer chạy trong giai đoạn khởi tạo lớp |
| Compact canonical constructor `Product { ... }` | **Có** | Xử lý tham số của từng lần tạo đối tượng |
| Normal canonical constructor `Product(String code, int quantity) { ... }` | **Có** | Tự kiểm tra, khởi tạo các component fields đúng quy tắc |
| Instance method `int doubled() { ... }` | **Có** | Hành vi tính từ dữ liệu đã có, không tự thêm trạng thái |
| Static factory `static Product of(...)` | **Có** | Phương thức cấp lớp gọi đường khởi tạo hợp lệ |
| Nested class, interface, enum hoặc record | **Có** | Kiểu lồng là thành viên hỗ trợ, không phải instance field bổ sung |

Các quy tắc **cấm non-static field declaration và instance initializer** được định nghĩa trực tiếp trong Java Language Specification, mục `8.10.2 Record Body Declarations`. Đây là lỗi ở thời điểm **biên dịch**, không phải cảnh báo về phong cách lập trình.

## 3. Instance field bổ sung: bị cấm, kể cả khi final

Các ví dụ dưới đây **cố ý sai** và chỉ nên biên dịch riêng từng ví dụ nếu bạn muốn quan sát thông báo lỗi.

### 3.1. Trường thông thường

```java
record BadProduct(String code, int quantity) {
    private int cachedTotal;  // ERROR: non-static field in a record.
}
```

`cachedTotal` là field cấp đối tượng do người viết khai báo thêm, không được dẫn xuất từ header. Compiler từ chối ngay cả khi field là `private` và không có phương thức nào sử dụng nó.

### 3.2. Thêm final hoặc giá trị khởi tạo vẫn sai

```java
record BadProduct(String code, int quantity) {
    private final int cachedTotal = 0;  // ERROR: still non-static.
}
```

`final` chỉ hạn chế việc gán lại biến. Nó **không** biến field cấp instance thành field cấp lớp. Record không cho phép khai báo mới field này, dù giá trị là hằng hay một kết quả đã tính toán.

### 3.3. Tự khai báo lại field ứng với component cũng sai

```java
record BadProduct(String code, int quantity) {
    private final String code; // ERROR: non-static field declaration
                               // and conflicts with component field.
}
```

Field `code` đã được Java khai báo ngầm từ header. Bạn không được viết thêm field `code` của riêng mình.

Nếu cần thêm dữ liệu thật sự cấu thành **trạng thái giá trị**, hãy cân nhắc đưa nó thành component **với chủ ý**. Tuy nhiên, một component bổ sung cũng thay đổi constructor, accessors, `equals`, `hashCode` và `toString` được suy ra. Không thêm component chỉ để cất một cache kỹ thuật mà các hành vi giá trị không nên phụ thuộc.

## 4. Instance initializer: khối lệnh không có static cũng bị cấm

Trong một class thông thường, khối `{ ... }` trực tiếp trong class body có thể là **instance initializer**. Nhưng trong record, dạng này bị cấm:

```java
record BadProduct(String code, int quantity) {
    {
        System.out.println("creating an instance"); // ERROR.
    }
}
```

Dấu ngoặc ở ví dụ trên là một khối độc lập trong thân record: không phải thân method, không phải constructor và không có từ khóa `static`. Compiler từ chối toàn bộ instance initializer.

**Cách thay thế đúng:** Chuyển logic kiểm tra hoặc chuẩn hóa đầu vào sang **canonical constructor**. Với compact constructor, tên tham số được suy ra từ header, và compiler tự gán tham số đã xử lý vào component fields khi thân constructor kết thúc bình thường.

```java
record Product(String code, int quantity) {
    Product {
        java.util.Objects.requireNonNull(code, "code");
        code = code.strip();

        if (code.isEmpty()) {
            throw new IllegalArgumentException("code is blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
        // Java assigns this.code and this.quantity afterward.
    }
}
```

Đây là **khai báo record hợp lệ**, có thể đặt trong một tệp nguồn nhưng chưa chứa `main`. Nó diễn đạt đúng ý định: mọi lần tạo `Product` đều phải đi qua cùng quy tắc đầu vào. `Product { ... }` là compact canonical constructor, **không** phải instance initializer. Điểm khác nhau thấy ngay ở **tên constructor `Product` đứng trước dấu `{`**.

Trong compact constructor, **không** viết `this.code = code;`: compiler cấm gán trực tiếp component field trong dạng này vì nó tự gán sau thân. Nếu cần điều khiển các phép gán trực tiếp, bạn có thể viết **normal canonical constructor** với danh sách tham số khớp header và tự khởi tạo đầy đủ các field.

## 5. Static field và static initializer: hoàn toàn hợp lệ

Record vẫn là một class. Trong phần thân, bạn có thể khai báo thành viên cấp lớp bằng `static`:

```java
record Invoice(String code, int units) {
    private static final int MAX_UNITS = 100;
    private static final String PREFIX;

    static {
        PREFIX = "INV";
    }

    Invoice {
        if (units < 1 || units > MAX_UNITS) {
            throw new IllegalArgumentException(
                    "units must be between 1 and 100");
        }
    }

    String display() {
        return PREFIX + "-" + code + " x" + units;
    }
}
```

Đoạn này minh họa **khai báo record hợp lệ**, chưa có method `main`:

- `MAX_UNITS` là một hằng static. Mọi `Invoice` sử dụng chung giới hạn.
- `PREFIX` là một static final field, được gán trong `static { ... }`.
- Khối `static { ... }` là **static initializer**, không bị cấm như instance initializer.
- Compact constructor kiểm tra `units` cho **mỗi lần tạo đối tượng**.
- `display()` là instance method, được phép sử dụng các component `code` và `units` cùng giá trị static `PREFIX`.

Static initializer chạy theo cơ chế **khởi tạo lớp** của Java, về nguyên tắc mỗi lần một lớp được khởi tạo thành công, chứ **không chạy lại cho từng đối tượng**. Thời điểm chính xác tuân theo quy tắc class initialization của JVM; ví dụ việc chỉ đọc một hằng `static final` có giá trị compile-time constant có thể không làm lớp được khởi tạo. Hãy tránh dùng static initializer như một nơi giả lập “mỗi instance chạy một lần”.

**Static field không phải trạng thái riêng của từng record.** Một biến `static` được dùng chung cho mọi instance và cũng không tham gia các triển khai `equals`/`hashCode` mặc định của record. Nếu bạn dùng static state có thể thay đổi, cần nghĩ đến vòng đời, dữ liệu chung giữa các request và an toàn luồng.

## 6. Chương trình hoàn chỉnh: nhìn thấy sự khác biệt khi chạy

Tạo tệp **`RecordBodyDemo.java`**:

```java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

public final class RecordBodyDemo {
    record Item(String sku, int quantity) {
        // Class-level constant, not an extra instance field.
        private static final int MIN_QUANTITY = 1;

        // Shared class-level counter, not part of record equality.
        private static final AtomicInteger CREATED =
                new AtomicInteger();

        // A static final field initialized by a static initializer.
        private static final String PREFIX;

        static {
            PREFIX = "ITEM";
        }

        // Compact canonical constructor: runs per construction.
        Item {
            Objects.requireNonNull(sku, "sku");
            sku = sku.strip();

            if (sku.isEmpty()) {
                throw new IllegalArgumentException("sku is blank");
            }
            if (quantity < MIN_QUANTITY) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }

            // Count constructions that passed the checks above.
            CREATED.incrementAndGet();
        }

        // Instance method: computes a value from existing components.
        String label() {
            return PREFIX + "[" + sku() + " x" + quantity() + "]";
        }

        // Static method: reads shared class-level data.
        static int createdCount() {
            return CREATED.get();
        }
    }

    private static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        Item first = new Item("  Pen  ", 2);
        Item second = new Item("Pen", 2);

        check(first.equals(second), "same component values");
        check(first.sku().equals("Pen"), "normalized sku");
        check(Item.createdCount() == 2, "counter after two");

        System.out.println("item = " + first.label());
        System.out.println("same values = " + first.equals(second));
        System.out.println("created = " + Item.createdCount());

        try {
            new Item("   ", 3);
            throw new AssertionError("Blank SKU must fail");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid sku = "
                    + expected.getMessage());
        }

        try {
            new Item("Pencil", 0);
            throw new AssertionError("Quantity zero must fail");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid quantity = "
                    + expected.getMessage());
        }

        check(Item.createdCount() == 2, "counter after rejection");
        System.out.println(
                "created after errors = " + Item.createdCount());
    }
}
```

Lưu đúng tên tệp rồi biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac --release 17 RecordBodyDemo.java
java RecordBodyDemo
```

**Stdout mong đợi:**

```text
item = ITEM[Pen x2]
same values = true
created = 2
invalid sku = sku is blank
invalid quantity = quantity must be positive
created after errors = 2
```

### Giải thích hành vi

1. `Item` có hai component trong header: `sku` và `quantity`. Không có **bất kỳ instance field nào khai báo thêm** trong body.
2. `PREFIX` được gán từ static initializer; cả `first` và `second` dùng chung chuỗi `"ITEM"` trong method `label()`.
3. Compact constructor dùng `sku = sku.strip()` để chuẩn hóa **tham số**; sau thân, compiler mới gán vào component field tương ứng. Vì thế hai đối tượng cùng có `sku() == "Pen"` theo nghĩa giá trị chuỗi và `quantity() == 2`.
4. `first.equals(second)` là `true` do hai record cùng kiểu và các component mang cùng giá trị. Static counter `CREATED` **không nằm trong hợp đồng giá trị của record**, nên không ảnh hưởng so sánh.
5. `CREATED` là `static final` nhưng đối tượng `AtomicInteger` mà nó tham chiếu **có trạng thái biến đổi**. Hai lần tạo hợp lệ tăng số đếm lên `2`. Hai lần cố tạo với dữ liệu sai ném ngoại lệ trước lệnh tăng; kết quả cuối vẫn là `2`.
6. `AtomicInteger` được dùng để việc tăng đếm an toàn khi có nhiều luồng. Đây là **ví dụ về static state chia sẻ**, không phải bộ đếm số đối tượng đang còn sống hay một phần dữ liệu của từng `Item`.

Mã có các `check(...)` ném `AssertionError` nếu kết quả khác contract. Dòng stdout cuối cùng chỉ xuất hiện khi các trường hợp hợp lệ và ngoại lệ đã được kiểm chứng theo các điều kiện trong `main`.

## 7. Cần dữ liệu tính toán bổ sung? Dùng instance method

Nhu cầu thực tế thường là lưu `unitPrice` và `quantity` rồi tính `totalPrice`. Do record không cho thêm instance field `cachedTotal`, hãy xem kết quả dẫn xuất có thực sự cần lưu hay có thể **tính từ components mỗi lần truy cập**.

Ví dụ hợp lệ:

```java
record OrderLine(String sku, long unitPrice, int quantity) {
    OrderLine {
        java.util.Objects.requireNonNull(sku, "sku");
        if (unitPrice < 0 || quantity < 0) {
            throw new IllegalArgumentException("negative amount");
        }
    }

    long totalPrice() {
        return Math.multiplyExact(unitPrice, quantity);
    }
}
```

`totalPrice()` là instance method, không khai báo field mới. `Math.multiplyExact` giúp báo `ArithmeticException` nếu phép nhân vượt phạm vi kiểu `long` thay vì âm thầm tràn. Đây là đoạn khai báo record hợp lệ **chưa có `main`**.

Cân nhắc ba cách thiết kế:

- **Tính khi gọi method:** phù hợp khi phép tính rẻ, chỉ phụ thuộc components và không cần cache.
- **Đưa vào header:** chỉ phù hợp nếu giá trị bổ sung thực sự là component của mô hình dữ liệu; việc này thay đổi canonical constructor và các hành vi giá trị mặc định.
- **Dùng class thường hoặc bộ nhớ đệm bên ngoài:** cân nhắc nếu bắt buộc có **trạng thái phụ thuộc từng instance nhưng không phải component**, như cache tính toán có vòng đời riêng. Static map không tự biến thành per-instance field và có thể phát sinh vấn đề đồng thời/rò rỉ bộ nhớ; không dùng vô điều kiện.

Quyết định đúng phụ thuộc vào **mô hình giá trị và yêu cầu hiệu năng**, không phải cố vượt qua lỗi compiler của record.

## 8. Phân biệt ba thời điểm xử lý

| Cơ chế | Thời điểm | Áp dụng cho record? | Tác dụng thích hợp |
| --- | --- | --- | --- |
| Static field initializer hoặc `static { ... }` | Khi **class được khởi tạo** | **Có** | Chuẩn bị dữ liệu dùng chung, hằng cấu hình cấp class |
| Instance initializer `{ ... }` trực tiếp trong body | Trong class thường, mỗi lần khởi tạo instance | **Không** | Không dùng cho record |
| Canonical constructor, nhất là dạng compact | Mỗi lần tạo record bằng constructor | **Có** | Kiểm tra, chuẩn hóa, sao chép phòng vệ các component |
| Instance method | Khi được gọi trên một record instance | **Có** | Tính/biểu diễn dữ liệu từ components |

**Khác biệt quan trọng trong mã nguồn:**

```java
record Example(int value) {
    static {
        // Valid: class-level initialization.
    }

    Example {
        // Valid: compact canonical constructor.
        if (value < 0) {
            throw new IllegalArgumentException("negative");
        }
    }

    // A standalone { ... } block HERE would be invalid.
}
```

Không nhầm `Example { ... }` với một initializer thông thường: việc có tên record trước dấu `{` xác định đó là compact canonical constructor. Cũng không nhầm `static { ... }` với initializer theo từng đối tượng.

### Static context không có `this` của instance

Trong static initializer và static method, không có `this` trỏ đến một `Example` cụ thể. Bạn không thể truy cập trực tiếp component field `value` theo cách cần instance:

```java
record Wrong(int value) {
    static {
        System.out.println(value); // ERROR: non-static variable
                                   // cannot be referenced here.
    }
}
```

Đây là mã **cố ý sai**. Nếu muốn xử lý một giá trị của đối tượng, dùng canonical constructor hoặc instance method, hoặc truyền một instance vào phương thức static:

```java
record Example(int value) {
    static int read(Example e) {
        return e.value();
    }
}
```

Đây là khai báo hợp lệ: phương thức static không dùng `this`, mà làm việc với instance `e` được truyền tường minh.

## 9. Những hiểu lầm thường gặp

| Hiểu lầm | Vấn đề | Cách hiểu đúng |
| --- | --- | --- |
| “Record không có instance fields” | Bỏ qua field ngầm của component | Có field ngầm `private final` cho từng component; chỉ **cấm khai báo thêm** |
| “Thêm `final` thì được khai báo cache riêng” | `final` không đồng nghĩa `static` | Mọi non-static field declaration trong record body đều bị cấm |
| “Một khối `{ ... }` có thể in log lúc tạo” | Instance initializer bị JLS cấm | Dùng constructor khi logic liên quan từng lần khởi tạo |
| “Compact constructor là instance initializer hợp lệ” | Nhầm hai cú pháp và cơ chế gán | `RecordName { ... }` là canonical constructor; compiler gán fields sau thân |
| “Khối `static` chạy với mỗi `new`” | Nhầm khởi tạo class với instance | Static initializer chạy ở bước class initialization |
| “Static counter thuộc về mỗi record” | Tất cả instances cùng tham chiếu dữ liệu static | Static state chia sẻ, không tham gia `equals`/`hashCode` mặc định |
| “Không viết được instance method trong record” | Nhầm cấm state bổ sung với cấm hành vi | Instance method được phép, có thể dùng components và trả giá trị tính toán |
| “Chỉ cần đặt cache vào header cho hết lỗi” | Có thể thay đổi mô hình giá trị không chủ ý | Cân nhắc tính động hoặc class thường; thêm component chỉ khi có ý nghĩa nghiệp vụ |
| “Field của record `final` nên list bên trong tự bất biến” | `final` chỉ cố định tham chiếu | Dùng phòng vệ như `List.copyOf` khi cần; lưu ý sao chép nông |
| “Khởi tạo bằng static factory bỏ qua constructor” | Factory vẫn gọi đường khởi tạo record | Giữ invariant trong canonical constructor để mọi đường `new` đều hợp lệ |

## 10. Bài thực hành

Thiết kế `record CartLine(String productId, int quantity, long unitPrice)` với yêu cầu:

1. Có constant cấp lớp `private static final int MAX_QUANTITY = 1000;`.
2. Dùng compact canonical constructor từ chối `null`, mã sản phẩm rỗng sau khi `strip()`, `quantity` ngoài miền `1..1000` và `unitPrice` âm.
3. Có instance method `long subtotal()`, tính bằng `Math.multiplyExact(unitPrice, quantity)`.
4. Có static factory `static CartLine one(String id, long price)` gọi `new CartLine(id, 1, price)`.
5. Nếu muốn theo dõi số lần tạo record hợp lệ trong bài thực hành, dùng `static AtomicInteger`; chỉ tăng sau các kiểm tra đầu vào. Giải thích vì sao biến này **không** phải số instance hiện còn trong bộ nhớ.
6. Viết dữ liệu kiểm chứng cho `quantity = 0, 1, 1000, 1001`; `productId = null`, chuỗi trắng; `unitPrice = -1, 0` và số lớn gây tràn trong `subtotal()`.

Thử cố ý thêm `private long subtotalCache;` và một instance initializer `{ ... }`. Dự đoán chúng **không biên dịch**, trong khi một static initializer và instance method hợp lệ. Sau đó xóa hai phần sai và biên dịch lại.

**Tiêu chí hoàn thành:** Bạn xác định được đâu là field ngầm từ header, đâu là field bị cấm, điểm đặt khởi tạo theo từng instance và điểm đặt khởi tạo cấp lớp; đồng thời giải thích được vì sao kết quả từ instance method không nhất thiết phải lưu thành một trường mới.

## Nguồn kiểm chứng

- [Java Language Specification, `8.10.2 Record Body Declarations](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10.2): quy tắc cấm non-static fields và instance initializers.
- [Oracle Java SE 17 — Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html): static fields, static initializers, methods và hạn chế của record.
- [dev.java — Using Records to Model Immutable Data](https://dev.java/learn/records/): cách tổ chức component, constructor và tính bất biến.

**Ghi nhớ:** Trạng thái riêng của mỗi record được công bố trong **header** và được lưu qua các component fields do compiler cung cấp. Body record có thể bổ sung **hành vi**, **constructor**, **thành viên static** và **static initializer**, nhưng **không được khai báo thêm instance fields hay instance initializer**.