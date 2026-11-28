# Kiểm tra bất biến và bảo vệ component có thể thay đổi trong Java 27

Trong chương **Records và hệ phân cấp sealed**, `record` thường được dùng để biểu diễn một giá trị có cấu trúc: địa chỉ, khoảng thời gian, kết quả xử lý, dữ liệu cấu hình hoặc một biến thể của mô hình domain. Cú pháp ngắn gọn dễ tạo ấn tượng rằng record luôn bất biến. Thực tế, Java bảo đảm các **component field** của record là `private final`, nhưng không tự làm bất biến những đối tượng mà các field tham chiếu đến.

Để record luôn hợp lệ và không bị sửa từ bên ngoài, cần giải quyết **hai vấn đề riêng biệt**:

1. **Kiểm tra bất biến (invariant)**: mọi instance được tạo hợp lệ phải thỏa mãn những quy tắc nghiệp vụ, ví dụ `start < end`, danh sách không rỗng hoặc số lượng không âm.
2. **Bảo vệ component có thể thay đổi (mutable component)**: sau khi xây dựng record, mã bên ngoài không được thay đổi trạng thái quan sát được của record thông qua tham chiếu đầu vào hoặc giá trị trả về từ accessor.

Bài học áp dụng cho Java 27, tập trung vào **canonical/compact constructor**, `List.copyOf`, `Map.copyOf`, mảng, sao chép phòng vệ (*defensive copying*), `equals`/`hashCode` và cách kết hợp record với sealed hierarchy. Không cần thư viện ngoài hoặc API đã lỗi thời.

## 1. Record bất biến đến mức nào?

Xem record đơn giản:

```java
record Point(int x, int y) { }

Point point = new Point(10, 20);
System.out.println(point.x()); // 10
System.out.println(point.y()); // 20
```

Trình biên dịch cung cấp canonical constructor, accessor `x()`/`y()`, `equals`, `hashCode` và `toString` nếu không khai báo phiên bản riêng. Hai component `int` là giá trị nguyên thủy, không có đối tượng mutable nằm phía sau. Vì vậy, đây là một ví dụ rất thuận lợi cho mô hình giá trị bất biến.

Ngược lại:

```java
import java.util.ArrayList;
import java.util.List;

record UnsafeOrder(List<String> items) { }

List<String> cart = new ArrayList<>(List.of("Book"));
UnsafeOrder order = new UnsafeOrder(cart);

cart.add("Pen");
System.out.println(order.items()); // [Book, Pen]

order.items().add("Bag");
System.out.println(cart); // [Book, Pen, Bag]
```

`items` là một `final` reference đến cùng đối tượng `ArrayList` mà `cart` đang tham chiếu. Field `items` không thể được gán sang list khác sau khi khởi tạo, nhưng list được tham chiếu vẫn có thể sửa. Accessor mặc định `items()` cũng trả về chính tham chiếu đó.

Do đó, **record là shallowly immutable (bất biến nông)** theo hợp đồng Java API, không mặc nhiên deep immutable. Muốn tạo kiểu giá trị ổn định, hãy phân tích khả năng thay đổi của từng component.

### 1.1. Phân loại component theo rủi ro

| Component | Có rủi ro thay đổi trạng thái? | Hướng xử lý |
| --- | --- | --- |
| `int`, `long`, `boolean`, `double` | Không có tham chiếu mutable | Kiểm tra miền giá trị và quan hệ giữa component |
| `String`, `UUID`, `Instant`, `LocalDate`, `BigDecimal` | Những kiểu này bất biến | Kiểm tra null và ràng buộc nghiệp vụ |
| `List<String>` | Bản thân list có thể mutable | Tạo snapshot không thể sửa bằng `List.copyOf` |
| `Set<String>`, `Map<String, Integer>` | Cấu trúc có thể mutable | Dùng `Set.copyOf`, `Map.copyOf` nếu quy tắc null/thứ tự phù hợp |
| `int[]`, `byte[]`, `String[]` | Có thể sửa phần tử | Sao chép khi nhận **và** khi trả ra; xem thêm quy tắc equality |
| `List<StringBuilder>`, `List<MutableItem>` | Cả cấu trúc và phần tử có thể mutable | Chuyển phần tử sang kiểu bất biến hoặc sao chép từng phần tử |
| `Date`, `Calendar` hoặc một bean mutable | Đối tượng thành phần có thể sửa | Ưu tiên kiểu `java.time` bất biến hoặc sao chép theo hợp đồng domain |

`final` chỉ bảo vệ **phép gán lại field**, không bảo vệ toàn bộ đồ thị đối tượng ở phía sau tham chiếu.

## 2. Invariant là gì và nên kiểm tra ở đâu?

Invariant là điều kiện phải đúng đối với mọi instance hợp lệ trong suốt vòng đời đối tượng. Ví dụ, một khoảng thời gian phải có điểm đầu trước điểm cuối:

```java
import java.time.Instant;
import java.util.Objects;

record TimeWindow(Instant start, Instant end) {
    TimeWindow {
        Objects.requireNonNull(start, "start must not be null");
        Objects.requireNonNull(end, "end must not be null");

        if (!start.isBefore(end)) {
            throw new IllegalArgumentException("start must be before end");
        }
    }
}
```

`TimeWindow { ... }` là **compact canonical constructor** của record. Hai tham số `start`, `end` được khai báo ngầm từ record header. Nếu kiểm tra thành công, Java tự gán chúng vào các component field tương ứng **sau khi thân constructor hoàn tất bình thường**.

```java
TimeWindow ok = new TimeWindow(
    Instant.parse("2026-11-27T09:00:00Z"),
    Instant.parse("2026-11-27T10:00:00Z")
);

// Ném IllegalArgumentException: start không trước end.
TimeWindow invalid = new TimeWindow(
    Instant.parse("2026-11-27T10:00:00Z"),
    Instant.parse("2026-11-27T09:00:00Z")
);
```

Các đối tượng `Instant` bất biến. Sau khi constructor hợp lệ, không có cách sửa `start` hay `end` từ bên ngoài nên invariant được bảo vệ bởi thiết kế này.

### 2.1. Các nhóm invariant phổ biến

| Nhóm quy tắc | Ví dụ | Cách xác thực |
| --- | --- | --- |
| Không null | `id`, `start`, `items` bắt buộc | `Objects.requireNonNull(...)` |
| Miền số | `quantity >= 0`, `price > 0` | So sánh, ném `IllegalArgumentException` |
| Chuỗi | `id` không rỗng, chiều dài giới hạn | Chuẩn hóa rồi kiểm tra `isBlank`, `length` |
| Quan hệ giữa component | `start < end`, `min <= max` | Kiểm tra chéo trong canonical constructor |
| Collection | Không có phần tử null, không rỗng, số lượng tối đa | Snapshot trước; kiểm tra trên snapshot |
| Tính duy nhất | Các mã thành phần không trùng | Kiểm tra duplicate trên một bản snapshot |
| Trạng thái của từng phần tử | Mỗi item phải hợp lệ | Kiểm tra từng phần tử hoặc dùng kiểu item bất biến có invariant riêng |

Không nên nhầm invariant của một **giá trị** với chính sách thay đổi theo thời gian. Ví dụ "giá hiện tại không vượt ngưỡng khuyến mãi" phụ thuộc cấu hình bên ngoài, không nhất thiết là invariant cố hữu của `Price` record. Chọn ràng buộc thích hợp với trách nhiệm của kiểu.

## 3. Compact constructor: xác thực và chuẩn hóa trước khi gán field

Compact constructor thường là lựa chọn rõ ràng nhất khi muốn kiểm tra hoặc chuẩn hóa component:

```java
import java.util.Objects;

record UserId(String value) {
    UserId {
        value = Objects.requireNonNull(value, "value").strip();

        if (value.isEmpty()) {
            throw new IllegalArgumentException("User id must not be empty");
        }
        if (value.length() > 64) {
            throw new IllegalArgumentException("User id is too long");
        }
    }
}

UserId id = new UserId("  u-42  ");
System.out.println(id.value()); // u-42
```

Trong constructor, `value` là **tham số ngầm định**, nên gán `value = value.strip()` là hợp lệ. Khi thân constructor hoàn tất, compiler mới gán kết quả cuối cùng của tham số vào field `this.value`.

### 3.1. Quy tắc cần nhớ về compact constructor

- Không viết `this.value = ...` để tự gán component field trong compact constructor; đó là lỗi biên dịch.
- Không đặt `return` hay lời gọi constructor tường minh `this(...)`/`super(...)` trong thân compact constructor.
- Được kiểm tra, chuẩn hóa và gán lại **tham số** `value`, `items`, ... trước khi field được gán ngầm.
- Nếu constructor ném exception, quá trình tạo record dừng; đối tượng không được trả về cho người gọi như một instance hợp lệ.
- Canonical constructor được khai báo tường minh phải có phạm vi truy cập ít nhất bằng phạm vi truy cập của record. Ví dụ `public record ...` có compact constructor `public RecordName { ... }`.

Ví dụ sau **không hợp lệ**:

```java
record InvalidId(String value) {
    InvalidId {
        // this.value = value.strip(); // Lỗi: gán component field trực tiếp
        // return;                     // Lỗi: compact constructor không có return
    }
}
```

Nếu không cần logic phức tạp, hãy ưu tiên compact constructor thay vì lặp lại toàn bộ danh sách tham số.

### 3.2. Normal canonical constructor

Record cũng có thể khai báo canonical constructor ở dạng đầy đủ. Khi đó, **chính constructor phải gán tất cả component field**:

```java
record Range(int min, int max) {
    Range(int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min must not exceed max");
        }

        this.min = min;
        this.max = max;
    }
}
```

Không được vừa khai báo compact canonical constructor vừa khai báo normal canonical constructor cho cùng record. Chỉ một canonical constructor xử lý việc khởi tạo từng instance.

### 3.3. Constructor bổ sung phải ủy quyền về canonical constructor

Một record được phép có constructor tiện ích, nhưng constructor đó phải gọi một constructor khác của cùng record thông qua `this(...)` để cuối cùng đi đến canonical constructor. Nhờ đó, đường khởi tạo thông thường vẫn áp dụng một nơi kiểm tra invariant.

```java
record PageSize(int value) {
    PageSize {
        if (value < 1 || value > 500) {
            throw new IllegalArgumentException("Page size must be 1..500");
        }
    }

    PageSize() {
        this(25);
    }
}
```

`new PageSize()` gọi `this(25)`, rồi `PageSize(int value)` được kiểm tra. Với record bất biến, cách này tránh tạo nhiều nhánh khởi tạo không nhất quán.

## 4. Bảo vệ `List` bằng `List.copyOf`

Nếu component là danh sách các giá trị **đã bất biến**, một snapshot không thể sửa thường đủ để bảo vệ record:

```java
import java.util.List;
import java.util.Objects;

record Course(String name, List<String> topics) {
    Course {
        name = Objects.requireNonNull(name, "name").strip();
        if (name.isEmpty()) {
            throw new IllegalArgumentException("Course name is required");
        }

        topics = List.copyOf(Objects.requireNonNull(topics, "topics"));
        if (topics.isEmpty()) {
            throw new IllegalArgumentException("At least one topic is required");
        }
        if (topics.stream().anyMatch(String::isBlank)) {
            throw new IllegalArgumentException("Topics must not be blank");
        }
    }
}
```

Tại thời điểm constructor kết thúc:

- Danh sách lưu trong `Course` không phản ánh các thao tác thêm, xóa hoặc thay phần tử trên danh sách nguồn.
- Accessor mặc định `topics()` có thể trả về list đó vì list là **unmodifiable**; gọi `add`, `remove`, `set` trên list này sẽ ném `UnsupportedOperationException`.
- `List.copyOf` từ chối tham số `null` và phần tử `null` bằng `NullPointerException`.
- `String` bất biến, nên việc chia sẻ các phần tử giữa list nguồn và snapshot không làm lộ trạng thái mutable của `Course`.

Ví dụ quan sát:

```java
import java.util.ArrayList;

List<String> input = new ArrayList<>(List.of("Records"));
Course course = new Course(" Java 27 ", input);

input.add("Sealed types");
System.out.println(course.name());   // Java 27
System.out.println(course.topics()); // [Records]

// Ném UnsupportedOperationException:
// course.topics().add("Unexpected topic");
```

**Không cần sao chép lại ở accessor** khi đã lưu một list unmodifiable chỉ chứa những phần tử thực sự bất biến; trả về cùng snapshot là đủ. Tự tạo một bản copy trên mỗi lần gọi chỉ tăng chi phí nếu không làm tăng độ an toàn.

### 4.1. Copy trước, kiểm tra trên bản copy

Một thói quen tốt là tạo snapshot trước rồi kiểm tra chính snapshot đó:

```java
topics = List.copyOf(Objects.requireNonNull(topics));
if (topics.size() > 100) {
    throw new IllegalArgumentException("Too many topics");
}
```

Nếu validate một collection mutable đầu vào rồi mới sao chép, dữ liệu có thể bị bên khác sửa giữa hai thao tác. Snapshot trước giúp giữ phép kiểm tra nhất quán với dữ liệu dự định lưu. **Tuy nhiên, `List.copyOf` không làm an toàn việc đọc nguồn đang bị thread khác sửa đồng thời**: người gọi vẫn phải bảo đảm không có ghi đồng thời không được đồng bộ trong quá trình sao chép, hoặc dùng một cơ chế snapshot có đồng bộ phù hợp.

### 4.2. `Set.copyOf` và `Map.copyOf`

Các factory của JDK cũng giúp tạo những collection không thể sửa:

```java
import java.util.Map;
import java.util.Set;

record AccessRules(Set<String> roles, Map<String, Integer> limits) {
    AccessRules {
        roles = Set.copyOf(roles);
        limits = Map.copyOf(limits);

        if (roles.isEmpty()) {
            throw new IllegalArgumentException("At least one role is required");
        }
        if (limits.values().stream().anyMatch(limit -> limit < 0)) {
            throw new IllegalArgumentException("Limits must be non-negative");
        }
    }
}
```

`Set.copyOf` và `Map.copyOf` từ chối collection/map null, phần tử null, key null hoặc value null theo từng API. `Map.copyOf` không bảo đảm thứ tự duyệt theo thứ tự nguồn. Nếu thứ tự là một phần của hợp đồng nghiệp vụ, hãy chọn cấu trúc và chiến lược snapshot bảo toàn thứ tự thay vì giả định `Map.copyOf` giữ nguyên.

Nếu cần giữ cả giá trị null như một trạng thái nghiệp vụ, `List.copyOf`/`Map.copyOf` không phù hợp trực tiếp; hãy mô hình hóa trạng thái đó rõ ràng, ví dụ bằng một kiểu kết quả có tên hoặc cấu trúc được thiết kế chuyên biệt. Không âm thầm biến null thành giá trị mặc định nếu điều đó làm đổi ý nghĩa dữ liệu.

## 5. Unmodifiable collection chưa chắc là immutable

`List.copyOf` tạo snapshot **cấu trúc danh sách**, nhưng **không sao chép sâu từng phần tử**. Nếu danh sách chứa đối tượng mutable, trạng thái của record vẫn có thể thay đổi thông qua chính đối tượng phần tử đó.

```java
import java.util.ArrayList;
import java.util.List;

record UnsafeLabels(List<StringBuilder> labels) {
    UnsafeLabels {
        labels = List.copyOf(labels);
    }
}

StringBuilder mutableLabel = new StringBuilder("Before");
var source = new ArrayList<StringBuilder>();
source.add(mutableLabel);

UnsafeLabels labels = new UnsafeLabels(source);
mutableLabel.append(" - After");

System.out.println(labels.labels().get(0)); // Before - After
```

Danh sách trong `UnsafeLabels` không thêm/xóa được, nhưng phần tử `StringBuilder` có thể bị sửa. Vì thế, gọi record là “bất biến sâu” là sai.

### 5.1. Chuyển phần tử mutable thành giá trị bất biến

Nếu nghiệp vụ chỉ cần văn bản, một lựa chọn tốt là chuyển `StringBuilder` thành `String` trước khi lưu:

```java
import java.util.List;
import java.util.Objects;

record Labels(List<String> values) {
    Labels {
        values = List.copyOf(values);
    }

    static Labels fromBuilders(List<StringBuilder> builders) {
        Objects.requireNonNull(builders, "builders");

        List<String> snapshot = builders.stream()
            .map(builder -> Objects.requireNonNull(builder, "label").toString())
            .toList();

        return new Labels(snapshot);
    }
}
```

Đối với object domain mutable, có thể chuyển mỗi phần tử thành một record/giá trị immutable độc lập hoặc copy dữ liệu cần thiết:

```java
record ImmutableItem(String sku, int quantity) {
    ImmutableItem {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU is required");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
    }
}
```

Nếu `ImmutableItem` chỉ chứa các thành phần bất biến thì `List<ImmutableItem>` được bảo vệ bởi `List.copyOf` sẽ là một mô hình giá trị ổn định. Không có một API deep-copy tổng quát nào của Java tự bảo đảm đúng mọi cấu trúc đối tượng tùy ý; chính mô hình domain phải quyết định thế nào là một bản sao độc lập.

### 5.2. Snapshot cho cấu trúc lồng nhau

`Map.copyOf` ở lớp ngoài cũng chưa đủ với `Map<String, List<String>>` nếu các list bên trong còn mutable:

```java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

record FeatureMatrix(Map<String, List<String>> permissions) {
    FeatureMatrix {
        Objects.requireNonNull(permissions, "permissions");

        Map<String, List<String>> snapshot = new HashMap<>();
        for (var entry : permissions.entrySet()) {
            String role = Objects.requireNonNull(entry.getKey(), "role");
            if (role.isBlank()) {
                throw new IllegalArgumentException("Role must not be blank");
            }

            List<String> rights = List.copyOf(
                Objects.requireNonNull(entry.getValue(), "rights")
            );
            if (rights.isEmpty() || rights.stream().anyMatch(String::isBlank)) {
                throw new IllegalArgumentException("Invalid rights for " + role);
            }
            snapshot.put(role, rights);
        }

        permissions = Map.copyOf(snapshot);
    }
}
```

Ở đây, cả `Map` ngoài và từng `List` bên trong đều được snapshot thành collection không thể sửa; key và các phần tử đều là `String` bất biến. Điều này đủ cho mô hình trên, dù về kỹ thuật vẫn là các bản sao theo từng tầng cấu trúc. Nếu thay `String` bằng một object mutable, phải xử lý thêm ở tầng phần tử.

## 6. Mảng: sao chép hai chiều và vấn đề equality

Mảng là đối tượng có phần tử thay đổi được. Record chứa mảng cần đặc biệt cẩn trọng vì **accessor mặc định trả về mảng gốc** và **`equals` mặc định so sánh tham chiếu của mảng** (không so sánh từng phần tử).

Ví dụ dễ mắc lỗi:

```java
record UnsafeSamples(int[] values) { }

int[] input = {1, 2, 3};
UnsafeSamples samples = new UnsafeSamples(input);
input[0] = 99;

System.out.println(samples.values()[0]); // 99
```

Kể cả khi chỉ sao chép tại constructor, accessor vẫn có thể làm lộ mảng nội bộ:

```java
record HalfProtected(int[] values) {
    HalfProtected {
        values = values.clone();
    }
}

HalfProtected data = new HalfProtected(new int[] {1, 2, 3});
data.values()[0] = 99; // Vẫn sửa được mảng nội bộ!
```

### 6.1. Bảo vệ mảng ở đầu vào và đầu ra

Một kiểu giữ `int[]` có thể clone khi nhận và khi trả ra:

```java
import java.util.Arrays;
import java.util.Objects;

record Samples(int[] values) {
    Samples {
        values = Objects.requireNonNull(values, "values").clone();
        if (values.length == 0) {
            throw new IllegalArgumentException("Samples must not be empty");
        }
    }

    public int[] values() {
        return values.clone();
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof Samples that
            && Arrays.equals(values, that.values);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(values);
    }

    @Override
    public String toString() {
        return "Samples" + Arrays.toString(values);
    }
}
```

Có **ba lựa chọn chủ đích** trong ví dụ:

1. Compact constructor clone mảng trước khi kiểm tra; dữ liệu lưu trong record không alias với mảng nguồn.
2. Accessor `values()` trả clone; người gọi không thể lấy mảng nội bộ rồi sửa trực tiếp.
3. `equals`/`hashCode` được định nghĩa theo **nội dung** mảng để mô hình có ngữ nghĩa giá trị nhất quán. `toString` cũng được điều chỉnh để hiển thị nội dung.

```java
int[] input = {1, 2, 3};
Samples first = new Samples(input);

input[0] = 99;
first.values()[1] = 88;

System.out.println(Arrays.toString(first.values())); // [1, 2, 3]
System.out.println(first.equals(new Samples(new int[] {1, 2, 3}))); // true
```

### 6.2. Vì sao chỉ clone mảng có thể phá hợp đồng record?

Với record có component là array, `equals` mặc định của record so sánh array bằng `Objects.equals`-like semantics, tức **danh tính mảng**, không phải `Arrays.equals`. Hai mảng khác nhau có nội dung bằng nhau vẫn không được xem là cùng component theo `equals` mặc định.

```java
record RawSamples(int[] values) { }

RawSamples a = new RawSamples(new int[] {1, 2});
RawSamples b = new RawSamples(new int[] {1, 2});

System.out.println(a.equals(b)); // false: hai mảng khác tham chiếu
System.out.println(Arrays.equals(a.values(), b.values())); // true
```

Tài liệu `java.lang.Record` quy định **copy invariant**: với `r` của record `R`, việc tạo `new R(r.c1(), r.c2(), ...)` từ các accessor phải cho giá trị bằng `r` theo `equals`. Nếu accessor trả clone mảng và constructor cũng clone mảng nhưng giữ `equals` mặc định, bản sao sẽ chứa một array object khác nên `r.equals(copy)` thành `false`. Đó là lý do cần **customize `equals`/`hashCode` nhất quán** nếu vẫn chọn array component và muốn phòng vệ hai chiều.

Với dữ liệu có thể dùng `List<Integer>`, chuyển sang unmodifiable list có thể đơn giản hóa việc bảo vệ và so sánh theo giá trị, đổi lại chi phí boxing và bộ nhớ. Với dữ liệu nhị phân lớn, `byte[]` cộng defensive copy và custom equality có thể hợp lý; lựa chọn phụ thuộc yêu cầu API và hiệu năng thực tế.

> Lưu ý: `values.clone()` chỉ đủ sâu cho mảng nguyên thủy một chiều như `int[]`. Với `Widget[]`, clone tạo array mới nhưng vẫn chia sẻ các `Widget` có thể mutable. Với mảng nhiều chiều, phải xử lý từng mảng con hoặc chuyển sang cấu trúc giá trị phù hợp.

## 7. Bảo vệ invariant khi component thay đổi theo thời gian

Một record có thể hợp lệ lúc tạo nhưng **trở nên không hợp lệ** nếu cấu trúc con được phép thay đổi.

```java
record UnsafeCart(List<String> items) {
    UnsafeCart {
        if (items == null || items.isEmpty()) {
            throw new IllegalArgumentException("Cart must have items");
        }
    }
}

List<String> items = new java.util.ArrayList<>(List.of("Book"));
UnsafeCart cart = new UnsafeCart(items);
items.clear();

System.out.println(cart.items().isEmpty()); // true: invariant đã bị phá!
```

Constructor đã kiểm tra `!items.isEmpty()` nhưng **không tạo snapshot**, vì vậy tác động từ bên ngoài phá vỡ điều kiện sau khi khởi tạo.

Giải pháp là kiểm tra trên dữ liệu sẽ được giữ trong record:

```java
record Cart(List<String> items) {
    Cart {
        items = List.copyOf(items);
        if (items.isEmpty()) {
            throw new IllegalArgumentException("Cart must have items");
        }
    }
}
```

Khi component là list chỉ chứa `String`, invariant không rỗng được duy trì sau khi tạo. Còn nếu list chứa `MutableProduct`, bảo vệ cấu trúc list vẫn chưa bảo vệ invariant của từng product. Phải bảo đảm cả object phần tử và các quan hệ liên quan đều giữ trạng thái hợp lệ.

### 7.1. Invariant có liên quan nhiều component

Đôi khi từng component riêng lẻ hợp lệ nhưng tổ hợp của chúng không hợp lệ:

```java
record PriceRange(int min, int max, int defaultPrice) {
    PriceRange {
        if (min < 0 || max < min) {
            throw new IllegalArgumentException("Invalid price range");
        }
        if (defaultPrice < min || defaultPrice > max) {
            throw new IllegalArgumentException("Default price out of range");
        }
    }
}
```

Mọi giá trị cần dùng để kiểm tra đã là primitive bất biến; constructor duy nhất đủ để giữ quan hệ giữa các component. Với component mutable, phải snapshot trước rồi xác thực **tổ hợp trên snapshot**, không chỉ xác thực từng input nguyên bản.

### 7.2. Không dùng getter để trả trạng thái mutable riêng

Một accessor được viết thủ công cần tuân theo cùng hợp đồng quan sát như constructor. Ví dụ, đừng clone array trong constructor rồi lại trả trực tiếp field ở accessor. Cũng đừng trả một `Collection.unmodifiableList` view của list mutable nội bộ nếu có nơi khác vẫn giữ khả năng sửa list nền.

Nếu cần làm việc với một tập giá trị mới, nên tạo record mới thay vì sửa bên trong:

```java
record Tags(List<String> values) {
    Tags {
        values = List.copyOf(values);
    }

    Tags withAdded(String tag) {
        Objects.requireNonNull(tag, "tag");
        var next = new java.util.ArrayList<>(values);
        next.add(tag);
        return new Tags(next);
    }
}
```

Phương thức `withAdded` giữ instance cũ không đổi và trả instance mới đã đi qua cùng invariant constructor. Đây là cách thiết kế phù hợp với value object, miễn là kích thước dữ liệu và tần suất cập nhật cho phép sao chép.

## 8. Đưa invariant vào từng biến thể của sealed hierarchy

`sealed interface` hoặc `sealed class` giới hạn các kiểu được phép kế thừa/triển khai trực tiếp. Nó **không tự bảo đảm bất biến dữ liệu**. Khi các biến thể là record, mỗi record cần xác thực các component của chính nó.

Giả sử hệ thống xử lý một kết quả đặt hàng có đúng hai biến thể: thành công và thất bại.

```java
import java.util.List;
import java.util.Objects;

sealed interface CheckoutResult permits Accepted, Rejected { }

record Accepted(String orderId, List<String> itemIds) implements CheckoutResult {
    Accepted {
        orderId = Objects.requireNonNull(orderId, "orderId").strip();
        if (orderId.isEmpty()) {
            throw new IllegalArgumentException("orderId must not be blank");
        }

        itemIds = List.copyOf(Objects.requireNonNull(itemIds, "itemIds"));
        if (itemIds.isEmpty() || itemIds.stream().anyMatch(String::isBlank)) {
            throw new IllegalArgumentException("Invalid itemIds");
        }
    }
}

record Rejected(String reason) implements CheckoutResult {
    Rejected {
        reason = Objects.requireNonNull(reason, "reason").strip();
        if (reason.isEmpty()) {
            throw new IllegalArgumentException("reason must not be blank");
        }
    }
}

class CheckoutPrinter {
    static String describe(CheckoutResult result) {
        return switch (result) {
            case Accepted a -> "Accepted " + a.orderId()
                + " with " + a.itemIds().size() + " items";
            case Rejected r -> "Rejected: " + r.reason();
        };
    }
}
```

Trong mô hình này:

- `CheckoutResult` giới hạn các biến thể trực tiếp đã biết (`Accepted` và `Rejected`). Hai record là `final` ngầm định, nên không mở thêm nhánh kế thừa bên dưới chúng.
- `Accepted` tự kiểm tra mã đơn hàng và snapshot danh sách item ID; `Rejected` tự kiểm tra lý do từ chối.
- `switch` trên sealed type có thể được compiler kiểm tra tính đầy đủ của các nhánh khi không có subclass tùy ý mở rộng.
- `switch (result)` với `result == null` không được xử lý bởi hai case ở trên; nó ném `NullPointerException` theo ngữ nghĩa switch hiện hành. Nếu null hợp lệ, cần thiết kế case null hoặc xác thực trước.

**Giới hạn kiểu (sealed)** và **giới hạn trạng thái (invariant + defensive copy)** là hai tầng bảo vệ độc lập. Sealed không khiến component tự động immutable, và record không khiến một hierarchy tự động sealed.

### 8.1. Không áp đặt invariant sai vào superclass hoặc interface

Invariant chung thật sự thuộc về contract chung của hierarchy; invariant riêng nên nằm ở biến thể. Ví dụ `Accepted` bắt buộc có ít nhất một item nhưng `Rejected` không có danh sách item. Không nên ép cả hai biến thể phải mang cùng dữ liệu chỉ để dùng một record chung với các field nullable không liên quan.

Nếu sau này thêm một biến thể mới vào sealed hierarchy, phải xác thực invariant của biến thể đó và xử lý các biểu thức `switch` bị ảnh hưởng. Đây là lợi ích của việc mô hình hóa trạng thái rõ ràng ngay từ đầu.

## 9. `equals`, `hashCode` và trạng thái mutable

`equals`, `hashCode`, `toString` do compiler sinh cho record dựa vào các component. Nếu một component được trỏ tới là object mutable, hành vi quan sát của các phương thức đó **có thể thay đổi theo thời gian**.

```java
import java.util.ArrayList;
import java.util.List;

record UnsafeKey(List<String> parts) { }

List<String> source = new ArrayList<>(List.of("A"));
UnsafeKey key = new UnsafeKey(source);

int oldHash = key.hashCode();
source.add("B");
int newHash = key.hashCode();

System.out.println(oldHash == newHash); // Không nên dựa vào điều này
```

Nếu dùng `UnsafeKey` làm key trong `HashMap` rồi sửa list phía sau, việc tra cứu có thể sai vì mã hash của key đã thay đổi sau khi đưa vào map. Một object được dùng làm hash key cần có equality/hash ổn định trong thời gian nó nằm trong cấu trúc dữ liệu.

```java
record StableKey(List<String> parts) {
    StableKey {
        parts = List.copyOf(parts);
    }
}
```

Với `List<String>` bất biến về cấu trúc và phần tử, `StableKey` có ngữ nghĩa equality ổn định. Nếu component chứa object mutable với `equals`/`hashCode` phụ thuộc trạng thái, `List.copyOf` một mình vẫn chưa đủ.

### 9.1. Tránh sửa `equals` mà quên `hashCode`

Khi thiết kế custom equality (chẳng hạn record chứa array), phải tùy chỉnh cả `hashCode` cho nhất quán: hai object `equals == true` **phải** có cùng hash code. Đồng thời, record phải giữ hợp đồng copy invariant trong Java API: bản sao tạo từ các accessor và canonical constructor phải `equals` với bản gốc.

Nếu yêu cầu equality khác nhau quá xa ý nghĩa "giá trị được định nghĩa bằng record components", cân nhắc dùng một class thường với API chủ động thiết kế thay vì ép record làm một mô hình không còn minh bạch.

## 10. Kiểm thử invariant và defensive copy

Không đủ để kiểm tra rằng constructor từ chối vài giá trị sai. Cần kiểm thử **trước, trong và sau** thời điểm tạo object, đặc biệt khi đầu vào chứa mutable component.

### 10.1. Bảng ca kiểm thử đề xuất

| Nhóm | Ca kiểm thử | Kỳ vọng |
| --- | --- | --- |
| Dữ liệu hợp lệ | Record nhận component đúng miền | Instance được tạo; giá trị đọc ra đúng |
| Null | Truyền null vào component bắt buộc | NPE có thông điệp rõ ràng nếu dùng `requireNonNull` |
| Miền số | Truyền số âm, ranh giới min/max | Giá trị ngoài miền bị từ chối |
| Quan hệ chéo | `start >= end`, `min > max` | Constructor từ chối |
| Chuẩn hóa | Chuỗi có khoảng trắng ngoài | Record lưu dạng đã chuẩn hóa |
| Sửa nguồn | Sửa list/array sau khi tạo | Record không thay đổi |
| Sửa kết quả accessor | Thử `add`, `set` hoặc sửa array trả ra | Không thay đổi trạng thái nội bộ |
| Cấu trúc sâu | Sửa object phần tử bên ngoài | Không lộ thay đổi nếu contract yêu cầu immutable sâu |
| Equality | Tạo bản sao từ accessor | `equals` và `hashCode` đúng hợp đồng |
| Hash key | Dùng làm key trong map rồi tác động đến input nguồn | Tra cứu vẫn ổn định |

### 10.2. Ví dụ tự kiểm tra không cần thư viện ngoài

```java
import java.util.ArrayList;
import java.util.List;

public class RecordSafetyDemo {
    record SafeCart(List<String> products) {
        SafeCart {
            products = List.copyOf(products);
            if (products.isEmpty()) {
                throw new IllegalArgumentException("Cart must not be empty");
            }
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>(List.of("Book"));
        SafeCart first = new SafeCart(input);

        input.add("Pen");
        if (!first.products().equals(List.of("Book"))) {
            throw new AssertionError("Input alias leaked");
        }

        try {
            first.products().add("Bag");
            throw new AssertionError("Accessor must not expose mutable list");
        } catch (UnsupportedOperationException expected) {
            // Danh sách không thể sửa: đúng thiết kế.
        }

        SafeCart reconstructed = new SafeCart(first.products());
        if (!first.equals(reconstructed)
                || first.hashCode() != reconstructed.hashCode()) {
            throw new AssertionError("Record copy invariant violated");
        }

        try {
            new SafeCart(List.of());
            throw new AssertionError("Empty cart must be rejected");
        } catch (IllegalArgumentException expected) {
            // Invariant được áp dụng.
        }

        System.out.println("All checks passed");
    }
}
```

Đoạn minh họa này kiểm tra snapshot, accessor không thể sửa, invariant danh sách không rỗng và equality sau khi dựng lại record. Trong dự án thực tế, nên chuyển chúng thành test có tên, dữ liệu biên và kiểm tra hành vi cho tất cả biến thể sealed.

## 11. Giới hạn quan trọng của việc bảo vệ bằng record

### 11.1. Không có "deep immutable" tự động

Một component có thể là list không thể sửa nhưng chứa những object mutable, map của list, array nhiều chiều hoặc object có API ghi trạng thái. Muốn bảo đảm bất biến sâu, mọi đường dẫn có thể sửa dữ liệu cần được giải quyết bởi thiết kế immutable hoặc sao chép độc lập phù hợp.

### 11.2. Snapshot không thay cho đồng bộ đa luồng

Sao chép từ một cấu trúc được thread khác sửa đồng thời có thể gặp dữ liệu không nhất quán hoặc lỗi tại thời điểm copy. Record không tự mang thread safety cho toàn bộ quá trình thu thập dữ liệu; người gọi phải cung cấp dữ liệu ổn định khi tạo, hoặc phải dùng một giao thức đồng bộ/snapshot riêng.

### 11.3. Phòng vệ có chi phí

Copy collection/mảng là công việc tỷ lệ với lượng dữ liệu được sao chép. Trả clone mảng trên mỗi accessor có thể tốn bộ nhớ và CPU nếu gọi nhiều lần. Khi tải lớn, hãy đo trên workload thật, lựa chọn value object có cấu trúc phù hợp hoặc thiết kế API đọc dữ liệu theo cách không làm lộ mutable reference. Không nên bỏ defensive copy để tối ưu trước khi đã xác định rõ hợp đồng sở hữu dữ liệu.

### 11.4. Không nhầm bất biến với xác thực bên ngoài

Record có thể đảm bảo các điều kiện nội tại khi tạo instance hợp lệ, nhưng điều kiện phụ thuộc hệ thống bên ngoài vẫn phải được kiểm tra tại ranh giới thích hợp. Ví dụ ID không rỗng là invariant nội tại; ID đã tồn tại trong cơ sở dữ liệu hay chưa là một vấn đề khác và có thể thay đổi theo thời gian.

## 12. Những lỗi thường gặp và cách khắc phục

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Cho rằng field `final` làm list bất biến | Mã gọi thêm/xóa phần tử qua tham chiếu | `List.copyOf`/`Map.copyOf` hoặc snapshot phù hợp |
| Chỉ validate list mà không copy | Đối tượng thay đổi thành trạng thái không hợp lệ sau construction | Copy trước rồi validate snapshot |
| Chỉ clone array trong constructor | Accessor mặc định trả lại array nội bộ | Override accessor để trả clone |
| Chỉ clone array trong accessor | Mã gọi vẫn sửa được array đầu vào đã lưu | Clone tại constructor và accessor |
| Clone array hai chiều nhưng dùng default `equals` | Không giữ copy invariant theo giá trị | Custom `equals`/`hashCode` hoặc dùng kiểu collection phù hợp |
| `List.copyOf` cho list chứa mutable element | Các element vẫn có thể thay đổi | Chuyển sang immutable element hoặc copy từng element |
| `Map.copyOf` cho map chứa list mutable | Thay đổi list lồng bên trong còn được quan sát | Snapshot từng tầng chứa mutable reference |
| Dùng `Collections.unmodifiableList` trên list đang chia sẻ | View vẫn thấy thay đổi ở collection nền | Tạo bản sao độc lập, sau đó bọc hoặc `List.copyOf` |
| Viết `this.component = ...` trong compact constructor | Lỗi biên dịch | Gán lại tham số component; để compiler tự gán field |
| Tùy chỉnh `equals` mà không tùy chỉnh `hashCode` | Vi phạm hợp đồng equality/hash | Cập nhật đồng bộ hai phương thức |
| Dùng record có hash biến đổi làm key của `HashMap` | Tra cứu không ổn định | Đảm bảo toàn bộ component tham gia equality/hash bất biến |
| Nghĩ sealed interface làm các record con immutable | Các component mutable vẫn có thể lộ trạng thái | Xác thực và defensive copy ở từng biến thể |

## 13. Checklist thiết kế record an toàn

Trước khi công khai một record trong API, nên trả lời các câu hỏi sau:

1. Invariant của record là gì? Ràng buộc của từng component và quan hệ giữa chúng đã được diễn đạt rõ chưa?
2. Mọi đường khởi tạo có đi qua canonical constructor đã kiểm tra dữ liệu không?
3. Có component nào tham chiếu đến object mutable không? Nếu có, đã chặn alias từ đầu vào chưa?
4. Accessor có trả reference có thể sửa trạng thái nội bộ không?
5. Nếu component là collection, các **phần tử** bên trong có bất biến không?
6. Nếu component là array, `equals`/`hashCode`/`toString` có đúng ngữ nghĩa dữ liệu và record copy invariant không?
7. Khi snapshot collection lồng nhau, đã snapshot đầy đủ những tầng mutable cần bảo vệ chưa?
8. Code có phụ thuộc vào thứ tự của `Map.copyOf` hoặc cho phép null trái quy tắc API không?
9. Mọi invariant có còn đúng sau khi caller sửa dữ liệu nguồn hoặc cố sửa dữ liệu từ accessor không?
10. Nếu record là biến thể của sealed hierarchy, invariant có đúng cho từng biến thể và switch có xử lý đủ trạng thái hợp lệ không?

**Nguyên tắc cốt lõi:** *Validate the snapshot you store, and never expose mutable state that can break the invariant.* Record giúp khai báo mô hình dữ liệu ngắn gọn, nhưng trách nhiệm bảo vệ sự nhất quán của dữ liệu vẫn thuộc về thiết kế API.

## Tài liệu tham khảo chính thức

- [Java SE 27 API — java.lang.Record](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Record.html): record shallow immutability, canonical constructor, equality và copy invariant.
- [Java Language Specification 27 — §8.10 Record Classes](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.10): thành phần, thành viên, constructor của record.
- [Java Language Specification 27 — §8.10.4.2 Compact Canonical Constructors](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.10.4.2): tham số ngầm định, chuẩn hóa và gán field sau constructor.
- [Java SE 27 API — List.copyOf](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): snapshot list không thể sửa, quy tắc null và shallow elements.
- [Java SE 27 API — Map.copyOf](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): snapshot map, quy tắc null và iteration order.
- [Java SE 27 API — Set.copyOf](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)): snapshot set, quy tắc phần tử null và trùng lặp.
- [Java SE 27 API — Arrays](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Arrays.html): so sánh, hash và thao tác với array.
- [Java Language Specification 27 — sealed và permitted direct subclasses](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.1.6): giới hạn các biến thể kế thừa trực tiếp.
