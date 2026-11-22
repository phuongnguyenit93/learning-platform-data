# Chọn thành phần bất biến cho đối tượng giá trị và khóa trong Java

## 1. Vấn đề cần giải quyết

Trong thiết kế Java, **đối tượng giá trị** (*value object*) biểu diễn một giá trị theo **nội dung**, thay vì theo danh tính của một thực thể đang thay đổi. Ví dụ, mã tiền tệ, khoảng ngày, tọa độ, mã hàng đã chuẩn hóa, hoặc khóa tổng hợp `(tenantId, productCode)` có thể được mô hình hóa thành value object.

Một đối tượng được dùng làm **khóa** trong `HashMap`/`HashSet` còn phải giữ ổn định các thuộc tính tham gia `equals()` và `hashCode()` trong suốt thời gian nó nằm trong cấu trúc băm. Nếu thuộc tính đó thay đổi, đối tượng có thể nằm trong “bucket” được tính bằng hash cũ, trong khi lần tra cứu mới dùng hash mới.

Vì vậy, khi chọn thành phần (*component/field*) của value object hoặc key, không chỉ hỏi “trường này có ý nghĩa nghiệp vụ không?” mà còn phải hỏi:

- Giá trị có ổn định trong toàn bộ vòng đời đối tượng không?
- Nếu là tham chiếu, **bản thân đối tượng được tham chiếu** và toàn bộ trạng thái dùng để so sánh có bất biến không?
- Phép so sánh của kiểu dữ liệu có đúng ngữ nghĩa nghiệp vụ không?
- Cần chuẩn hóa dữ liệu đầu vào trước khi tính bằng nhau không?
- Đối tượng có tự bảo vệ khỏi thay đổi qua tham số constructor hoặc accessor không?
- Trường nào thật sự định nghĩa bình đẳng giá trị? Trường nào chỉ là dữ liệu mô tả, không nên tham gia identity của khóa?

**Bất biến (*immutability*)** nghĩa là trạng thái quan sát được qua API của đối tượng không thể đổi sau khi được xây dựng. `final` trên một biến/trường chỉ ngăn gán lại tham chiếu đó, **không** tự biến đối tượng mà nó trỏ đến thành bất biến.

## 2. Mối liên hệ giữa bất biến, `equals()` và `hashCode()`

Hợp đồng quan trọng của Java:

- `equals()` phải có tính phản xạ, đối xứng, bắc cầu và nhất quán khi thông tin dùng cho so sánh không thay đổi; so với `null` phải trả về `false`.
- Nếu `a.equals(b)` là `true`, bắt buộc `a.hashCode() == b.hashCode()`. Điều ngược lại **không** bắt buộc: hash bằng nhau vẫn có thể là hai giá trị khác nhau.
- Khi đối tượng đang là khóa băm, không được thay đổi trạng thái góp phần vào `equals()`/`hashCode()`. Ngay cả khi chương trình chỉ giữ **cùng một tham chiếu**, việc đổi hash có thể làm `get()` hoặc `containsKey()` không tìm thấy khóa.

Bất biến là cách đơn giản và mạnh để duy trì hợp đồng này. Tuy nhiên, **một khóa vẫn có thể hợp lệ nếu lớp mutable nhưng tuyệt đối không bị thay đổi khi đang nằm trong map**; vấn đề là điều kiện đó khó duy trì và kiểm chứng khi hệ thống lớn lên. Ưu tiên key bất biến sẽ giảm hẳn lớp lỗi này.

Đối với các cấu trúc **có thứ tự** như `TreeMap`/`TreeSet`, còn cần `compareTo()` hoặc `Comparator` ổn định và phù hợp với khái niệm khóa bằng nhau của miền bài toán. Nếu thứ tự so sánh coi hai giá trị là tương đương nhưng `equals()` không coi chúng bằng nhau, hành vi của tree collection có thể khác hash collection.

## 3. Chọn kiểu thành phần nào?

Một hướng chọn thực dụng là dùng các giá trị có trạng thái bất biến, có ngữ nghĩa bình đẳng rõ ràng và không chứa đường đi tới trạng thái mutable có thể quan sát được.

| Nhóm thành phần | Thường phù hợp làm thành phần bất biến? | Điều phải xem xét |
| --- | --- | --- |
| Kiểu nguyên thủy `int`, `long`, `boolean`, ... | Có | Chọn kiểu/đơn vị diễn tả đúng miền dữ liệu; cẩn trọng `float`/`double` |
| `String`, `UUID`, wrapper `Integer`/`Long`, `BigInteger` | Có | Quy tắc chuẩn hóa, so sánh và miền giá trị |
| `LocalDate`, `LocalDateTime`, `Instant`, `Duration`, `ZoneId` | Có | Phân biệt ngày địa phương, thời điểm toàn cầu, múi giờ và đơn vị thời gian |
| `BigDecimal` | Bản thân bất biến | `equals()` xét cả `scale`; `compareTo()` có thể cho kết quả khác |
| `enum` | Có | Chọn hằng nghiệp vụ ổn định; không dựa vào `ordinal()` làm mã lưu trữ lâu dài |
| Value object tự định nghĩa, mọi thành phần bất biến | Có | Phải bảo đảm bất biến xuyên suốt và `equals()/hashCode()` đúng |
| `List`, `Set`, `Map` | Chỉ khi cấu trúc **và** các phần tử/khóa/giá trị liên quan đều an toàn | `List.copyOf`, `Set.copyOf`, `Map.copyOf` chỉ sao chép nông các tham chiếu phần tử |
| Mảng `byte[]`, `int[]`, mảng đối tượng | Không, nếu lộ trực tiếp | Mảng luôn mutable; cần defensive copy và bình đẳng theo nội dung nếu dùng làm value |
| `Date`, `Calendar`, `StringBuilder`, `ArrayList`, `HashMap` | Không trực tiếp | Mutable; cần chuyển thành biểu diễn bất biến hoặc sao chép sâu trong phạm vi thích hợp |
| `AtomicInteger`, `AtomicReference` | Không trực tiếp | Thread-safe cho thao tác riêng lẻ **không có nghĩa là bất biến** |
| `ByteBuffer`, entity JPA, DTO có setter | Thường không | Trạng thái, vị trí con trỏ, quan hệ và dữ liệu có thể đổi |

**Lưu ý về bộ sưu tập:** một collection không cho `add()`/`remove()` vẫn có thể chứa đối tượng mutable. Khi đối tượng con bị sửa, trạng thái logic của key vẫn thay đổi dù container không thêm/xóa phần tử được.

**Lưu ý về kiểu thời gian:** `java.util.Date` mutable, trong khi `java.time.Instant` bất biến. Một key biểu diễn “ngày đặt hàng” nên cân nhắc `LocalDate`; key biểu diễn “thời điểm chính xác” nên cân nhắc `Instant`. Hai khái niệm không thể hoán đổi nếu bỏ qua múi giờ.

## 4. Ví dụ Java 17: key bất biến được chuẩn hóa

Đặt trong tệp `ImmutableKeyDemo.java`:

```java
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

public class ImmutableKeyDemo {
    record ProductKey(String tenant, String sku, int revision) {
        ProductKey {
            Objects.requireNonNull(tenant, "tenant");
            Objects.requireNonNull(sku, "sku");

            tenant = tenant.trim().toLowerCase(Locale.ROOT);
            sku = sku.trim().toUpperCase(Locale.ROOT);

            if (tenant.isEmpty() || sku.isEmpty()) {
                throw new IllegalArgumentException("Empty tenant or sku");
            }
            if (revision < 0) {
                throw new IllegalArgumentException("Negative revision");
            }
        }
    }

    public static void main(String[] args) {
        ProductKey first = new ProductKey(" Store-A ", " ab-10 ", 2);
        ProductKey equivalent = new ProductKey("store-a", "AB-10", 2);
        ProductKey differentVersion = new ProductKey("store-a", "AB-10", 3);

        Map<ProductKey, String> inventory = new HashMap<>();
        inventory.put(first, "Available");

        System.out.println(first.equals(equivalent));
        System.out.println(first.hashCode() == equivalent.hashCode());
        System.out.println(inventory.get(equivalent));
        System.out.println(inventory.get(differentVersion));
        System.out.println(first);
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 ImmutableKeyDemo.java
java ImmutableKeyDemo
```

Kết quả:

```text
true
true
Available
null
ProductKey[tenant=store-a, sku=AB-10, revision=2]
```

Giải thích:

1. `ProductKey` là `record` với ba thành phần bất biến: `String`, `String`, `int`. Java sinh `equals()`, `hashCode()`, accessor và `toString()` theo thành phần của record.
2. *Compact constructor* là nơi chuẩn hóa dữ liệu **trước khi** bản ghi hoàn tất khởi tạo; các tham số `tenant`/`sku` đã chuẩn hóa được gán vào trường tương ứng.
3. `Locale.ROOT` giúp chuẩn hóa chữ hoa/chữ thường theo quy tắc độc lập với locale máy đang chạy. Đây chỉ là **chính sách ví dụ**: một hệ thống phân biệt hoa/thường ở SKU không được áp dụng chính sách này.
4. Hai key biểu diễn cùng bộ ba giá trị chuẩn hóa có `equals() == true` và hash bằng nhau; việc tra cứu map bằng key mới hoạt động.
5. `revision` là một phần giá trị khóa, vì ví dụ này định nghĩa mỗi phiên bản là một key khác nhau. Nếu miền bài toán chỉ dùng SKU để xác định danh tính, không được tự động thêm `revision` vào equality.

**Quy tắc thiết kế:** chọn tập thành phần từ **ngữ nghĩa nghiệp vụ của khóa** trước, sau đó bảo đảm mọi thành phần được chọn có trạng thái an toàn. Thêm quá nhiều trường mutable hoặc dữ liệu trình bày vào `equals()`/`hashCode()` có thể khiến key trở nên mong manh.

## 5. Lỗi điển hình: thay đổi thành phần của một key trong `HashMap`

Tệp `MutableKeyDemo.java` cho thấy một lỗi dù không hề thay thế tham chiếu đến key:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class MutableKeyDemo {
    public static void main(String[] args) {
        List<String> key = new ArrayList<>(List.of("A"));
        Map<List<String>, String> map = new HashMap<>();

        map.put(key, "found");
        System.out.println(map.get(key));

        key.set(0, "B");
        System.out.println(map.get(key));
        System.out.println(map.containsKey(List.of("A")));
        System.out.println(map.size());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 MutableKeyDemo.java
java MutableKeyDemo
```

Kết quả trên Java 17:

```text
found
null
false
1
```

Giải thích chính xác:

- `ArrayList.equals()` và `ArrayList.hashCode()` dựa trên nội dung phần tử.
- Khi đưa `["A"]` vào map, map dùng hash của danh sách tại thời điểm đó.
- Sau `key.set(0, "B")`, hash của cùng danh sách thay đổi; tra cứu bằng `key` mới không thấy mục đã lưu. `List.of("A")` cũng không bằng key đã biến thành `["B"]`.
- `map.size()` vẫn là `1`: entry không tự biến mất; vấn đề nằm ở tính nhất quán giữa vị trí lưu và khóa dùng để tìm. Các bucket được trình bày chỉ để giải thích hành vi; kết quả tra cứu trong ví dụ dùng khóa cụ thể `"A"` và `"B"`.

**Không được** sửa một key mutable đang nằm trong map rồi dựa vào `remove(key)` để chắc chắn lấy được phần tử ra: chính thao tác `remove` cũng dùng hash hiện tại. Khi cần đổi giá trị khóa, hãy xóa entry bằng **khóa ban đầu vẫn còn hợp lệ**, rồi chèn entry mới với một key bất biến khác; nếu đã làm hỏng map do biến đổi key, cần có chiến lược khôi phục tương thích với toàn bộ cấu trúc.

## 6. `record` và `final` chưa bảo đảm bất biến sâu

`record` giúp biểu diễn value object ngắn gọn và tự sinh các phương thức dựa trên thành phần. Tuy nhiên, record chỉ cố định **tham chiếu thành phần**; nó không tự đóng băng đối tượng con.

Ví dụ có vấn đề:

```java
record UnsafeGroupKey(String tenant, java.util.List<String> members) {}
```

Code trên chỉ là định nghĩa kiểu. Nếu truyền một `ArrayList` vào `UnsafeGroupKey`, bên ngoài vẫn có thể sửa danh sách gốc; accessor `members()` cũng trả về cùng danh sách. Vì `List.equals()`/`hashCode()` phụ thuộc phần tử, hash của record thay đổi cùng danh sách.

### Cách làm đúng khi phần tử tự nó bất biến

Tệp `DefensiveRecordDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class DefensiveRecordDemo {
    record GroupKey(String tenant, List<String> members) {
        GroupKey {
            if (tenant == null || tenant.isBlank()) {
                throw new IllegalArgumentException("Missing tenant");
            }
            members = List.copyOf(members);
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("An", "Bình"));
        GroupKey key = new GroupKey("T1", source);
        Map<GroupKey, String> map = Map.of(key, "team");

        source.add("Chi");

        System.out.println(key.members());
        System.out.println(map.get(new GroupKey("T1", List.of("An", "Bình"))));

        try {
            key.members().add("Dũng");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Unmodifiable");
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 DefensiveRecordDemo.java
java DefensiveRecordDemo
```

Kết quả:

```text
[An, Bình]
team
Unmodifiable
```

`List.copyOf` ngăn caller sửa cấu trúc qua biến `source` rồi ảnh hưởng tới cấu trúc danh sách bên trong key, và danh sách trả từ `members()` không cho thao tác thêm/xóa. Các phần tử ở đây là `String` bất biến nên có thể được chia sẻ an toàn. Nếu `members` là `List<Member>` mà `Member` mutable, **mã này chưa đủ**: phải chuyển `Member` sang value object bất biến hoặc sao chép từng `Member` theo đúng hợp đồng.

`List.copyOf`, `Set.copyOf` và `Map.copyOf` tạo collection không thể chỉnh sửa qua API của chúng nhưng **không sao chép sâu** phần tử/khóa/giá trị; các factory này cũng không chấp nhận phần tử `null` (với `Map.copyOf`, cả khóa và giá trị đều không được `null`).

**Cẩn thận với constructor/accessor:**

- Constructor chỉ copy nhưng accessor trả ra tham chiếu mutable bên trong → vẫn rò rỉ trạng thái.
- Accessor trả bản sao nhưng constructor lưu tham chiếu đầu vào trực tiếp → caller vẫn sửa được từ bên ngoài.
- Cả hai phía cần được bảo vệ khi dữ liệu con mutable, hoặc dùng **kiểu dữ liệu con bất biến thật sự**.

## 7. Mảng là trường hợp cần xử lý riêng

Mảng Java luôn mutable. Thêm nữa, `equals()`/`hashCode()` mặc định của mảng dùng **danh tính mảng**, không so sánh nội dung. Ví dụ hai `new byte[] {1, 2}` là hai đối tượng khác nhau; `array1.equals(array2)` là `false`.

Nếu dùng một `record BlobKey(byte[] data)`, phương thức `equals()`/`hashCode()` được sinh ra **không tự so mảng theo nội dung**; đồng thời `data()` có thể cho phép sửa trực tiếp mảng. Cần quyết định một trong hai hướng:

1. Chuyển dữ liệu mảng sang một kiểu giá trị bất biến có bình đẳng theo nội dung phù hợp.
2. Tự viết lớp hoặc record với defensive copy ở đầu vào/đầu ra và `Arrays.equals()`/`Arrays.hashCode()` tương ứng; nếu phần tử mảng là tham chiếu, còn phải quyết định mức copy sâu.

### Ví dụ lớp bất biến giữ nội dung `byte[]`

Tệp `ByteArrayKeyDemo.java`:

```java
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;

public class ByteArrayKeyDemo {
    static final class ByteArrayKey {
        private final byte[] data;

        ByteArrayKey(byte[] data) {
            this.data = data.clone();
        }

        byte[] bytes() {
            return data.clone();
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof ByteArrayKey that)) return false;
            return Arrays.equals(data, that.data);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(data);
        }
    }

    public static void main(String[] args) {
        byte[] source = {1, 2};
        ByteArrayKey key = new ByteArrayKey(source);
        Map<ByteArrayKey, String> map = new HashMap<>();
        map.put(key, "OK");

        source[0] = 9;
        byte[] exposed = key.bytes();
        exposed[1] = 8;

        System.out.println(Arrays.toString(key.bytes()));
        System.out.println(key.equals(new ByteArrayKey(new byte[] {1, 2})));
        System.out.println(map.get(new ByteArrayKey(new byte[] {1, 2})));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ByteArrayKeyDemo.java
java ByteArrayKeyDemo
```

Kết quả:

```text
[1, 2]
true
OK
```

Hai lần `clone()` ở **constructor** và **accessor** bảo vệ khỏi sửa qua cả hai hướng; `Arrays.equals`/`Arrays.hashCode` thống nhất theo nội dung. Với mảng `byte[]`, `clone()` đủ để tạo bản sao dữ liệu các phần tử nguyên thủy. Với `MutableItem[]`, clone chỉ tạo **mảng mới**, không nhân bản từng `MutableItem`.

Cũng cần kiểm tra `null` một cách tường minh nếu API cho phép hoặc cấm `null`. Ở ví dụ này, truyền `null` vào constructor sẽ gây `NullPointerException` tại lời gọi `clone()`; trong API thực tế nên dùng `Objects.requireNonNull(data, "data")` để làm rõ hợp đồng.

## 8. Trạng thái bất biến có thể bị rò rỉ qua nhiều tầng

Ví dụ `List<List<String>>`: chỉ gọi `List.copyOf(outer)` khiến danh sách ngoài không thể sửa nhưng các danh sách trong vẫn mutable nếu nguồn ban đầu mutable. Nếu đối tượng key chứa danh sách lồng nhau, cần copy **cả container ngoài và từng container con** cần bảo vệ.

Đoạn mã minh họa, áp dụng khi phần tử cuối cùng đều là `String` bất biến:

```java
List<List<String>> snapshot = source.stream()
        .map(List::copyOf)
        .toList();
```

Đoạn trên dùng `source` là `List<List<String>>` đã tồn tại và Java 17+; `Stream.toList()` trả về danh sách không thể sửa. Nếu cấu trúc sâu thêm một tầng `List<List<Member>>` với `Member` mutable thì vẫn chưa giải quyết phần `Member`. Đối với `Map<Key, Value>`, phải đánh giá **cả key lẫn value** nếu trạng thái value là một phần của value object; `Map.copyOf` không làm các value mutable trở thành bất biến.

So sánh ba cách thường bị nhầm:

| Cách | Cấu trúc collection qua tham chiếu kết quả | Dữ liệu con mutable |
| --- | --- | --- |
| `new ArrayList<>(original)` | Có thể sửa; container mới | Phần tử vẫn chia sẻ |
| `Collections.unmodifiableList(original)` | Không sửa qua view; view phản ánh thay đổi cấu trúc từ `original` | Phần tử vẫn chia sẻ |
| `List.copyOf(original)` | Không sửa qua danh sách kết quả, cấu trúc chụp tại thời điểm copy | Phần tử vẫn chia sẻ |

Khi đầu vào đã bất biến, `List.copyOf` có thể trả lại cùng instance; đây không phải lỗi vì mục tiêu là ổn định cấu trúc. Khi đầu vào có thay đổi đồng thời từ luồng khác, quá trình copy cần một cơ chế tạo snapshot nhất quán riêng nếu miền bài toán yêu cầu.

## 9. Bình đẳng số học không luôn trùng với `equals()`: `BigDecimal`

`BigDecimal` **bất biến**, nhưng không phải cứ hai số có cùng trị số là `equals()` bằng nhau. `BigDecimal.equals()` xét cả **giá trị và scale**, trong khi `compareTo()` so theo trị số.

Tệp `BigDecimalKeyDemo.java`:

```java
import java.math.BigDecimal;
import java.util.HashSet;
import java.util.List;
import java.util.TreeSet;

public class BigDecimalKeyDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("1.0");
        BigDecimal b = new BigDecimal("1.00");

        System.out.println(a.equals(b));
        System.out.println(a.compareTo(b) == 0);
        System.out.println(new HashSet<>(List.of(a, b)).size());
        System.out.println(new TreeSet<>(List.of(a, b)).size());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 BigDecimalKeyDemo.java
java BigDecimalKeyDemo
```

Kết quả:

```text
false
true
2
1
```

`HashSet` dùng `equals()`/`hashCode()`; `TreeSet` dùng thứ tự sắp xếp (ở đây là `BigDecimal.compareTo()`). Hai collection vì thế có cách xác định phần tử trùng khác nhau.

Nếu miền bài toán cho rằng `1.0` và `1.00` biểu diễn cùng giá trị, cần quy ước **canonical form** ngay lúc tạo key; ví dụ xử lý `stripTrailingZeros()` và thống nhất zero theo nhu cầu nghiệp vụ. Nếu scale mang ý nghĩa nghiệp vụ (độ chính xác khai báo, đơn vị, định dạng hóa đơn), có thể **cố ý giữ scale** để phân biệt. Không tự thay đổi `equals()` theo `compareTo()` mà quên `hashCode()`; hai phương thức phải tương thích.

Với tiền tệ, lựa chọn kiểu số còn gắn với **đơn vị, mã tiền tệ và quy tắc làm tròn**. Một khóa gồm `(amount, currency)` phải giải thích rõ giá trị `amount` được chuẩn hóa ra sao; một `long` số đơn vị nhỏ nhất chỉ phù hợp khi miền bài toán định nghĩa rõ số chữ số thập phân và phạm vi.

### `double`/`float` cần chính sách so sánh riêng

Các kiểu dấu chấm động có `NaN`, vô cực và hai giá trị `+0.0`/`-0.0`. Không nên cho rằng quy tắc so sánh toán học thông thường là đủ để định nghĩa key. `Double.equals()` và các phương thức wrapper có quy tắc riêng đối với `NaN` và dấu của zero; bản thân phép `==` ở kiểu nguyên thủy còn có hành vi khác. Nếu cần khóa theo số đo liên tục, hãy xác định cách làm tròn, độ chính xác và cách biểu diễn chuẩn **trước khi** chọn thành phần; tránh tự cài `equals()` bằng dung sai `epsilon` vì có thể phá tính bắc cầu.

## 10. Chọn đúng trường theo ngữ nghĩa nghiệp vụ

Tính bất biến chỉ là điều kiện kỹ thuật. Một key còn phải chứa **đúng các trường định nghĩa danh tính giá trị** trong phạm vi sử dụng.

Xét một sản phẩm có `productId` không đổi, `displayName` có thể được đổi, `price` cập nhật theo thời điểm:

- Nếu map muốn tra **thực thể sản phẩm** qua một khóa lâu dài, `productId` thường là ứng viên tốt; đưa `displayName` hoặc `price` vào key sẽ làm khóa gắn với thuộc tính dễ đổi.
- Nếu map muốn tra **báo giá tại phiên bản cụ thể**, cặp `(productId, priceVersion)` có thể có nghĩa. `priceVersion` nên là giá trị được cố định trong key được tạo mới, không phải trường mutable bị sửa tại chỗ.
- Nếu business key là `(tenantId, externalCode)`, cả hai thành phần phải có quy tắc rõ về hoa/thường, khoảng trắng, Unicode và `null`.

Ví dụ mô hình hợp đồng:

```text
Entity Product:
    id = P-42             // danh tính ổn định
    displayName = "..."   // thuộc tính có thể đổi
    price = ...            // thuộc tính có thể đổi

Value Key:
    ProductId("P-42")     // giá trị bất biến
    ProductVersion("P-42", 7) // phiên bản được phân biệt có chủ đích
```

Đây là sơ đồ minh họa, không phải mã Java để biên dịch. Một **value object** có thể là thành phần của entity, nhưng value object không có nghĩa là entity. Cũng không có quy tắc bắt buộc “mọi trường của một object phải tham gia `equals()`”: với class thường, trường metadata/trạng thái dẫn xuất có thể bị loại khỏi equality theo hợp đồng; với record mặc định, equality tính trên **tất cả** thành phần record.

### Chuẩn hóa trước khi tạo key

Hãy quyết định rõ ràng:

- Chữ hoa/thường có ý nghĩa không? `toLowerCase(Locale.ROOT)` là lựa chọn độc lập locale nếu nghiệp vụ muốn không phân biệt chữ, nhưng không phù hợp cho mọi mã định danh hoặc văn bản tự nhiên.
- Có bỏ khoảng trắng đầu/cuối, chuẩn hóa Unicode, gộp nhiều dấu cách, hay chuyển định dạng dấu phân cách không? Nếu có, quy tắc phải nhất quán giữa ghi và tra cứu.
- Các cách biểu diễn `null`, chuỗi rỗng, “unknown” có tương đương không? Cân nhắc cấm trạng thái không hợp lệ ngay trong constructor.
- Nếu key là tổ hợp nhiều thành phần, thứ tự trong `List` có ý nghĩa không? Nếu thứ tự không có nghĩa, cân nhắc kiểu tập hợp và quy tắc xử lý phần tử trùng.
- Nếu key dùng để lưu trữ/caching qua nhiều phiên bản ứng dụng, schema và cách chuẩn hóa có ổn định không? Khi thay đổi chính sách key, cần xem xét migration, cache invalidation và tương thích dữ liệu.

**Không sửa key tại chỗ để “chuẩn hóa sau”**; hãy chuẩn hóa khi tạo rồi xuất bản một đối tượng bất biến.

## 11. Thiết kế class bất biến khi record không phù hợp

`record` có các ưu điểm: ngắn, component `private final`, accessor không có setter và sinh equality theo mọi component. Dù vậy, record không luôn phù hợp:

- Cần so sánh dựa trên **một phần** các trường, hoặc có trạng thái dẫn xuất/cached value không thuộc equality.
- Muốn che giấu biểu diễn lưu trữ, ví dụ mảng byte, nhưng vẫn dùng equality theo nội dung.
- Cần kế thừa lớp khác: record không thể `extends` một class tùy ý (record kế thừa `java.lang.Record`).
- Cần kiểm soát chặt accessor để không rò rỉ tham chiếu mutable.

Một `final class` bất biến thường dùng các nguyên tắc:

1. Đặt lớp `final` (hoặc kiểm soát nghiêm ngặt khả năng kế thừa), đóng các trường bằng `private final`.
2. Validate và chuẩn hóa toàn bộ dữ liệu đầu vào trong constructor/factory trước khi lưu.
3. Defensive copy mọi thành phần mutable cần được sở hữu riêng ở **đầu vào**.
4. Không cung cấp phương thức thay đổi trạng thái; bảo vệ **đầu ra** qua giá trị bất biến, bản sao hoặc read-only interface có hợp đồng rõ.
5. Viết `equals()`/`hashCode()` đồng nhất theo **các trường thực sự định nghĩa giá trị**, không dựa vào tham chiếu của mảng/collection mutable.
6. Nếu có trường được dẫn xuất hoặc hash được cache, bảo đảm cache không làm thay đổi quan sát công khai và không phá hợp đồng equality.
7. Kiểm tra khởi tạo an toàn, nhất là khi đối tượng sẽ được sử dụng giữa nhiều luồng; `final` hỗ trợ mô hình bộ nhớ Java nhưng không chữa việc làm rò rỉ `this` trong constructor hay lưu mutable reference không được bảo vệ.

Nếu muốn sử dụng `Lombok @Value`, `@EqualsAndHashCode` hoặc mã sinh tự động, vẫn phải kiểm tra đúng thành phần equality và deep immutability; annotation không tự deep-copy các đối tượng mutable bên trong.

## 12. Không nhầm immutable, unmodifiable và thread-safe

- **Immutable object:** trạng thái quan sát của chính đối tượng không thay đổi sau khởi tạo. Một chuỗi `String` là ví dụ phổ biến.
- **Unmodifiable view:** API view không cho chỉnh sửa, nhưng dữ liệu nguồn có thể đổi. `Collections.unmodifiableList(mutableList)` là ví dụ.
- **Unmodifiable snapshot container:** cấu trúc kết quả không cho sửa và không thay đổi theo các thao tác sửa cấu trúc nguồn sau lúc copy, như `List.copyOf(source)`; nội dung con mutable vẫn có thể đổi.
- **Thread-safe mutable object:** có thể thay đổi trạng thái trong môi trường đồng thời theo hợp đồng, như `AtomicInteger`. Nó không trở thành immutable.

Vì vậy, cấu trúc kiểu sau không phải một key bất biến đúng nghĩa:

```java
record CounterKey(String label, java.util.concurrent.atomic.AtomicInteger value) {}
```

`AtomicInteger` mutable. Record giữ tham chiếu `value` cố định nhưng giá trị số bên trong vẫn thay đổi, và equality mặc định của record dành cho `AtomicInteger` sử dụng equality của chính đối tượng đó, không tự biểu diễn bình đẳng theo giá trị số đang giữ. Nếu khóa phải gắn với số tại thời điểm xây dựng, hãy lấy `int snapshot = value.get()` rồi lưu `int` hoặc wrapper bất biến trong key.

**Snapshot consistency:** đọc từng trường của một object đang bị cập nhật bởi nhiều luồng có thể tạo key với các trường đến từ hai thời điểm khác nhau. Defensive copy và `final` không tự đảm bảo snapshot đa trường nhất quán; cần giao thức khóa, immutable snapshot được công bố an toàn hoặc cơ chế versioning khi cần.

## 13. Kiểm thử hợp đồng value object và map key

Viết test dựa trên **hành vi quan sát được**, không chỉ kiểm tra có `final` hay có `record`.

| Tình huống kiểm thử | Điều cần đúng |
| --- | --- |
| Hai input khác cách viết nhưng chuẩn hóa thành cùng khóa | `equals() == true` và hash bằng nhau |
| Hai key khác dữ liệu identity | `equals() == false` theo quy tắc đã định |
| Tra cứu bằng instance khác nhưng bằng giá trị | `map.get(equivalentKey)` tìm đúng entry |
| Sửa mảng/list đầu vào sau khi tạo key | Giá trị key, hash và kết quả tra cứu không đổi |
| Lấy accessor rồi thử sửa dữ liệu trả ra | Không sửa được trạng thái nội bộ của key |
| Thành phần lồng nhiều tầng, phần tử mutable | Không có đường sửa vô ý vào trạng thái key |
| `null`, rỗng, dữ liệu không hợp lệ | Bị từ chối hoặc được xử lý theo chính sách đã ghi |
| `BigDecimal` khác scale, số dấu chấm động đặc biệt | Bình đẳng/khóa theo đúng quy ước nghiệp vụ |
| Ghi cache/map dài hạn | Khóa giữ ổn định qua thao tác thường xuyên và không phụ thuộc trường trình bày |

Một kiểm thử đặc biệt có giá trị là:

1. Tạo key từ một **nguồn mutable**.
2. Chèn key vào `HashMap`.
3. Thay đổi nguồn mutable và cố gắng thay đổi dữ liệu qua accessor.
4. Tạo key mới tương đương với **giá trị ban đầu**.
5. Xác nhận `get(newEquivalentKey)` vẫn tìm được entry, `equals()/hashCode()` của key cũ vẫn giữ nguyên.

Test này thường bắt được lỗi defensive copy bị quên ở constructor hoặc accessor. Với record chứa mảng, còn phải kiểm tra equality theo nội dung thay vì dùng identity mảng.

## 14. Sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách giải quyết |
| --- | --- | --- |
| “Trường `final List<T>` nên value object bất biến” | Chỉ tham chiếu final, list/phần tử còn mutable | Bảo vệ cả container và phần tử |
| “Record tự deep-copy mọi component” | Record không tự copy mutable reference | Dùng compact constructor và sao chép phù hợp |
| “`List.copyOf` luôn deep copy” | Phần tử tham chiếu vẫn dùng chung | Dùng value element bất biến hoặc copy từng phần tử |
| “Mảng ở record tự được so theo phần tử” | Mảng mặc định so theo identity | `Arrays.equals/hashCode` cùng defensive copy |
| “`BigDecimal("1.0")` và `BigDecimal("1.00")` là cùng key” | `equals()` xét scale | Canonicalize nếu nghiệp vụ muốn bằng nhau |
| “Hash giống nhau tức là `equals()` true” | Collision là hợp lệ | Dùng `equals()` xác nhận |
| “Key chỉ cần hash ổn định, equality đổi cũng không sao” | `equals()` là một phần hợp đồng tra cứu | Ổn định toàn bộ trạng thái tham gia equality |
| “Dùng giá bán/tên hiển thị để định danh sản phẩm” | Thuộc tính dễ đổi, không nhất thiết là identity | Dùng identifier bất biến đúng miền dữ liệu |
| “Immutable tức là thread-safe trong mọi trường hợp” | Quá trình lấy snapshot từ nguồn mutable có thể không nhất quán | Bảo đảm snapshot và publication phù hợp |
| “Cứ copy object là có key độc lập” | Có thể chỉ copy nông | Kiểm tra từng tham chiếu và ranh giới sở hữu |

## 15. Quy trình chọn thành phần cho một key mới

**Bước 1 — Định nghĩa quan hệ bình đẳng nghiệp vụ.** Viết câu: “Hai key bằng nhau khi và chỉ khi ...”. Ví dụ: “Cùng tenant, cùng mã SKU theo quy tắc không phân biệt hoa/thường, cùng số phiên bản”.

**Bước 2 — Chọn biểu diễn bất biến.** Ưu tiên primitive, `String`, `UUID`, `java.time` và các nested value object thật sự bất biến. Với mảng/collection, xác định chính xác mức sở hữu và sao chép.

**Bước 3 — Chuẩn hóa và validate tại biên.** Chốt locale, nullability, Unicode, scale, đơn vị đo và phiên bản. Từ chối trạng thái bất hợp lệ khi tạo object.

**Bước 4 — Tạo immutable API.** Có thể dùng record cho tập component thuần bất biến, hoặc `final class` nếu cần kiểm soát sâu, so sánh đặc biệt, getter bảo vệ hay encapsulation.

**Bước 5 — Đảm bảo `equals/hashCode` cùng ngữ nghĩa.** Với tree collection còn cần comparator nhất quán với định nghĩa trùng khóa mong muốn.

**Bước 6 — Kiểm thử chống mutation và tra cứu tương đương.** Sửa dữ liệu đầu vào hoặc mọi tham chiếu có thể lấy ra; xác nhận key và map không bị ảnh hưởng.

**Bước 7 — Tài liệu hóa hợp đồng.** Ghi rõ trường nào tham gia identity, cách chuẩn hóa, alias nào được phép, và tác động khi schema key thay đổi.

## 16. Câu hỏi tự kiểm tra

1. Một `record OrderKey(String id, List<OrderLine> lines)` dùng `List.copyOf(lines)` nhưng `OrderLine` có setter. Có thật sự là key bất biến không? Vì sao?
2. Nếu dùng `byte[]` lưu SHA-256 digest, vì sao không nên chỉ tạo `record Digest(byte[] bytes)` rồi để Java sinh `equals/hashCode`?
3. Tại sao `Collections.unmodifiableList(original)` khác `List.copyOf(original)` khi `original` tiếp tục được chỉnh sửa?
4. Một hệ thống coi giá tiền `1.0` và `1.00` là tương đương. Phải quyết định chính sách nào trước khi đưa `BigDecimal` vào key?
5. Khi nào nên dùng `ProductId(id)`, khi nào cần `ProductVersion(id, version)`, và vì sao không nên đưa tên sản phẩm thay đổi liên tục vào key lâu dài?
6. Vì sao `final AtomicInteger counter` không chứng minh được trạng thái của đối tượng bất biến?

**Ghi nhớ:** thành phần tốt cho value object và key phải có **ngữ nghĩa bình đẳng đúng**, **trạng thái ổn định**, và **không rò rỉ mutation qua tham chiếu bên trong**. Record, `final` và unmodifiable collection là công cụ hỗ trợ; hợp đồng bất biến sâu và `equals()/hashCode()` vẫn cần được thiết kế, kiểm thử rõ ràng.