# Giữ ổn định `equals`, `hashCode`, comparator và định dạng biểu diễn

Trong tiến hóa API Java, một thư viện có thể giữ nguyên tất cả class, method và chữ ký public nhưng vẫn làm ứng dụng sử dụng thư viện hoạt động khác trước. Những thay đổi tưởng nhỏ trong `equals(Object)`, `hashCode()`, `Comparator`, `Comparable.compareTo` hoặc cách tạo chuỗi biểu diễn có thể phá vỡ hợp đồng nghiệp vụ, cấu trúc dữ liệu, cache, thứ tự bản ghi, chữ ký số hoặc giao thức trao đổi dữ liệu.

Ví dụ: một bản nâng cấp bổ sung trường `displayName` cho đối tượng khách hàng. Nếu tự động đưa trường đó vào `equals` và `hashCode`, hai khách hàng có cùng mã định danh nhưng khác cách viết tên bỗng trở thành hai khóa khác nhau. Nếu đổi comparator từ thứ tự theo mã sang thứ tự theo tên, một `TreeSet` trước đây loại các bản ghi trùng mã có thể giữ hoặc loại tập bản ghi khác. Nếu thay đổi `toString()` vốn đang bị client dùng làm định dạng CSV, dữ liệu mới có thể không còn được hệ thống cũ phân tích chính xác.

Đây chủ yếu là **rủi ro tương thích hành vi**. Các method có thể vẫn được JVM liên kết thành công, source vẫn compile, nhưng ý nghĩa của so sánh, hash, sắp xếp và biểu diễn đã thay đổi. Để tiến hóa API an toàn, cần xem các hành vi này như một phần hợp đồng mà consumer có thể phụ thuộc, thay vì chi tiết triển khai tùy ý.

## 1. Bốn hợp đồng thường bị bỏ sót khi nâng phiên bản

| Hợp đồng | Ứng dụng sử dụng ở đâu? | Điều gì có thể hỏng khi thay đổi? |
|---|---|---|
| `equals` | Kiểm tra trùng lặp, tập hợp, so sánh giá trị, logic nghiệp vụ | Hai đối tượng trước đây được coi là một nay thành hai, hoặc ngược lại |
| `hashCode` | `HashMap`, `HashSet`, các bảng hash và cache dùng object làm khóa | Tìm kiếm khóa thất bại, trùng lặp bất ngờ, phân phối hash thay đổi |
| `Comparator` / `compareTo` | `TreeMap`, `TreeSet`, sort, phân trang, ưu tiên, tìm kiếm nhị phân | Thứ tự và cách nhóm phần tử thay đổi; `compare(a,b)==0` có thể làm mất key |
| Định dạng biểu diễn | `toString`, CSV, JSON, log, audit, cache key, wire protocol | Parser cũ không đọc được, chuỗi bị hiểu sai hoặc dữ liệu không còn ổn định |

Điểm chung là các hợp đồng này thường không xuất hiện rõ trong ABI của thư viện. Công cụ so sánh binary API có thể kết luận các method public vẫn tồn tại, nhưng không thể chứng minh kết quả mà chúng trả về còn có cùng ý nghĩa.

### 1.1. Phân biệt ba lớp tương thích

- **Tương thích nhị phân:** bytecode consumer cũ có thể liên kết với thư viện mới mà không gặp các lỗi như `NoSuchMethodError` hoặc `IllegalAccessError`.
- **Tương thích mã nguồn:** mã nguồn consumer cũ vẫn biên dịch khi dùng thư viện mới.
- **Tương thích hành vi:** những giả định mà consumer đã dựa vào vẫn đúng, như “hai khóa cùng định danh thì bằng nhau” hoặc “dữ liệu được sắp theo mã tăng dần”.

Thay đổi body của `equals` trong một class có thể không thay đổi public method descriptor nào. Vì thế, **binary compatibility không kéo theo behavioral compatibility**.

## 2. Hợp đồng của `equals(Object)`

`equals` định nghĩa quan hệ tương đương theo ngữ nghĩa của một đối tượng. `Object.equals` mặc định dựa trên danh tính object; các value object thường override để so sánh theo dữ liệu hoặc khóa nghiệp vụ.

Java quy định quan hệ `equals` trên các tham chiếu khác `null` phải có các tính chất cơ bản:

1. **Phản xạ (reflexive):** với tham chiếu `x` khác `null`, `x.equals(x)` là `true`.
2. **Đối xứng (symmetric):** `x.equals(y)` và `y.equals(x)` phải cùng kết quả.
3. **Bắc cầu (transitive):** nếu `x.equals(y)` và `y.equals(z)` đúng thì `x.equals(z)` cũng đúng.
4. **Nhất quán (consistent):** nhiều lần gọi cho cùng hai đối tượng phải cho cùng kết quả nếu thông tin dùng trong phép so sánh không thay đổi.
5. **Không bằng null:** `x.equals(null)` phải là `false`.

Đây là hợp đồng Java cơ bản. Khi nâng phiên bản thư viện, còn có **hợp đồng ứng dụng**: thuộc tính nào xác định hai đối tượng là cùng một thực thể hoặc cùng một giá trị?

### 2.1. Quyết định “bằng nhau” dựa trên ý nghĩa, không dựa vào số field

Xét một value object định danh sản phẩm:

```java
import java.util.Objects;

public final class ProductKey {
    private final String tenantId;
    private final String productId;

    public ProductKey(String tenantId, String productId) {
        this.tenantId = Objects.requireNonNull(tenantId);
        this.productId = Objects.requireNonNull(productId);
    }

    public String tenantId() {
        return tenantId;
    }

    public String productId() {
        return productId;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof ProductKey)) return false;
        ProductKey that = (ProductKey) other;
        return tenantId.equals(that.tenantId)
                && productId.equals(that.productId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, productId);
    }
}
```

Ở đây danh tính theo hợp đồng là cặp `(tenantId, productId)`. Hai key có cùng cặp này được xem là tương đương, bất kể đối tượng được tạo ở đâu.

Giả sử phiên bản sau bổ sung `displayName` nhằm hiển thị:

```java
private final String displayName;
```

Nếu `displayName` chỉ là thông tin trình bày, đưa nó vào `equals` sẽ thay đổi định nghĩa danh tính. Một key trước đây khớp với bản ghi trong cache có thể bỗng không khớp chỉ vì tên hiển thị thay đổi.

Nên viết rõ trong API documentation: “Hai `ProductKey` bằng nhau khi cùng `tenantId` và `productId`; tên hiển thị không tham gia định danh.” Quyết định này phải được duy trì qua các bản phát hành trừ khi dự án chủ đích thực hiện breaking behavioral change.

### 2.2. Giá trị và thực thể không nhất thiết có cùng ngữ nghĩa bằng nhau

Với **value object**, `equals` thường dựa trên toàn bộ thành phần cấu thành giá trị: hai tọa độ hoặc hai khoản tiền có cùng thuộc tính chuẩn hóa được xem là bằng nhau.

Với **entity**, hợp đồng có thể dựa trên định danh ổn định. Tuy nhiên, entity chưa được cấp ID, entity từ ORM proxy, ID do database sinh và các giai đoạn trước/sau lưu trữ đều cần một thiết kế riêng. Không nên áp dụng máy móc “mọi entity bằng nhau nếu cùng ID” khi ID có thể là `null` hoặc được cấp sau khi object đã làm key trong collection.

Điểm cần giữ ổn định là **ý nghĩa được công bố** của phép so sánh, không phải một công thức duy nhất cho mọi loại object.

### 2.3. Mở rộng class và quy tắc đối xứng

Một base class có `equals` so sánh bằng `instanceof`, rồi một subclass bổ sung field mới vào phép so sánh, rất dễ làm mất tính đối xứng.

Ví dụ khái niệm:

```java
class Point {
    final int x;
    final int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    @Override
    public boolean equals(Object other) {
        if (!(other instanceof Point)) return false;
        Point p = (Point) other;
        return x == p.x && y == p.y;
    }
}

class ColoredPoint extends Point {
    final String color;

    ColoredPoint(int x, int y, String color) {
        super(x, y);
        this.color = color;
    }

    @Override
    public boolean equals(Object other) {
        if (!(other instanceof ColoredPoint)) return false;
        ColoredPoint p = (ColoredPoint) other;
        return super.equals(p) && color.equals(p.color);
    }
}
```

Với `Point(1,2)` và `ColoredPoint(1,2,"red")`, phép so sánh theo hai hướng có thể khác nhau. Đây là lỗi hợp đồng `equals`, không phải chỉ là vấn đề phong cách code.

Một số chiến lược thiết kế gồm: value object `final`; composition thay vì inheritance; quy tắc so sánh giới hạn chính xác runtime class; hoặc cơ chế tương thích kế thừa được định nghĩa rõ. Mỗi lựa chọn có đánh đổi khác nhau về khả năng mở rộng và tương thích; không nên đổi giữa các chiến lược mà không kiểm tra consumer.

### 2.4. `getClass()` và `instanceof` đều là quyết định hợp đồng

- `getClass() == other.getClass()` có thể giới hạn equality vào đúng runtime class. Điều này rõ ràng với một số value type, nhưng có thể không phù hợp với proxy/subclass.
- `instanceof` cho phép một số subclass tham gia equality, nhưng cần bảo vệ tính đối xứng và bắc cầu khi subclass thêm trạng thái.

Khi thư viện đang được nhiều consumer kế thừa, thay đổi từ `instanceof` sang `getClass()` có thể khiến hai object từng bằng nhau nay khác nhau mà không có lỗi compile. Cần xem hành vi đó là một thay đổi API ở cấp ngữ nghĩa.

## 3. `hashCode()` là phần bắt buộc đi cùng `equals`

Java quy định:

- Nếu `a.equals(b)` là `true`, `a.hashCode()` và `b.hashCode()` phải bằng nhau.
- Hai object không bằng nhau **được phép** có cùng mã hash (collision).
- Trong một lần thực thi, nhiều lời gọi `hashCode()` trên cùng object phải nhất quán nếu thông tin dùng trong phép tính không thay đổi.

Hợp đồng Java **không đòi hỏi** mỗi object có một giá trị hash không đổi mãi mãi giữa các tiến trình, JVM hoặc phiên bản ứng dụng. Nhưng nếu dự án tự dùng mã hash như dữ liệu persisted, shard key hoặc cache key ngoài tiến trình, dự án đã tạo thêm một hợp đồng riêng cần quản lý.

### 3.1. Vì sao phải thay `equals` và `hashCode` cùng nhau?

`HashMap` và `HashSet` dùng hash để chọn vùng tìm kiếm, rồi dùng equality để quyết định hai key có trùng nhau hay không. Nếu hai key bằng nhau nhưng có mã hash khác nhau, lookup và dedup có thể sai.

Ví dụ triển khai sai:

```java
import java.util.Objects;

final class UserKey {
    private final String id;

    UserKey(String id) {
        this.id = id;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof UserKey
                && Objects.equals(id, ((UserKey) other).id);
    }

    // Không override hashCode(): vi phạm hợp đồng.
}
```

Hai `UserKey("u-1")` có thể bằng nhau theo `equals` nhưng dùng `Object.hashCode` mặc định dựa trên đặc tính danh tính của từng object. `HashSet` không có cơ sở để xử lý chúng như cùng một khóa. Cần override cả hai method với cùng tiêu chí ngữ nghĩa.

### 3.2. Tránh dùng trạng thái thay đổi được làm hash key

Một lỗi phổ biến khác là đưa field mutable vào `equals` và `hashCode`:

```java
import java.util.Objects;

class MutableKey {
    String code;

    MutableKey(String code) {
        this.code = code;
    }

    @Override
    public boolean equals(Object o) {
        return o instanceof MutableKey
                && Objects.equals(code, ((MutableKey) o).code);
    }

    @Override
    public int hashCode() {
        return Objects.hashCode(code);
    }
}
```

Nếu key đang ở trong `HashMap` rồi `code` bị sửa, hash tính ra sau khi sửa có thể khác lúc chèn:

```java
import java.util.HashMap;
import java.util.Map;

Map<MutableKey, String> map = new HashMap<>();
MutableKey key = new MutableKey("A");
map.put(key, "value");

key.code = "B";

// Tìm bằng key đã đổi trạng thái có thể thất bại.
System.out.println(map.get(key));
```

Đối với object dùng làm key, ưu tiên immutable field tham gia equality/hash. Nếu bắt buộc thay định danh, hãy xóa key khỏi collection khi nó vẫn còn trạng thái cũ, tạo key mới và thêm lại. Không nên trông chờ `HashMap` tự theo dõi thay đổi bên trong key.

### 3.3. Một thay đổi hash hợp lệ theo Java vẫn có thể phá vỡ ứng dụng

Giả sử phiên bản 1 tính hash bằng `Objects.hash(tenantId, productId)`, phiên bản 2 thay thành thuật toán khác nhưng vẫn bảo đảm các key bằng nhau có hash giống nhau. Về hợp đồng cơ bản của Java, thay đổi này không nhất thiết sai.

Tuy nhiên, hệ thống có thể đã:

- Lưu nguyên `hashCode()` vào database làm “ID” của một record.
- Dùng nó để chọn partition trong một hệ thống phân tán.
- Dùng nó làm key của cache ngoài tiến trình.
- So sánh hash từ các phiên bản dịch vụ khác nhau.

Những cách dùng đó làm lộ thuật toán hash vốn nên là chi tiết triển khai. Khi đổi thuật toán, các record có thể bị phân phối lại hoặc không tìm thấy.

Với định danh cần tồn tại lâu dài, thiết kế một **stable key/canonical identifier riêng**, có version và quy tắc encoding rõ ràng. Không dùng `Object.hashCode()` như định danh bền vững.

### 3.4. Lưu ý với array và record

Array trong Java so sánh bằng danh tính nếu gọi `equals` kế thừa từ `Object`; `Objects.equals(array1,array2)` cũng không tự so sánh phần tử nếu hai array khác object. Với value object chứa array, nếu mong muốn so sánh theo nội dung, dùng `Arrays.equals` / `Arrays.hashCode` hoặc các biến thể `deepEquals` / `deepHashCode` khi đúng với mô hình dữ liệu.

Java `record` tự sinh `equals` và `hashCode` dựa trên record components. Nếu thêm một component vào record, hành vi equality/hash được sinh có thể thay đổi ngay cả khi các constructor hoặc API liên quan được điều chỉnh cho source compile được. Với component kiểu array, equality được sinh không tự hiểu rằng hai array khác instance nhưng cùng phần tử là bằng nhau. Đừng mặc định record giải quyết toàn bộ thiết kế semantic equality.

## 4. Hợp đồng của `Comparator` và `Comparable`

Java hỗ trợ hai cách định nghĩa thứ tự:

- `Comparable<T>`: thứ tự tự nhiên do chính class khai báo qua `compareTo`.
- `Comparator<T>`: một chiến lược so sánh bên ngoài class, cho phép nhiều thứ tự khác nhau cho cùng loại object.

Khi so sánh `a` và `b`, kết quả âm nghĩa là `a` đứng trước `b`, bằng không nghĩa là tương đương **theo comparator**, dương nghĩa là `a` đứng sau `b`. Không được giả định kết quả bắt buộc là -1, 0 hoặc 1; cần xét dấu của kết quả.

### 4.1. Những thuộc tính cần giữ

Một comparator đúng cần giữ các thuộc tính như:

1. **Đảo dấu khi đổi chỗ đối số:** dấu của `compare(a,b)` phải đối nghịch dấu `compare(b,a)`.
2. **Bắc cầu:** nếu `a > b` và `b > c` theo comparator, `a > c` cũng phải đúng.
3. **Nhất quán khi bằng theo comparator:** nếu `compare(a,b)==0` thì khi so với một `c` khác, dấu của `compare(a,c)` và `compare(b,c)` phải giống nhau.
4. **Tính xác định trong cùng điều kiện:** thứ tự không nên phụ thuộc vào trạng thái biến đổi bất ngờ trong quá trình sắp xếp hoặc lưu trong sorted collection.

Comparator không bắt buộc phải nhất quán với `equals` trong mọi mục đích sử dụng, nhưng **nhất quán với equals đặc biệt quan trọng khi dùng làm hợp đồng tập hợp/ánh xạ được sắp xếp**.

### 4.2. Tránh lỗi tràn số khi dùng phép trừ

Không nên viết:

```java
Comparator<Integer> bad = (a, b) -> a - b;
```

Nếu hiệu vượt phạm vi `int`, thứ tự có thể bị sai do overflow. Nên viết:

```java
Comparator<Integer> safe = Integer::compare;
```

Với đối tượng:

```java
import java.util.Comparator;

Comparator<Order> byPriority =
        Comparator.comparingInt(Order::getPriority);
```

Những helper như `comparingInt`, `comparingLong` và `thenComparing` giúp mô tả thứ tự rõ ràng hơn so với phép trừ thủ công.

### 4.3. Comparator bằng 0 không nhất thiết có nghĩa `equals` bằng nhau

Một ví dụ quan trọng:

```java
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

Set<String> hash = new HashSet<>();
Set<String> sorted = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);

hash.add("Java");
hash.add("java");

sorted.add("Java");
sorted.add("java");

System.out.println(hash.size());   // 2
System.out.println(sorted.size()); // 1
```

`String.equals` phân biệt chữ hoa/chữ thường, nhưng `String.CASE_INSENSITIVE_ORDER` coi hai chuỗi là tương đương theo comparator. `TreeSet` dựa trên comparator để quyết định hai phần tử có cùng vị trí khóa; vì thế nó có thể chỉ giữ một trong hai.

Đây không phải lỗi của `TreeSet`. Nó cho thấy **định nghĩa trùng lặp của sorted set được quyết định bởi comparator**.

Khi thay comparator trong một bản nâng cấp, hãy kiểm tra:

- Số phần tử trong `TreeSet` có thay đổi không?
- Những key nào trong `TreeMap` bị coi là trùng và có thể bị ghi đè?
- API tìm kiếm/sắp xếp có còn dùng cùng chuẩn so sánh?
- Dữ liệu đã được index hoặc phân trang có còn hợp lệ?

### 4.4. `BigDecimal.compareTo` và `equals` cho thấy sự khác biệt có chủ đích

`BigDecimal` là ví dụ kinh điển về một kiểu mà thứ tự tự nhiên **không nhất quán hoàn toàn** với `equals`.

```java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));         // false
```

Vì `equals` của `BigDecimal` còn xét đến scale, hai giá trị số bằng nhau có thể không bằng nhau theo object equality. Một `HashSet<BigDecimal>` và `TreeSet<BigDecimal>` có thể cho kết quả loại trùng khác nhau.

Trong API tài chính, phải quyết định rõ hợp đồng cần “giá trị số bằng nhau” hay “giá trị và scale bằng nhau”. Đừng âm thầm đổi từ `equals` sang `compareTo` chỉ để sửa một test nếu consumer khác đang dựa trên scale.

### 4.5. Tạo thứ tự nhất quán cho một value key

Với `ProductKey` ở trên, thứ tự theo cùng hai thành phần định danh có thể viết:

```java
import java.util.Comparator;

Comparator<ProductKey> BY_KEY =
        Comparator.comparing(ProductKey::tenantId)
                  .thenComparing(ProductKey::productId);
```

Vì cả equality và comparator đều dựa trên cùng cặp chuỗi theo ngữ nghĩa phân biệt chữ hoa/chữ thường, hai object có comparator result bằng 0 cũng bằng nhau theo `equals`.

Nếu sort theo `displayName` là nhu cầu giao diện, nên tạo comparator riêng tên rõ mục đích, ví dụ `BY_DISPLAY_NAME`. Đừng thay comparator định danh mà các `TreeMap`, `TreeSet` hoặc thuật toán phân trang đã dùng để biểu diễn khóa ổn định.

### 4.6. Sắp xếp ổn định không đồng nghĩa thứ tự luôn xác định

Một thuật toán sort *stable* giữ nguyên thứ tự tương đối của các phần tử mà comparator trả về 0. Nhưng nếu đầu vào đến từ `HashMap` hoặc truy vấn SQL không có thứ tự xác định, thứ tự của các phần tử hòa vẫn có thể khác giữa các lần chạy.

Với API trả danh sách có thứ tự có thể tái tạo, cần một **tie-breaker có tính xác định**:

```java
Comparator<Order> BY_CREATED_AT_AND_ID =
        Comparator.comparing(Order::getCreatedAt)
                  .thenComparing(Order::getId);
```

Nếu `createdAt` không duy nhất, `id` giúp cố định thứ tự giữa các bản ghi cùng thời điểm. Với phân trang bằng cursor hoặc offset, đổi thứ tự/tie-breaker giữa các phiên bản có thể gây lặp hoặc bỏ sót bản ghi. Cần coi sort order là một phần hợp đồng response.

### 4.7. `null`, locale, case và Unicode là quyết định cần cố định

Comparator có thể chấp nhận hoặc từ chối null; policy này cần nhất quán:

```java
Comparator<String> NULL_LAST =
        Comparator.nullsLast(Comparator.naturalOrder());
```

Nếu một bản nâng cấp đổi từ null-first sang null-last, dữ liệu phân trang hoặc kết quả ưu tiên có thể thay đổi mà code vẫn biên dịch.

So sánh chuỗi còn phụ thuộc vào mục tiêu:

- `String.compareTo` so sánh theo thứ tự lexicographic của chuỗi Java, không phải thứ tự chữ cái của một ngôn ngữ tự nhiên.
- `Collator` có thể dùng quy tắc ngôn ngữ/locale. Kết quả có thể chịu tác động của cấu hình locale, dữ liệu collation và phiên bản môi trường.
- Case folding, Unicode normalization và cách xử lý dấu có thể biến các chuỗi trước đây phân biệt thành tương đương, hoặc ngược lại.

Nếu thứ tự có giá trị nghiệp vụ hoặc cần ổn định giữa các dịch vụ, hãy chọn quy tắc chính thức, ghi rõ locale và phiên bản thuật toán khi phù hợp, rồi kiểm thử trên dữ liệu có dấu, chữ hoa/chữ thường và ký tự Unicode đặc biệt.

## 5. Định dạng biểu diễn: từ `toString` đến JSON, CSV và cache key

Một đối tượng thường có nhiều kiểu biểu diễn:

- Biểu diễn cho lập trình viên đọc: `toString()` và log.
- Biểu diễn cho client: JSON, XML, CSV, Protobuf hoặc định dạng text đã công bố.
- Biểu diễn dùng làm khóa: chuỗi định danh, canonical key, cache key.
- Biểu diễn tồn tại lâu dài: bản ghi lưu trong database, event log, message hoặc chữ ký số.

Không nên xem chúng là một hợp đồng duy nhất. `toString` thường thích hợp để debug, còn wire format và persisted format cần một quy tắc tường minh, có version và có kiểm thử tương thích.

### 5.1. Vì sao không nên dùng `toString()` như giao thức dữ liệu?

Giả sử phiên bản đầu có:

```java
public String toString() {
    return tenantId + ":" + productId;
}
```

Client tách chuỗi theo dấu `:` để lấy hai trường. Một bản nâng cấp thay thành:

```java
public String toString() {
    return "ProductKey[tenant=" + tenantId
            + ", id=" + productId + "]";
}
```

Lời gọi `toString()` vẫn tồn tại và có cùng return type `String`. Nhưng client phân tích chuỗi cũ có thể lỗi ngay lập tức. Ngay cả định dạng cũ `tenantId + ":" + productId` cũng không an toàn nếu một thành phần chứa dấu `:` mà không có quy tắc escaping.

Cách tốt hơn là cung cấp API riêng:

```java
public String toDisplayString() {
    return "Product " + productId + " (tenant " + tenantId + ")";
}

public String toExternalId() {
    // Trả về định danh với encoding/escaping đã được quy định.
    return encodeKey(tenantId, productId);
}
```

`encodeKey` ở đây đại diện cho một thuật toán encoding được định nghĩa riêng; không nên thay bằng phép nối chuỗi không có quy tắc phân tách. Với định danh dùng trên hệ thống khác, cần công bố encoding, escaping và version của định dạng.

### 5.2. Chuỗi biểu diễn số phải có quy tắc locale và precision

Một lời gọi `String.format` hoặc `NumberFormat` sử dụng locale mặc định có thể tạo dấu phân cách thập phân hoặc hàng nghìn khác nhau theo môi trường.

Ví dụ minh họa:

```java
import java.util.Locale;

String output = String.format(Locale.US, "%.2f", 1234.5);
System.out.println(output); // 1234.50
```

Đặt locale tường minh làm kết quả bớt phụ thuộc vào cấu hình máy. Với tiền tệ, hãy xác định riêng precision, rounding mode, đơn vị và scale. `BigDecimal` giúp tránh nhiều vấn đề biểu diễn nhị phân của `double`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal amount = new BigDecimal("1234.5");
String decimal = amount
        .setScale(2, RoundingMode.HALF_UP)
        .toPlainString();

System.out.println(decimal); // 1234.50
```

`RoundingMode.HALF_UP` chỉ là lựa chọn trong ví dụ; hợp đồng tài chính thực tế có thể yêu cầu HALF_EVEN hoặc một quy tắc khác. Đừng âm thầm thay đổi rounding mode khi cập nhật thư viện format.

### 5.3. Ngày giờ: cố định timezone và chuẩn biểu diễn

Không nên phụ thuộc vào `ZoneId.systemDefault()` khi định dạng timestamp dùng trao đổi giữa các hệ thống, trừ khi đó là hợp đồng đã được quy định.

Ví dụ biểu diễn thời điểm ở UTC:

```java
import java.time.Instant;
import java.time.format.DateTimeFormatter;

Instant createdAt = Instant.parse("2025-01-02T03:04:05Z");
String timestamp =
        DateTimeFormatter.ISO_INSTANT.format(createdAt);

System.out.println(timestamp);
```

Với dữ liệu có timezone địa phương, phải quy định cụ thể cách lưu offset, vùng thời gian, độ chính xác giây/nanosecond và xử lý daylight saving time. Đổi từ giờ địa phương sang UTC mà không version hóa schema có thể khiến client diễn giải sai thời điểm.

### 5.4. Charset là phần của hợp đồng wire format

Khi chuyển chuỗi thành byte hoặc ngược lại, chỉ định charset:

```java
import java.nio.charset.StandardCharsets;

byte[] bytes = payload.getBytes(StandardCharsets.UTF_8);
String restored = new String(bytes, StandardCharsets.UTF_8);
```

Nếu để JVM chọn charset mặc định, kết quả có thể phụ thuộc môi trường hoặc thay đổi khi nâng JDK. JEP 400 đưa UTF-8 làm charset mặc định của các API Java tiêu chuẩn trong môi trường chuẩn từ JDK 18; dù vậy, code trao đổi dữ liệu vẫn nên quy định encoding theo hợp đồng để dễ kiểm thử và tích hợp.

### 5.5. JSON và DTO: giữ schema, không chỉ giữ `toString`

Với JSON, hợp đồng có thể bao gồm tên field, kiểu dữ liệu, khả năng null, đơn vị, timezone, tính bắt buộc, dạng enum và hành vi khi xuất hiện field mới. Một thay đổi như:

```json
{"customerId":"C-42","amount":"12.50"}
```

sang:

```json
{"id":"C-42","amount":12.5}
```

có thể phá vỡ parser/validation cũ dù về mặt người đọc hai object có vẻ chứa thông tin gần giống. Tên `customerId` thành `id` và chuỗi `amount` thành số JSON đều là thay đổi schema cần được quản lý.

Trường mới chỉ mang tính tùy chọn có thể tương thích với một số client nhưng không nhất thiết với mọi client, nhất là client từ chối unknown fields hoặc so sánh response JSON nguyên văn. Cần có contract test dựa trên client thực tế và chính sách evolution của định dạng đang dùng.

### 5.6. Enum, Map và thứ tự serialize

- Không dùng `enum.ordinal()` làm giá trị persisted hoặc wire protocol: thêm hoặc đổi thứ tự enum constant sẽ làm ordinal thay đổi.
- `enum.name()` có thể dùng khi tên hằng được xem là schema công khai; đổi tên enum constant là thay đổi hợp đồng.
- Không dựa vào iteration order của `HashMap` để tạo text cần tính xác định. Nếu cần canonical representation, định nghĩa thứ tự field/key rõ ràng.
- Với dữ liệu dùng để ký số hoặc tính digest, phải định nghĩa chính xác byte sequence: charset, escaping, normalization, thứ tự field, định dạng số và newline.

Một thay đổi format có thể không làm lỗi compile, nhưng vẫn thay đổi hash/digest, chữ ký hoặc cách client tái tạo canonical bytes.

## 6. Ví dụ tiến hóa API: thêm trường nhưng giữ hợp đồng định danh

Giả sử phiên bản 1 của thư viện quản lý khách hàng có:

```java
import java.util.Objects;

public final class CustomerRef {
    private final String tenantId;
    private final String customerId;

    public CustomerRef(String tenantId, String customerId) {
        this.tenantId = Objects.requireNonNull(tenantId);
        this.customerId = Objects.requireNonNull(customerId);
    }

    public String tenantId() { return tenantId; }
    public String customerId() { return customerId; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof CustomerRef)) return false;
        CustomerRef that = (CustomerRef) other;
        return tenantId.equals(that.tenantId)
                && customerId.equals(that.customerId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, customerId);
    }
}
```

Ứng dụng dùng `CustomerRef` làm key:

```java
Map<CustomerRef, CustomerProfile> profiles = new HashMap<>();
profiles.put(new CustomerRef("T1", "C42"), profile);

CustomerProfile found =
        profiles.get(new CustomerRef("T1", "C42"));
```

Phiên bản 2 muốn thêm `displayName`. Có hai cách tiến hóa:

**Cách dễ gây breaking change:** thêm `displayName` vào `equals` và `hashCode` vì IDE tự generate lại method dựa trên mọi field. Hai object cùng tenant và customer ID nhưng khác tên sẽ không còn bằng nhau; lookup cũ có thể thất bại.

**Cách duy trì hợp đồng:** giữ `tenantId` và `customerId` làm danh tính; cho `displayName` tham gia hiển thị, nhưng không thay đổi `equals` và `hashCode`. Nếu cần so sánh toàn bộ profile, tạo API so sánh profile riêng.

Một phiên bản 2 có thể giữ constructor cũ và bổ sung constructor mới:

```java
public CustomerRef(String tenantId, String customerId) {
    this(tenantId, customerId, null);
}

public CustomerRef(String tenantId, String customerId,
                   String displayName) {
    this.tenantId = Objects.requireNonNull(tenantId);
    this.customerId = Objects.requireNonNull(customerId);
    this.displayName = displayName;
}
```

Giữ constructor cũ có thể hỗ trợ tương thích source và binary cho các client gọi chữ ký hai tham số, nhưng **không tự bảo đảm tương thích hành vi**. Vẫn phải duy trì quy tắc equality/hash và format bên ngoài. Đồng thời kiểm tra serialization/ORM nếu object này được lưu theo schema khác.

### 6.1. Không trộn thứ tự UI với thứ tự identity

Nếu phiên bản 1 có comparator theo `customerId` và phiên bản 2 muốn hiển thị khách hàng theo `displayName`, nên công bố comparator thứ hai:

```java
Comparator<CustomerRef> BY_ID =
        Comparator.comparing(CustomerRef::tenantId)
                  .thenComparing(CustomerRef::customerId);

Comparator<CustomerRef> BY_DISPLAY_NAME =
        Comparator.comparing(
                CustomerRef::displayName,
                Comparator.nullsLast(String::compareTo))
                  .thenComparing(CustomerRef::tenantId)
                  .thenComparing(CustomerRef::customerId);
```

`BY_ID` phù hợp cho thứ tự key nhất quán với định danh. `BY_DISPLAY_NAME` là thứ tự giao diện, có tie-breaker giúp đầu ra xác định; nó không được mặc định thay thế comparator sử dụng trong một `TreeMap` vốn coi thứ tự key là một phần hợp đồng.

## 7. Test hợp đồng thay vì chỉ test giá trị trả về của API mới

Khi nâng JDK hoặc thư viện, bộ test cần giữ những dữ liệu và hành vi được consumer quan tâm. Một vài test đơn lẻ cho `equals` không đủ nếu ứng dụng dùng sorted collections, cache, serialization hoặc giao thức JSON.

### 7.1. Test luật cơ bản của `equals` và `hashCode`

Ví dụ JUnit Jupiter cho `ProductKey`:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ProductKeyContractTest {
    @Test
    void equalKeysHaveEqualHashCodes() {
        ProductKey first = new ProductKey("T1", "P7");
        ProductKey second = new ProductKey("T1", "P7");
        ProductKey different = new ProductKey("T1", "P8");

        assertEquals(first, first);
        assertEquals(first, second);
        assertEquals(second, first);
        assertEquals(first.hashCode(), second.hashCode());
        assertNotEquals(first, different);
        assertNotEquals(first, null);
    }
}
```

Test trên kiểm tra một số ví dụ quan trọng nhưng chưa chứng minh đầy đủ mọi thuộc tính trên toàn bộ tập dữ liệu. Với kiểu phức tạp, nên xây dựng thêm property-based tests cho đối xứng, bắc cầu, tính nhất quán và cùng-hash-khi-bằng.

### 7.2. Test hành vi khi dùng trong collection

Một kiểm thử có ý nghĩa nghiệp vụ hơn:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;

class ProductKeyCollectionsTest {
    @Test
    void logicalIdentityWorksAsHashKey() {
        ProductKey key1 = new ProductKey("T1", "P7");
        ProductKey key2 = new ProductKey("T1", "P7");

        Map<ProductKey, String> map = new HashMap<>();
        map.put(key1, "READY");

        assertEquals("READY", map.get(key2));

        Set<ProductKey> set = new HashSet<>();
        set.add(key1);
        set.add(key2);
        assertEquals(1, set.size());
    }
}
```

Test này thể hiện đúng ý nghĩa của key: client khác tạo object tương đương vẫn lấy được giá trị đã lưu. Khi một field hiển thị mới được thêm vào class, test cần tiếp tục bảo vệ định nghĩa danh tính ban đầu.

### 7.3. Test comparator và consistency với equality

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Comparator;
import java.util.TreeSet;
import org.junit.jupiter.api.Test;

class ProductKeyOrderTest {
    private static final Comparator<ProductKey> BY_KEY =
            Comparator.comparing(ProductKey::tenantId)
                      .thenComparing(ProductKey::productId);

    @Test
    void comparisonZeroMatchesLogicalIdentity() {
        ProductKey a = new ProductKey("T1", "P1");
        ProductKey b = new ProductKey("T1", "P1");
        ProductKey c = new ProductKey("T1", "P2");

        assertEquals(0, BY_KEY.compare(a, b));
        assertEquals(a, b);
        assertTrue(BY_KEY.compare(a, c) < 0);

        TreeSet<ProductKey> set = new TreeSet<>(BY_KEY);
        set.add(a);
        set.add(b);
        set.add(c);
        assertEquals(2, set.size());
    }
}
```

Nếu comparator không được thiết kế nhất quán với equality, hãy mô tả rõ lý do và test hành vi tập hợp mong muốn. Với comparator dùng cho danh sách UI, consistency với `equals` có thể không phải mục tiêu; với `TreeSet`/`TreeMap` làm nơi lưu key, nó thường là yêu cầu quan trọng.

### 7.4. Golden tests cho biểu diễn dữ liệu

Khi format đã là hợp đồng công khai, lưu bộ dữ liệu mẫu và output kỳ vọng:

| Input mẫu | Điều cần cố định |
|---|---|
| Chuỗi có dấu tiếng Việt, emoji và ký tự Unicode kết hợp | Charset, normalization và escaping |
| Tiền tệ có phần thập phân, giá trị âm và số lớn | Scale, precision, rounding, decimal separator |
| Thời điểm có offset và chuyển ngày | Timezone, offset, định dạng timestamp |
| Chuỗi rỗng, null, field thiếu | Quy tắc biểu diễn null/missing |
| Enum mới và enum không còn sử dụng | Schema/tên giá trị và khả năng đọc phiên bản cũ |
| JSON object có field mới hoặc thay đổi thứ tự | Chính sách unknown fields, thứ tự nếu được cam kết |

Nếu kết quả byte-for-byte quan trọng, so sánh **bytes** thay vì chỉ so sánh object sau deserialize. Nếu hợp đồng cho phép thứ tự field JSON khác nhau, test nên so sánh theo schema/semantics thay vì snapshot chuỗi nguyên văn.

### 7.5. So sánh phiên bản cũ và mới trên cùng fixture

Một quy trình migration hữu ích:

```text
Bộ fixture đã được chốt
        |
        +--> chạy bằng thư viện v1 --> kết quả equality/hash/order/format
        |
        +--> chạy bằng thư viện v2 --> kết quả equality/hash/order/format
                                        |
                                        v
                              so sánh theo hợp đồng
```

Không cần kỳ vọng **mọi giá trị hash số học** giữa hai phiên bản luôn giống nhau trừ khi hệ thống có hợp đồng riêng về việc đó. Phải giữ nguyên thuộc tính “object bằng nhau có hash bằng nhau”; còn nếu hash được persisted hoặc dùng liên tiến trình, cần test chính giá trị hash hoặc thuật toán canonical hash đã được công bố.

Việc chạy riêng từng phiên bản giúp so sánh hành vi mà không phải nạp hai phiên bản cùng tên class vào một class loader. Nếu có consumer đã biên dịch với thư viện v1, cũng cần chạy binary cũ với thư viện v2 để kiểm tra lớp tương thích nhị phân riêng.

## 8. Migration khi bắt buộc thay đổi equality, comparator hoặc format

Không phải lúc nào cũng có thể giữ hợp đồng cũ mãi mãi. Ví dụ, quy tắc định danh mới có thể cần thêm tenant, đơn vị tiền tệ hoặc vùng pháp lý; hệ thống phân trang có thể cần đổi thứ tự; giao thức có thể cần định dạng ngày giờ mới. Khi đó, nên xem đây là **breaking behavioral change** và xây dựng chiến lược chuyển đổi.

### 8.1. Ghi rõ hợp đồng cũ và mới

Một bảng thay đổi có thể ghi:

| Thành phần | Phiên bản cũ | Phiên bản mới | Consumer bị ảnh hưởng |
|---|---|---|---|
| Equality | Theo `customerId` | Theo `tenantId + customerId` | Cache, HashSet, dedup |
| Hash | Theo customer ID | Theo cặp tenant/customer | Cache key, partition, map |
| Comparator | Theo createdAt | Theo createdAt rồi ID | API list, pagination, TreeSet |
| JSON field | `createdAt` là local text | `createdAt` là ISO-8601 UTC | Clients, event subscribers |

Đừng chỉ viết “cải thiện comparator” hoặc “refactor equals” trong changelog. Cần mô tả **tập input nào sẽ cho kết quả khác** và cách consumer chuyển đổi.

### 8.2. Version hóa hành vi khi cần hỗ trợ song song

Với sort order, có thể cung cấp hai comparator/API được đặt tên rõ:

```java
Comparator<Order> LEGACY_ORDER = ...;
Comparator<Order> ORDER_V2 = ...;
```

Với wire format, có thể công bố schema version mới, API endpoint versioned hoặc một DTO mới. Trong thời gian migration, server có thể hỗ trợ đọc cả định dạng cũ và mới, nhưng chỉ ghi một định dạng chuẩn sau khi consumer đã sẵn sàng.

Với equality, thay đổi ngay `equals` của một class public đang làm khóa có thể gây tác động rộng. Khi không thể duy trì ngữ nghĩa cũ, cân nhắc tạo loại key mới có tên rõ như `TenantCustomerKey` thay vì âm thầm đổi `CustomerKey`.

### 8.3. Xử lý lại trạng thái lưu trữ và index

Nếu hash hoặc comparator đã được dùng làm cấu trúc lưu trữ, migration có thể cần:

- Xây dựng lại cache hoặc invalidation để không mang key cũ sang thuật toán mới.
- Reindex dữ liệu đã sắp xếp hoặc cấu trúc tìm kiếm.
- Migrate partition/shard nếu khóa phân phối thực sự đã đổi.
- Cấp lại pagination cursor theo phiên bản sort mới.
- Chuyển đổi dữ liệu persisted theo schema mới.
- Cho phép đọc định dạng cũ trong giai đoạn chuyển tiếp.

Đặc biệt, không nên thay đổi các field dùng trong hash của **key đang nằm trong HashMap/HashSet** rồi hy vọng collection tự sắp xếp lại. Cần tạo lại collection hoặc di chuyển entry theo khóa mới.

### 8.4. Triển khai theo phiên bản consumer

Trong hệ thống nhiều dịch vụ, producer và consumer có thể không cập nhật đồng thời. Kiểm thử các tổ hợp phù hợp:

- Producer cũ ↔ consumer cũ: baseline.
- Producer mới ↔ consumer mới: hợp đồng mục tiêu.
- Producer mới ↔ consumer cũ: backward compatibility khi rollout producer trước.
- Producer cũ ↔ consumer mới: forward compatibility khi rollout consumer trước.

Với định dạng biểu diễn, xác định rõ tổ hợp nào được cam kết hỗ trợ. Nếu thay đổi gây breaking behavior, cần thứ tự triển khai, feature flag hoặc versioned endpoint thay vì giả định tất cả dịch vụ sẽ nâng cùng lúc.

## 9. Các tình huống đặc biệt đáng chú ý

### 9.1. ORM entity và proxy

JPA/Hibernate hoặc framework tương tự có thể tạo proxy subclass. Việc `equals` dựa vào `getClass`, ID trước/sau persistence hoặc field lazy-loaded có thể dẫn đến kết quả bất ngờ.

Khi thay đổi entity, kiểm thử cùng lúc:

- Entity mới, chưa có ID hoặc chưa được lưu.
- Entity đã lưu, có ID ổn định.
- Entity được nạp ở transaction/session khác.
- Proxy và entity gốc nếu framework tạo proxy.
- Entity đặt vào `HashSet` trước và sau khi trạng thái persistence thay đổi.

Không có một công thức equals phù hợp cho tất cả ORM. Cần dựa trên mô hình định danh, lifecycle và yêu cầu của framework.

### 9.2. Cache và idempotency

Một service có thể dùng `CustomerKey` làm key cho cache hoặc bộ lọc xử lý trùng. Nếu equality hoặc canonical key thay đổi, cùng một request có thể không còn được nhận diện là duplicate. Hậu quả có thể là xử lý giao dịch hai lần, bỏ qua cache hoặc trả dữ liệu sai.

Với idempotency key, nên dùng một định danh hoặc canonical representation đã được công bố, không dựa vào `toString`/`hashCode` mặc định của object nghiệp vụ. Kiểm thử cả phiên bản dịch vụ cũ và mới bằng cùng tập request.

### 9.3. Comparator trong database và pagination

API có thể sắp xếp dữ liệu trong Java trong khi truy vấn database cũng có `ORDER BY`. Nếu hai phía dùng quy tắc collation khác nhau, thứ tự có thể không khớp. Điều này đặc biệt nguy hiểm với pagination/cursor: một bản ghi có thể di chuyển giữa các trang khi thay đổi thứ tự hoặc tie-breaker.

Hãy mô tả sort key theo cách có thể tái tạo trên cả server và database, chú ý null ordering, locale/collation, timezone và các giá trị trùng. Nếu đổi comparator, hãy version hóa cursor hoặc làm mất hiệu lực cursor cũ theo một chính sách công khai.

### 9.4. Tương thích với Kotlin/Scala hoặc client không phải Java

Các client JVM khác cũng có thể sử dụng `equals`/`hashCode` và các collection Java, nhưng chúng có thể sinh equality tự động theo class/value type của riêng ngôn ngữ. Khi sửa một Java API public, cần kiểm tra consumer JVM hiện có và cách chúng ánh xạ dữ liệu.

Nếu các client ngoài JVM nhận JSON hoặc text, chúng không quan tâm trực tiếp đến method Java, nhưng sẽ bị ảnh hưởng nếu wire representation, thứ tự danh sách hoặc quy tắc null/encoding thay đổi.

### 9.5. Log và audit không chỉ là trình bày

Thay đổi `toString` có thể được chấp nhận khi nó chỉ phục vụ debug, nhưng nếu log được hệ thống phân tích bằng biểu thức chính quy, dùng cho audit hoặc tạo alert, định dạng thực tế đã trở thành một hợp đồng vận hành.

Với các luồng này, ưu tiên structured logging có schema ổn định. Trường log mới nên được thêm có chủ đích; không dùng output của `toString` từ entity phức tạp làm message được máy phân tích.

## 10. Quy trình đánh giá một thay đổi API

Khi thay một value object, comparator hoặc serializer, có thể đi theo trình tự:

### Bước 1: Kiểm kê nơi hành vi được sử dụng

Tìm các lời gọi `equals`, `hashCode`, `compareTo`, `Comparator`, `sort`, `TreeSet`, `TreeMap`, `HashSet`, `HashMap`, serializer và các đoạn biến object thành chuỗi. Đừng chỉ tìm lời gọi trực tiếp: nhiều collection và framework gọi các method này ngầm.

### Bước 2: Ghi hợp đồng dự kiến

Xác định thành phần định danh, trường nào được bỏ qua, quy tắc null, quan hệ equality-comparator, thứ tự tie-breaker, precision/rounding, timezone, charset và schema output. Phân biệt điều bắt buộc ổn định với chi tiết không được cam kết.

### Bước 3: Chốt fixture từ phiên bản đang phát hành

Lấy các trường hợp đại diện như cùng ID/khác tên, mã nhiều tenant, null, Unicode, giá trị số bằng nhau khác scale, timestamp có offset, key trùng sort key và trường hợp biên. Giữ expected behavior được xác nhận của version cũ.

### Bước 4: Thực hiện thay đổi và chạy contract tests

Kiểm thử luật Java cơ bản, hành vi collection, comparator và định dạng dữ liệu. Nếu có schema/wire protocol, chạy các consumer tests; nếu có persisted hash/key, kiểm thử migration của chúng.

### Bước 5: Đánh giá tương thích theo từng lớp

| Lớp tương thích | Kiểm tra |
|---|---|
| Source | Biên dịch lại consumer/source được hỗ trợ |
| Binary | Chạy binary consumer cũ với artifact mới khi cần |
| Hành vi đối tượng | Equality/hash, collection lookup, comparator order |
| Dữ liệu | Schema, encoding, format, parser cũ/mới |
| Vận hành | Cache, idempotency, partition, index, pagination, log |

### Bước 6: Phát hành với migration guide

Nếu thay đổi là breaking behavior, tài liệu cần nêu đầu vào chịu ảnh hưởng, hành vi cũ/mới, cách chuyển đổi, khả năng đọc dữ liệu cũ, thứ tự rollout và hướng rollback. Đừng chỉ dựa vào semver hay changelog tổng quát.

### Bước 7: Theo dõi sau triển khai

Quan sát các chỉ số có ý nghĩa như cache miss rate, tỷ lệ trùng lặp, idempotency conflict, lỗi deserialize, lỗi parse, thay đổi phân bố sort/page và số lượng dữ liệu cần reindex. Nếu có cơ chế hỗ trợ song song hai format, theo dõi mức sử dụng format cũ trước khi loại bỏ.

## 11. Những hiểu nhầm thường gặp

**“Method `equals` và `hashCode` vẫn tồn tại nên API tương thích.”** Cùng chữ ký chỉ giúp một phần binary/source compatibility. Ý nghĩa của kết quả có thể thay đổi.

**“Object không bằng nhau phải có hash khác nhau.”** Không. Hash collision được phép; chỉ có chiều “bằng nhau thì hash bằng nhau” là bắt buộc.

**“Mã hash bắt buộc bất biến giữa mọi JDK và mọi tiến trình.”** Không phải hợp đồng chung của Java. Nếu cần định danh bền vững, hãy thiết kế một API key riêng và version hóa thuật toán.

**“Dùng comparator để sort chỉ ảnh hưởng thứ tự hiển thị.”** Trong `TreeMap` và `TreeSet`, comparator còn xác định khi nào hai key được xem là trùng. Đổi comparator có thể đổi cả tập dữ liệu.

**“Comparator trả về 0 nghĩa là `equals` luôn true.”** Không mặc định. `BigDecimal` và comparator không phân biệt hoa/thường là những ví dụ rõ ràng.

**“Sort stable thì thứ tự output luôn xác định.”** Không nếu comparator hòa nhiều phần tử và thứ tự đầu vào không xác định. Cần tie-breaker ổn định cho API phân trang hoặc snapshot.

**“Thêm field vào record không ảnh hưởng equality.”** Equality/hash tự sinh của record dựa trên components, vì vậy thay đổi cấu trúc record có thể thay đổi hợp đồng ngữ nghĩa.

**“`toString` chỉ để debug, đổi thế nào cũng được.”** Đúng với API không cam kết format và không có consumer phụ thuộc; sai nếu hệ thống đã dùng output làm dữ liệu trao đổi, cache key, audit hoặc parser.

**“JSON có cùng thông tin nên đổi tên field hay kiểu số/chuỗi vẫn tương thích.”** Không. Client có thể kiểm tra schema chặt chẽ hoặc dựa vào kiểu field chính xác.

**“Biên dịch lại tất cả consumer là xong.”** Compile không phát hiện thay đổi semantic equality, comparator, cache key hoặc wire representation. Cần contract tests và kế hoạch migration dữ liệu.

## 12. Checklist giữ ổn định hợp đồng

- [ ] Đã định nghĩa chính xác những field/thuộc tính tạo nên equality.
- [ ] `equals` thỏa phản xạ, đối xứng, bắc cầu, nhất quán và khác null.
- [ ] `hashCode` dựa trên cùng tiêu chí equality; key hash không biến đổi trong khi nằm trong collection.
- [ ] Đã đánh giá tác động đến `HashMap`, `HashSet`, cache và idempotency.
- [ ] Đã xác định comparator nào là thứ tự định danh, comparator nào chỉ phục vụ trình bày.
- [ ] Đã kiểm tra tính đúng đắn, tính bắc cầu và trường hợp comparator trả về 0.
- [ ] Đã đánh giá sự nhất quán với `equals` khi dùng `TreeMap` hoặc `TreeSet`.
- [ ] Thứ tự API có tie-breaker rõ ràng khi phân trang hoặc cần kết quả tái tạo.
- [ ] Chính sách null, locale, Unicode, case và collation được quy định.
- [ ] Không dùng `toString` như wire format nếu không có hợp đồng được công bố rõ.
- [ ] Numeric scale, rounding, timezone, charset và kiểu dữ liệu JSON được cố định.
- [ ] Không dùng `hashCode` hoặc `enum.ordinal()` làm định danh persisted nếu không có cơ chế version riêng.
- [ ] Đã xây dựng fixture/golden tests cho phiên bản cũ và mới.
- [ ] Đã kiểm thử dữ liệu và consumer cũ theo thứ tự triển khai thực tế.
- [ ] Đã xem xét reindex, invalidate cache, chuyển đổi persisted key và version hóa cursor nếu cần.
- [ ] Breaking behavior được công bố trong release notes/migration guide, không chỉ trong code diff.

## 13. Kết luận

Trong tiến hóa API Java, `equals`, `hashCode`, comparator và định dạng biểu diễn là những **hợp đồng hành vi** có thể quan trọng không kém public method signature. Chúng quyết định object có được xem là cùng một giá trị hay không, khóa có được tìm thấy trong collection, bản ghi được sắp theo thứ tự nào và dữ liệu được diễn giải ra sao bên ngoài JVM.

Để giữ tương thích, cần xác định tiêu chí equality và hash ổn định, không đưa trạng thái mutable hoặc field hiển thị vào định danh một cách vô tình; duy trì comparator có ngữ nghĩa rõ ràng và tie-breaker thích hợp; định nghĩa representation theo schema, encoding, locale, timezone và precision tường minh. Khi buộc phải thay đổi, hãy coi đó là behavioral breaking change, cung cấp đường migration và xác minh bằng contract tests trên consumer, cache và dữ liệu thực tế.

**Một API có thể vẫn compile và link thành công nhưng không còn tương thích với điều mà người dùng của API đã tin tưởng.** Bảo vệ các hợp đồng hành vi này là phần cốt lõi của một chiến lược Java compatibility migration an toàn.
