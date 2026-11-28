# Các giới hạn về field instance bổ sung và instance initializer

## 1. Trạng thái instance của record được mô tả trong header

Record dùng record header để công bố đầy đủ các component tạo nên trạng thái instance. Mỗi component tương ứng với một field instance `private final` do Java khai báo ngầm. Vì vậy, record không cho phép khai báo thêm field instance riêng trong body và cũng không cho phép khai báo instance initializer block.

Ví dụ hợp lệ:

~~~java
record Product(String code, int quantity) {
    long totalUnits() {
        return quantity;
    }
}
~~~

`code` và `quantity` là hai component duy nhất tạo nên trạng thái instance của `Product`. Phương thức `totalUnits()` có thể tính toán từ component, nhưng không thể bổ sung một field instance như `cachedTotal` để lưu trạng thái ẩn.

Các giới hạn này là quy tắc ngôn ngữ chính thức của record từ Java 16, vẫn áp dụng trong Java hiện đại. Chúng giúp cấu trúc dữ liệu, constructor, accessor và các phương thức giá trị của record cùng dựa trên một danh sách component rõ ràng.

Mục tiêu bài học:

- Hiểu vì sao record không thể khai báo field instance bổ sung.
- Nhận diện instance initializer block không hợp lệ trong record.
- Phân biệt field instance với local variable, phương thức và thành viên static.
- Đặt logic xác thực, chuẩn hóa component vào canonical constructor.
- Chọn cách xử lý khi cần giá trị dẫn xuất, cache hoặc trạng thái thay đổi.
- Tránh nhầm lẫn giữa giới hạn trạng thái của record và bất biến sâu của object.

## 2. Không được khai báo field instance ngoài component

Trong class thông thường, lập trình viên có thể khai báo nhiều field instance:

~~~java
class ProductClass {
    private final String code;
    private int quantity;
    private long cachedTotal;
}
~~~

Record có quy tắc khác. Các component trong header đã xác định các field instance mà record sở hữu. Không được thêm một field instance khác, kể cả field đó là `private`, `final`, `transient` hoặc chỉ dùng để cache.

Khai báo sau không hợp lệ:

~~~java
record Product(String code, int quantity) {
    // Không hợp lệ: field instance bổ sung.
    // private long cachedTotal;
}
~~~

Cũng không thể khai báo một field trùng tên component để tự viết lại field do record sinh:

~~~java
record User(String name) {
    // Không hợp lệ: field name đã được khai báo ngầm từ component.
    // private final String name;
}
~~~

Java tự khai báo field component tương ứng với header. Không cần và không được khai báo lại field đó trong body.

### Vì sao record giới hạn field instance?

Record được thiết kế để trạng thái instance có thể được hiểu trực tiếp từ header:

1. Header liệt kê component.
2. Java khai báo field component tương ứng.
3. Canonical constructor khởi tạo các field đó.
4. Accessor cung cấp cách đọc component.
5. `equals()`, `hashCode()` và `toString()` mặc định dựa trên các component.

Nếu record được phép có field instance ẩn, hai object có thể có cùng component nhưng khác trạng thái bổ sung mà API record không thể hiện. Điều đó làm ý nghĩa của bình đẳng theo giá trị và cấu trúc công khai trở nên khó dự đoán.

Quy tắc này không cấm record có hành vi. Record vẫn có thể có nhiều phương thức instance, phương thức static, constructor, kiểu lồng và thành viên static hợp lệ.

## 3. Instance initializer block cũng bị cấm

Class thông thường có thể khai báo instance initializer block. Block này chạy khi mỗi instance được tạo, trước phần thân constructor:

~~~java
class UserClass {
    private final String name;

    {
        System.out.println("Initializing an instance");
    }

    UserClass(String name) {
        this.name = name;
    }
}
~~~

Record không được khai báo instance initializer block:

~~~java
record User(String name) {
    // Không hợp lệ: instance initializer block.
    // {
    //     System.out.println("Initializing an instance");
    // }
}
~~~

Lý do phù hợp với cùng nguyên tắc: record không có trạng thái instance ẩn cần được khởi tạo ngoài các component. Logic gắn với việc nhận và thiết lập component phải được đặt trong canonical constructor.

### Phân biệt instance initializer và static initializer

Record được phép có static initializer block vì block đó khởi tạo trạng thái thuộc về class, không phải từng instance:

~~~java
record StatusCode(int value) {
    static final String CATEGORY;

    static {
        CATEGORY = "HTTP";
    }
}
~~~

`static initializer` chạy khi class được khởi tạo theo quy tắc khởi tạo class của Java. Nó không chạy một lần cho mỗi object và không thể dùng `this` hoặc đọc component của một instance chưa được truyền vào.

| Khối khởi tạo | Record có cho phép? | Phạm vi |
| --- | --- | --- |
| Instance initializer `{ ... }` | Không | Gắn với từng instance. |
| Static initializer `static { ... }` | Có | Gắn với quá trình khởi tạo class. |
| Compact canonical constructor | Có | Xác thực và chuẩn hóa component khi tạo instance. |
| Canonical constructor đầy đủ | Có | Tự gán các field component theo quy tắc record. |

## 4. Đặt logic khởi tạo component trong canonical constructor

Nếu cần xác thực hoặc chuẩn hóa dữ liệu đầu vào, hãy dùng compact canonical constructor hoặc canonical constructor đầy đủ.

Compact canonical constructor thường gọn hơn vì không phải khai báo lại danh sách tham số và không phải tự gán field component:

~~~java
import java.util.Objects;

record UserName(String value) {
    UserName {
        value = Objects.requireNonNull(value, "value").strip();

        if (value.isEmpty()) {
            throw new IllegalArgumentException("value must not be blank");
        }
    }
}
~~~

Trong compact constructor:

- `value` là tham số tương ứng với component `value`.
- Có thể xác thực hoặc gán lại tham số để chuẩn hóa dữ liệu.
- Khi constructor kết thúc bình thường, Java tự gán giá trị cuối cùng của tham số vào field component.
- Không viết `this.value = value` trong compact constructor.

Ví dụ sử dụng:

~~~java
UserName user = new UserName("  Nguyen An  ");
System.out.println(user.value()); // Nguyen An
~~~

Mọi cách tạo `UserName` đều đi qua canonical constructor, nên quy tắc loại bỏ khoảng trắng và từ chối chuỗi rỗng được áp dụng nhất quán.

### Canonical constructor đầy đủ

Khi cần kiểm soát trực tiếp phép gán, có thể khai báo canonical constructor đầy đủ:

~~~java
import java.util.Objects;

record ProductCode(String value) {
    ProductCode(String value) {
        String normalized = Objects.requireNonNull(value, "value").strip();

        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("value is required");
        }

        this.value = normalized;
    }
}
~~~

Với dạng đầy đủ, lập trình viên phải tự gán mọi field component đúng một lần. Khác với compact constructor, không có bước gán field tự động ở cuối phần thân.

Không chuyển logic khởi tạo sang một instance initializer block. Hãy giữ việc xác thực và thiết lập component ở canonical constructor để mọi đường khởi tạo có cùng invariant.

## 5. Phương thức instance được phép và có thể dùng local variable

Không có field instance bổ sung không có nghĩa record không thể khai báo biến trong quá trình xử lý. Phương thức instance có thể dùng local variable, tham số phương thức và các biểu thức tính toán bình thường.

~~~java
record Rectangle(double width, double height) {
    double area() {
        double result = width * height;
        return result;
    }

    boolean isLargerThan(double minimumArea) {
        double currentArea = area();
        return currentArea > minimumArea;
    }
}
~~~

`result` và `currentArea` là local variable. Chúng chỉ tồn tại trong lần gọi phương thức và không trở thành trạng thái instance của record.

Có thể dùng helper method để chia nhỏ logic:

~~~java
record PersonName(String firstName, String lastName) {
    String fullName() {
        return join(firstName, lastName);
    }

    private static String join(String first, String last) {
        return first + " " + last;
    }
}
~~~

Các phương thức không bổ sung field instance. Chúng chỉ tính toán từ component hoặc tham số được truyền vào.

### Giá trị dẫn xuất nên được tính từ component

Nếu một giá trị có thể được tính trực tiếp từ component, hãy cân nhắc cung cấp một phương thức:

~~~java
record OrderLine(int quantity, long unitPrice) {
    long totalPrice() {
        return Math.multiplyExact(quantity, unitPrice);
    }
}
~~~

`totalPrice()` không cần field `cachedTotal`. Mỗi lần gọi, nó tính kết quả từ dữ liệu component hiện tại. `Math.multiplyExact` phát hiện tràn số nguyên và ném `ArithmeticException` thay vì trả về kết quả đã tràn.

## 6. Thành viên static vẫn được phép

Record không được bổ sung trạng thái instance, nhưng vẫn có thể khai báo thành viên static:

```java
record RetryPolicy(int maxAttempts) {
    static final int DEFAULT_MAX_ATTEMPTS = 3;

    static RetryPolicy defaultPolicy() {
        return new RetryPolicy(DEFAULT_MAX_ATTEMPTS);
    }
}
```

`DEFAULT_MAX_ATTEMPTS` là field static final thuộc class. `defaultPolicy()` là static factory method tạo một instance mới.

Record cũng có thể khai báo static initializer:

```java
record Region(String code) {
    static final java.util.Set<String> SUPPORTED;

    static {
        SUPPORTED = java.util.Set.of("VN", "SG", "JP");
    }
}
```

Những thành viên static này không phải field instance ẩn. Chúng dùng chung ở cấp class và không thay đổi danh sách component của mỗi object.

### Static state không phải instance state

Java cho phép khai báo static field mutable trong record, nhưng điều đó không có nghĩa đây luôn là thiết kế tốt:

```java
record Request(String id) {
    // Hợp lệ về mặt ngôn ngữ, nhưng đây là trạng thái dùng chung.
    static int createdCount = 0;
}
```

Nếu cập nhật `createdCount` từ nhiều luồng, cần xử lý đồng bộ hoặc dùng cấu trúc phù hợp như `AtomicInteger`. Một static field mutable có thể tạo trạng thái dùng chung, phụ thuộc thứ tự chạy và gây khó kiểm thử. Chỉ dùng khi nhu cầu ở cấp class thực sự tồn tại; không dùng static field để giả lập một field cache riêng cho từng instance.

## 7. Cần cache kết quả thì nên làm gì?

Một số phép tính có chi phí cao và có thể được gọi nhiều lần. Với class thông thường, có thể cân nhắc cache trong field instance. Record không cho phép cách đó vì không thể thêm field instance.

Có một số hướng thiết kế:

### Tính khi cần

Nếu phép tính đủ rẻ, hãy tính từ component trong phương thức:

```java
record Circle(double radius) {
    double area() {
        return Math.PI * radius * radius;
    }
}
```

Cách này đơn giản, không có trạng thái cache cần đồng bộ và không có nguy cơ cache lệch với component.

### Đưa dữ liệu đã tính thành component khi nó là một phần giá trị

Nếu giá trị tính trước thực sự là một phần của dữ liệu được trao đổi hoặc lưu trữ, có thể khai báo nó thành component:

```java
record ReportSummary(String title, long rowCount, long totalAmount) {}
```

Tuy nhiên, cần cân nhắc nguy cơ dữ liệu lặp lại không nhất quán. Nếu `totalAmount` luôn được tính từ các dòng chi tiết, có thể phù hợp hơn khi tính từ nguồn dữ liệu hoặc tạo snapshot qua factory có kiểm soát.

### Dùng cache bên ngoài với chính sách rõ ràng

Nếu phép tính đắt và cần cache, có thể đặt cache trong một dịch vụ hoặc thành phần riêng, bên ngoài record:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

record DocumentKey(String id, int version) {}

class DocumentPreviewCache {
    private final ConcurrentMap<DocumentKey, String> cache =
        new ConcurrentHashMap<>();

    String getOrCreate(DocumentKey key) {
        return cache.computeIfAbsent(key, this::renderPreview);
    }

    private String renderPreview(DocumentKey key) {
        return "Preview " + key.id() + " v" + key.version();
    }
}
```

Trong ví dụ, `DocumentKey` vẫn là record giá trị không có cache instance ẩn. `DocumentPreviewCache` là class thông thường chịu trách nhiệm vòng đời cache, chính sách xóa và truy cập đồng thời.

`ConcurrentHashMap` chỉ giải quyết một phần yêu cầu đồng thời; ứng dụng vẫn cần cân nhắc giới hạn dung lượng, invalidation và thời gian sống của entry.

### Khi object thực sự cần trạng thái riêng thay đổi theo thời gian

Nếu một object cần lưu cache nội bộ, bộ đếm mutable, trạng thái vòng đời hoặc các field instance không thể mô tả hợp lý bằng component, class thông thường thường là lựa chọn phù hợp hơn.

Đừng cố lách quy tắc record bằng static map toàn cục hoặc component là một holder mutable chỉ để giữ cache ẩn. Hãy chọn kiểu dữ liệu phù hợp với semantics và vòng đời của object.

## 8. Phân biệt không có field bổ sung với bất biến sâu

Record chỉ bảo đảm field component không thể gán lại sau khởi tạo. Nó không tự bảo đảm object được component tham chiếu đến là bất biến.

```java
import java.util.ArrayList;
import java.util.List;

record Team(List<String> members) {}

List<String> source = new ArrayList<>(List.of("An"));
Team team = new Team(source);

source.add("Binh");
System.out.println(team.members()); // [An, Binh]
```

Record không có field instance bổ sung, nhưng component `members` đang tham chiếu đến một `ArrayList` mutable. Nội dung danh sách vẫn có thể thay đổi qua tham chiếu bên ngoài hoặc qua accessor mặc định.

Nếu muốn snapshot cấu trúc danh sách, hãy sao chép phòng vệ trong constructor:

```java
import java.util.List;
import java.util.Objects;

record TeamSnapshot(List<String> members) {
    TeamSnapshot {
        members = List.copyOf(Objects.requireNonNull(members, "members"));
    }
}
```

`List.copyOf` bảo vệ cấu trúc collection nhưng không sao chép sâu các object phần tử. Nếu phần tử cũng mutable, cần thiết kế sao chép sâu hoặc dùng kiểu bất biến phù hợp.

Đây là hai vấn đề khác nhau:

- **Giới hạn field record:** không được khai báo trạng thái instance bổ sung ngoài component.
- **Bất biến của object graph:** cần kiểm soát các object mutable mà component tham chiếu đến.

## 9. Bảng tổng hợp thành viên được phép và không được phép

| Thành viên trong record body | Có được khai báo? | Vai trò |
| --- | --- | --- |
| Field component từ header | Có, do Java khai báo ngầm | Trạng thái instance chính thức của record. |
| Field instance bổ sung | Không | Không được thêm trạng thái instance ẩn. |
| Instance initializer block | Không | Không được thêm bước khởi tạo instance ngoài constructor. |
| Compact canonical constructor | Có | Xác thực và chuẩn hóa tham số component. |
| Canonical constructor đầy đủ | Có | Tự gán tất cả field component. |
| Constructor phụ | Có | Phải ủy quyền bằng `this(...)` đến constructor khác của record. |
| Instance method | Có | Tính toán và cung cấp hành vi dựa trên component. |
| Local variable trong method | Có | Dữ liệu tạm thời trong lần gọi phương thức. |
| Static method | Có | Factory hoặc tiện ích ở cấp class. |
| Static field | Có | Dữ liệu dùng chung ở cấp class. |
| Static initializer block | Có | Khởi tạo thành viên static của class. |
| Nested type | Có | Khai báo kiểu lồng theo quy tắc Java. |

## 10. Những lỗi thường gặp

1. **Thêm field `private final` để cache:** field vẫn là instance field bổ sung nên không hợp lệ. Hãy tính từ component hoặc đặt cache bên ngoài.
2. **Dùng instance initializer block để chuẩn hóa dữ liệu:** record không cho phép block này. Hãy dùng compact canonical constructor.
3. **Nghĩ record không có phương thức instance:** record có thể khai báo nhiều phương thức và helper.
4. **Nhầm local variable với field instance:** local variable trong method được phép vì không trở thành trạng thái lâu dài của object.
5. **Dùng static field mutable để giả lập cache riêng:** static field được chia sẻ giữa các instance, không có vòng đời riêng cho từng object.
6. **Nghĩ không có field bổ sung đồng nghĩa bất biến sâu:** component vẫn có thể tham chiếu đến collection hoặc object mutable.
7. **Gán lại `this.component` trong compact constructor:** hãy chuẩn hóa tham số; Java tự gán field sau khi compact constructor kết thúc bình thường.
8. **Đưa dữ liệu dẫn xuất vào component mà không kiểm soát:** có thể tạo trạng thái lặp lại không nhất quán; chỉ làm vậy khi giá trị đó thực sự thuộc hợp đồng dữ liệu.

## 11. Bài tập thực hành

1. Khai báo `record Rectangle(double width, double height)`. Viết phương thức `area()` mà không dùng field cache.
2. Thử khai báo field instance `private double cachedArea` trong record và giải thích lỗi biên dịch.
3. Thử thêm instance initializer block vào record. Chuyển logic cần thiết sang compact canonical constructor.
4. Khai báo một static final constant và một static initializer block trong record. Giải thích vì sao chúng không phải trạng thái riêng của từng instance.
5. Viết `record UserName(String value)` để chuẩn hóa chuỗi trong compact canonical constructor.
6. Xây dựng một class cache bên ngoài dùng record làm key. Giải thích vì sao cache thuộc class dịch vụ thay vì field instance của record.
7. So sánh record chứa `List<String>` trực tiếp với record dùng `List.copyOf()` trong constructor. Thử sửa collection nguồn và quan sát kết quả.
8. Đề xuất khi nào nên chuyển record thành class thông thường vì object cần trạng thái mutable hoặc cache nội bộ.

## Ghi nhớ

Trạng thái instance của record được mô tả đầy đủ bằng component trong header. Java khai báo field component `private final` từ header, vì vậy record không được thêm field instance khác và không được khai báo instance initializer block. Logic xác thực hoặc chuẩn hóa dữ liệu thuộc canonical constructor; hành vi tính toán thuộc instance method; biến tạm thuộc phạm vi method; dữ liệu dùng chung thuộc thành viên static. Khi cần giá trị dẫn xuất, hãy tính từ component; khi cần cache, cân nhắc một dịch vụ bên ngoài có chính sách vòng đời và đồng bộ; khi object cần trạng thái instance thay đổi độc lập, class thông thường có thể phù hợp hơn. Cuối cùng, không nhầm giới hạn field của record với bất biến sâu: component vẫn có thể tham chiếu đến object mutable và cần được bảo vệ riêng. Đây là các quy tắc ổn định của Java record từ Java 16, vẫn áp dụng trong Java hiện đại.

**Tài liệu tham khảo chính thức:**

- [OpenJDK JEP 395 – Records](https://openjdk.org/jeps/395)
- [Java Language Specification – Record Classes, mục 8.10](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.10)
- [Java Language Specification – Class Members, mục 8.2](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.2)
- [Java Language Specification – Instance Initializers, mục 8.6](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.6)
- [Java API – List.copyOf](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))
