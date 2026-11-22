# Phân nhóm theo khóa ghép bằng đối tượng giá trị

## 1. Bài toán: một thuộc tính không đủ để xác định nhóm

Trong **Java Stream API**, `filter` và `map` giúp chọn, biến đổi phần tử; `collect` là thao tác kết thúc dùng để gom dữ liệu thành kết quả. Một collector quan trọng là `Collectors.groupingBy`: nó phân loại từng phần tử theo một **khóa nhóm** rồi tích lũy những phần tử có cùng khóa.

Đôi khi khóa nhóm chỉ gồm một thuộc tính, như `department` hoặc `year`. Nhưng báo cáo thực tế thường cần kết hợp nhiều điều kiện: doanh thu **theo khu vực và loại hàng**, số đơn **theo khách hàng và tháng**, hay kết quả học tập **theo lớp và học kỳ**.

Nếu chỉ nhóm theo khu vực, hai loại hàng của cùng khu vực bị gộp chung. Nếu chỉ nhóm theo loại hàng, dữ liệu từ nhiều khu vực lại hòa vào nhau. Ta cần **khóa ghép** (*composite key*) chứa cả hai thuộc tính.

```text
Đơn hàng
  ├─ (Miền Bắc, Sách, 100)
  ├─ (Miền Bắc, Bút,   30)
  ├─ (Miền Nam,  Sách,  80)
  └─ (Miền Bắc, Sách,  50)
          │
          ▼ classifier: Order -> GroupKey(region, category)
          │
          ▼ groupingBy
  ┌───────────────────────┬─────────────────┐
  │ Khóa ghép             │ Nhóm đơn hàng   │
  ├───────────────────────┼─────────────────┤
  │ (Miền Bắc, Sách)      │ 100, 50         │
  │ (Miền Bắc, Bút)       │ 30              │
  │ (Miền Nam,  Sách)     │ 80              │
  └───────────────────────┴─────────────────┘
```

Một cách biểu diễn khóa nhóm an toàn, rõ nghĩa là dùng **đối tượng giá trị** (*value object*): đối tượng được so sánh dựa trên các giá trị thành phần, không dựa vào danh tính tham chiếu. Trong Java hiện đại, `record` rất phù hợp cho nhiệm vụ này.

Sau bài học, bạn có thể:

1. Tạo khóa ghép bằng `record` hoặc lớp bất biến với `equals`/`hashCode`.
2. Dùng `groupingBy` để tạo `Map<CompositeKey, List<T>>`.
3. Kết hợp downstream collector như `counting`, `summingLong`, `mapping` và `collectingAndThen` để tính kết quả theo từng khóa.
4. Chuẩn hóa dữ liệu khóa; xử lý `null`; xác định chính sách về thứ tự, song song và chi phí bộ nhớ.
5. Tránh lỗi nối chuỗi làm khóa, dùng mảng làm khóa, hoặc thay đổi khóa sau khi đưa vào Map.

Ví dụ hoàn chỉnh sử dụng **Java 17+**, vì `record` đã trở thành tính năng chính thức từ Java 16. `Collectors.groupingBy` và các nguyên tắc về khóa Map có từ Java 8.

## 2. Cơ chế groupingBy và vai trò của khóa

Overload cơ bản của `groupingBy` là:

```java
static <T, K> Collector<T, ?, Map<K, List<T>>> groupingBy(
        Function<? super T, ? extends K> classifier)
```

`classifier` nhận từng phần tử đầu vào `T` và trả về khóa `K`. Những phần tử có các khóa **bằng nhau theo cơ chế của Map kết quả** được gom vào cùng nhóm.

Ví dụ chỉ nhóm theo một trường:

```java
record Order(String id, String region, String category, long amount) {}

List<Order> orders = List.of(
        new Order("O01", "Bắc", "Sách", 100),
        new Order("O02", "Bắc", "Bút", 30),
        new Order("O03", "Nam", "Sách", 80),
        new Order("O04", "Bắc", "Sách", 50)
);

Map<String, List<Order>> byRegion = orders.stream()
        .collect(Collectors.groupingBy(Order::region));

System.out.println(byRegion.get("Bắc").size()); // 3
```

Trong `byRegion`, cả đơn sách lẫn đơn bút của khu vực Bắc cùng thuộc một nhóm. Muốn tách tiếp theo loại hàng, classifier phải trả về **cả hai thuộc tính** dưới một kiểu khóa phù hợp.

`groupingBy` là một **Collector** được truyền cho terminal operation `collect`. Mỗi phần tử được classifier phân loại trong quá trình thu thập; không cần tự tạo rồi duyệt hai lần một danh sách trung gian. Tuy nhiên, cách tổ chức nội bộ và số lần kết hợp các kết quả từng phần phụ thuộc vào việc pipeline tuần tự hay song song.

## 3. Thiết kế composite key bằng record

Định nghĩa một `record` nhỏ chứa đúng các thành phần xác định danh tính nhóm:

```java
record GroupKey(String region, String category) {}
```

Java tự sinh constructor, accessor `region()`/`category()`, cùng `equals`, `hashCode` và `toString` cho `record`. Hai đối tượng `GroupKey` được xem là bằng nhau nếu **các thành phần tương ứng bằng nhau**.

```java
GroupKey first = new GroupKey("Bắc", "Sách");
GroupKey second = new GroupKey("Bắc", "Sách");
GroupKey third = new GroupKey("Nam", "Sách");

System.out.println(first == second);      // false: hai tham chiếu khác nhau
System.out.println(first.equals(second)); // true: giá trị các thành phần bằng nhau
System.out.println(first.equals(third));  // false
System.out.println(first.hashCode() == second.hashCode()); // true
```

Vì Map thường dùng `equals` và `hashCode` để quản lý khóa, kết quả của `record` phù hợp với việc tạo một khóa mới từ mỗi đơn hàng:

```java
Map<GroupKey, List<Order>> groups = orders.stream()
        .collect(Collectors.groupingBy(
                order -> new GroupKey(order.region(), order.category())
        ));

GroupKey northBooks = new GroupKey("Bắc", "Sách");

System.out.println(groups.get(northBooks).size()); // 2
System.out.println(groups.size());                 // 3
```

Mặc dù biểu thức classifier tạo một đối tượng `GroupKey` mới ở mỗi lượt, các khóa có giá trị bằng nhau vẫn được nhóm đúng. Tính đúng đắn **không phụ thuộc việc tái sử dụng cùng một instance**.

### Vì sao nên dùng đối tượng giá trị?

| Tiêu chí | Khóa bằng `record GroupKey` | Khóa bằng chuỗi ghép thủ công |
| --- | --- | --- |
| Cấu trúc | Có tên và kiểu riêng cho từng trường | Phải tự quy ước dấu phân cách |
| So sánh bằng nhau | `equals`/`hashCode` theo thành phần | So sánh toàn bộ chuỗi đã nối |
| Truy xuất thông tin | `key.region()`, `key.category()` | Phải tách chuỗi để lấy trường |
| Tính đúng đắn | Giảm lỗi trùng khóa do mã hóa nhập nhằng | Có thể va chạm nếu dữ liệu chứa dấu phân cách |
| Bảo trì | Thêm, đổi quy tắc trường một cách rõ ràng | Dễ tạo những khóa chuỗi khác quy ước |

Ví dụ va chạm khi nối chuỗi thiếu quy tắc mã hóa:

```java
String a = "A:B" + ":" + "C"; // A:B:C
String b = "A" + ":" + "B:C"; // A:B:C

// Hai cặp thuộc tính khác nhau nhưng tạo cùng một khóa String.
```

Không nên giải quyết bằng việc tự thêm thật nhiều ký tự phân cách nếu nghiệp vụ cần một khóa gồm nhiều trường. Một `record` hoặc lớp khóa có giá trị bất biến thể hiện mục đích rõ ràng hơn.

## 4. equals và hashCode là hợp đồng cốt lõi

Hai `GroupKey` có nội dung như nhau phải được Map nhận diện là cùng một khóa. Với cấu trúc `HashMap` thông thường:

- `hashCode` giúp xác định vùng lưu khóa; các khóa bằng nhau **bắt buộc có cùng hash code**.
- `equals` phân biệt các khóa thực sự bằng nhau, kể cả khi hash code trùng nhau.
- Khóa sau khi đưa vào Map phải có các thành phần tham gia `equals`/`hashCode` **ổn định**.

`record` tự cung cấp những phương thức này cho các trường đã khai báo, nhưng tính an toàn còn phụ thuộc loại dữ liệu thành phần. `String`, `Integer`, `LocalDate` và `enum` là những lựa chọn thông dụng, ổn định.

### Không dùng array làm khóa nếu muốn so sánh theo nội dung

`record` không biến so sánh mảng thành so sánh theo phần tử:

```java
record BadKey(String[] fields) {}

BadKey a = new BadKey(new String[] {"Bắc", "Sách"});
BadKey b = new BadKey(new String[] {"Bắc", "Sách"});

System.out.println(a.equals(b)); // false
```

Hai mảng được cấp phát riêng; `equals` của mảng không so sánh nội dung như `Arrays.equals`. Ngoài ra, mảng có thể bị sửa, gây bất ổn định cho khóa. Với hai trường đã biết, hãy khai báo hai thành phần `String` trong `GroupKey`. Với số trường động, cân nhắc một đối tượng khóa bất biến có định nghĩa bình đẳng tường minh.

### Không dùng đối tượng khóa mutable

```java
class MutableKey {
    String region;
    String category;

    MutableKey(String region, String category) {
        this.region = region;
        this.category = category;
    }

    @Override public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof MutableKey key)) return false;
        return java.util.Objects.equals(region, key.region)
                && java.util.Objects.equals(category, key.category);
    }

    @Override public int hashCode() {
        return java.util.Objects.hash(region, category);
    }
}

MutableKey key = new MutableKey("Bắc", "Sách");
Map<MutableKey, Integer> map = new java.util.HashMap<>();
map.put(key, 2);
key.region = "Nam"; // SAI về thiết kế: đổi thành phần tạo hash sau khi dùng làm khóa
```

Sau thay đổi, tra cứu `map.get(key)` có thể thất bại vì Map đã đặt entry theo hash code cũ. Không dùng cách này làm nền tảng cho báo cáo hoặc cache. Với `record` chỉ chứa các thành phần bất biến, trường hợp trên tránh được. **Record chỉ bất biến nông:** nếu một thành phần chứa mảng, danh sách hoặc đối tượng mutable khác, vẫn cần bản sao và quy tắc bất biến cho thành phần đó.

## 5. Nếu không dùng record: lớp value object trên Java 8

Với codebase phải hỗ trợ Java 8, định nghĩa một lớp `final` với trường `private final`, constructor, getter, `equals` và `hashCode`:

```java
import java.util.Objects;

public final class GroupKey {
    private final String region;
    private final String category;

    public GroupKey(String region, String category) {
        this.region = Objects.requireNonNull(region);
        this.category = Objects.requireNonNull(category);
    }

    public String getRegion() { return region; }
    public String getCategory() { return category; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof GroupKey)) return false;
        GroupKey that = (GroupKey) other;
        return region.equals(that.region)
                && category.equals(that.category);
    }

    @Override
    public int hashCode() {
        return Objects.hash(region, category);
    }
}
```

Lớp minh họa này đặt ở file `GroupKey.java` khi dùng trong chương trình Java thông thường. `region` và `category` là chuỗi bất biến nên nội dung khóa ổn định. Với Java hiện đại, `record GroupKey(String region, String category)` thường ngắn và ít lỗi hơn.

Không nên dựa vào `toString` của đối tượng để làm khóa Map: biểu diễn chuỗi phục vụ hiển thị có thể thay đổi theo cách viết class, còn `equals`/`hashCode` phải diễn đạt đúng danh tính nghiệp vụ của nhóm.

## 6. Phân nhóm thành Map<GroupKey, List<Order>>

Ví dụ nguồn có bốn đơn hàng, trong đó hai đơn thuộc cùng cặp khu vực và loại hàng:

```java
Map<GroupKey, List<Order>> byRegionAndCategory = orders.stream()
        .collect(Collectors.groupingBy(
                order -> new GroupKey(order.region(), order.category())
        ));

List<Order> northBooks = byRegionAndCategory.get(
        new GroupKey("Bắc", "Sách")
);

System.out.println(northBooks.stream().map(Order::id).toList());
// [O01, O04]
```

Các mốc cần nhớ:

1. Kiểu phần tử nguồn là `Order`.
2. Classifier có kiểu logic `Function<Order, GroupKey>`.
3. Kết quả là `Map<GroupKey, List<Order>>`.
4. Mỗi key đại diện cho **một tổ hợp** các thuộc tính; mỗi value là danh sách phần tử cùng nhóm.

`groupingBy(classifier)` không cam kết Map kết quả có kiểu triển khai cụ thể hoặc thứ tự lặp khóa. Nếu muốn đọc một nhóm, dùng `get(new GroupKey(...))`. Nếu muốn in báo cáo theo thứ tự ổn định, định nghĩa thứ tự rõ ràng thay vì tin vào `Map.toString()`.

Nếu cần kiểm tra nhóm có tồn tại, dùng `containsKey` hoặc `getOrDefault`; tránh gọi thẳng phương thức trên kết quả `get` mà không xét trường hợp thiếu khóa:

```java
List<Order> westBooks = byRegionAndCategory.getOrDefault(
        new GroupKey("Tây", "Sách"),
        List.of()
);

System.out.println(westBooks.size()); // 0
```

Không có đơn nào trong một tổ hợp thì `groupingBy` **không tự tạo mục khóa với nhóm rỗng**. Nếu báo cáo yêu cầu đủ mọi tổ hợp khu vực × loại hàng, cần xây dựng danh sách các tổ hợp hợp lệ hoặc bổ sung nhóm thiếu sau khi thu thập.

## 7. Downstream collector: đếm và cộng theo khóa ghép

Đôi khi không cần giữ toàn bộ đối tượng đơn hàng. Ta chỉ muốn **một số tổng hợp cho mỗi tổ hợp khóa**. Khi đó sử dụng overload `groupingBy(classifier, downstream)`:

```java
Map<GroupKey, Long> counts = orders.stream()
        .collect(Collectors.groupingBy(
                order -> new GroupKey(order.region(), order.category()),
                Collectors.counting()
        ));

System.out.println(counts.get(new GroupKey("Bắc", "Sách"))); // 2
```

`Collectors.counting()` tạo số đếm `Long` cho mỗi nhóm; không tạo `List<Order>` trung gian như groupingBy mặc định.

Tính tổng số tiền theo khóa ghép:

```java
Map<GroupKey, Long> amountTotals = orders.stream()
        .collect(Collectors.groupingBy(
                order -> new GroupKey(order.region(), order.category()),
                Collectors.summingLong(Order::amount)
        ));

System.out.println(amountTotals.get(new GroupKey("Bắc", "Sách")));
// 150
```

Trong trường hợp này, `summingLong` nhận từng `Order` trong nhóm và lấy `amount()`. Nếu số tiền là tiền thật có đơn vị nhỏ nhất, có thể dùng `long` với kiểm soát overflow; nếu cần tính thập phân chính xác, sử dụng `BigDecimal` với phép tích lũy phù hợp.

### Thu thập nhiều đại lượng của mỗi nhóm

`summarizingLong` tính số lượng, tổng, min, max, trung bình trong một collector:

```java
Map<GroupKey, LongSummaryStatistics> summaries = orders.stream()
        .collect(Collectors.groupingBy(
                order -> new GroupKey(order.region(), order.category()),
                Collectors.summarizingLong(Order::amount)
        ));

LongSummaryStatistics northBookStats =
        summaries.get(new GroupKey("Bắc", "Sách"));

System.out.println(northBookStats.getCount()); // 2
System.out.println(northBookStats.getSum());   // 150
System.out.println(northBookStats.getMin());   // 50
System.out.println(northBookStats.getMax());   // 100
```

`LongSummaryStatistics` là **đối tượng tích lũy có thể thay đổi**. Nếu kết quả được công bố cho code khác và cần tránh việc bị sửa sau thu thập, chuyển mỗi thống kê thành một đối tượng giá trị kết quả riêng ở bước cuối:

```java
record Summary(long count, long totalAmount) {}

Map<GroupKey, Summary> immutableSummaries = orders.stream()
        .collect(Collectors.groupingBy(
                order -> new GroupKey(order.region(), order.category()),
                Collectors.collectingAndThen(
                        Collectors.summarizingLong(Order::amount),
                        stats -> new Summary(stats.getCount(), stats.getSum())
                )
        ));

System.out.println(immutableSummaries.get(
        new GroupKey("Bắc", "Sách")
)); // Summary[count=2, totalAmount=150]
```

`Summary` là record có các trường nguyên thủy nên bản thân giá trị thống kê không thể bị chỉnh sửa. **Map ngoài vẫn có thể sửa cấu trúc** theo hợp đồng mặc định của collector: nếu cần công bố một Map không sửa được, tạo bản sao bằng `Map.copyOf(immutableSummaries)` khi thích hợp.

## 8. Chỉ lấy thuộc tính cần thiết của mỗi nhóm với mapping

Nếu báo cáo cần danh sách **mã đơn hàng theo từng tổ hợp**, thay vì chứa toàn bộ `Order`, dùng downstream `Collectors.mapping`:

```java
Map<GroupKey, List<String>> idsByGroup = orders.stream()
        .collect(Collectors.groupingBy(
                order -> new GroupKey(order.region(), order.category()),
                Collectors.mapping(
                        Order::id,
                        Collectors.toList()
                )
        ));

System.out.println(idsByGroup.get(new GroupKey("Bắc", "Sách")));
// [O01, O04]
```

`groupingBy` quyết định **nhóm**, còn `mapping` quyết định **giá trị nào được đưa vào mỗi nhóm**. Có thể kết hợp thêm `filtering` downstream (Java 9+) hoặc lọc trước `groupingBy` tùy muốn bỏ cả nhóm hay giữ nhóm có kết quả downstream rỗng.

Ví dụ, chỉ lấy đơn có `amount() >= 80` trước khi nhóm:

```java
Map<GroupKey, List<Order>> highValueGroups = orders.stream()
        .filter(order -> order.amount() >= 80)
        .collect(Collectors.groupingBy(
                order -> new GroupKey(order.region(), order.category())
        ));
```

Những tổ hợp không còn phần tử sau `filter` **sẽ không xuất hiện** trong Map. Nếu dùng `Collectors.filtering` làm downstream của `groupingBy`, một khóa đã được classifier gặp có thể vẫn tồn tại với Collection rỗng khi các phần tử trong nhóm đều không qua bộ lọc. Đây là khác biệt có ý nghĩa khi tạo báo cáo cần giữ các nhóm gốc.

## 9. Khóa ghép hay groupingBy lồng nhau?

Cùng bài toán có thể giải quyết bằng **groupingBy lồng nhau**:

```java
Map<String, Map<String, List<Order>>> nested = orders.stream()
        .collect(Collectors.groupingBy(
                Order::region,
                Collectors.groupingBy(Order::category)
        ));

System.out.println(nested.get("Bắc").get("Sách").size()); // 2
```

So sánh hai cách:

| Khía cạnh | Khóa ghép `Map<GroupKey, List<Order>>` | Map lồng `Map<Region, Map<Category, ...>>` |
| --- | --- | --- |
| Một khóa biểu diễn | Một tổ hợp thuộc tính hoàn chỉnh | Một cấp trong phân cấp nhóm |
| Tra cứu nhóm | `get(new GroupKey(r, c))` | `get(r).get(c)` sau khi kiểm tra null |
| Duyệt toàn bộ tổ hợp | Duyệt các entry của một Map | Duyệt từng Map lồng |
| Thêm trường nhóm thứ ba | Thêm thành phần vào value object | Thường cần thêm một cấp Map |
| Truy vấn riêng theo khu vực | Phải lọc các khóa ghép hoặc lập chỉ mục riêng | Lấy trực tiếp `nested.get(region)` |
| Đọc mô hình | Phù hợp khi tổ hợp là danh tính một nhóm | Phù hợp với phân cấp khu vực → loại hàng |

Không có cách nào luôn tốt hơn. Chọn **khóa ghép** khi tổ hợp thuộc tính có ý nghĩa như một khóa nghiệp vụ thống nhất (báo cáo theo tháng + chi nhánh, nhóm hàng + khu vực). Chọn **Map lồng** khi người dùng thường cần điều hướng, tổng hợp hoặc hiển thị dữ liệu theo từng cấp.

`groupingBy` và `partitioningBy` cũng khác nhau. `partitioningBy(predicate)` tạo hai nhánh khóa `Boolean` cho đúng/sai và luôn có hai khóa; nó phù hợp với một điều kiện nhị phân, không thay thế một khóa ghép gồm nhiều thuộc tính độc lập.

## 10. Chuẩn hóa khóa để tránh tách nhóm không mong muốn

Trong dữ liệu thực, `"north"`, `" NORTH "` và `"North"` có thể cùng chỉ một vùng. `record` chỉ so sánh **giá trị thực tế của trường**, không tự hiểu quy tắc chuẩn hóa nghiệp vụ.

```java
record RegionCategory(String region, String category) {}

List<Order> noisy = List.of(
        new Order("O10", "north", "Books", 20),
        new Order("O11", " NORTH ", "books", 30)
);

Map<RegionCategory, Long> before = noisy.stream()
        .collect(Collectors.groupingBy(
                o -> new RegionCategory(o.region(), o.category()),
                Collectors.counting()
        ));
System.out.println(before.size()); // 2: hai khóa String khác nhau
```

Nếu nghiệp vụ xem các cách viết đó là tương đương, chuẩn hóa **trước khi tạo khóa**:

```java
static String normalize(String value) {
    return value.strip().toUpperCase(java.util.Locale.ROOT);
}

// Đặt trong cùng lớp chứa normalize:
Map<RegionCategory, Long> after = noisy.stream()
        .collect(Collectors.groupingBy(
                o -> new RegionCategory(
                        normalize(o.region()),
                        normalize(o.category())
                ),
                Collectors.counting()
        ));

System.out.println(after.size()); // 1
```

Hàm chuẩn hóa phải diễn đạt **chính sách dữ liệu**, không phải mẹo kỹ thuật. Ví dụ, chuẩn hóa bằng chữ hoa có phù hợp với mã phân biệt chữ hoa/chữ thường không? Nếu các thành phần là `enum` hoặc ID chuẩn hóa từ tầng nhập liệu, có thể không cần gọi `toUpperCase` nữa.

Với dữ liệu cần hiển thị chữ gốc, vẫn có thể giữ `Order` đầy đủ trong từng nhóm, còn `GroupKey` chứa giá trị chuẩn hóa. Tránh thay đổi chính đối tượng nguồn trong classifier để đạt được việc chuẩn hóa.

## 11. Null trong classifier và trong thành phần khóa

`Collectors.groupingBy` yêu cầu **giá trị do classifier trả về không được là `null`**. Nếu trả về `null`, terminal operation sẽ ném `NullPointerException` (thường với thông điệp về khóa null).

```java
// SAI: classifier có thể trả về null.
Map<String, List<Order>> invalid = orders.stream()
        .collect(Collectors.groupingBy(o ->
                o.region().equals("Bắc") ? o.category() : null
        ));
```

Nhưng cần phân biệt **toàn bộ khóa bằng null** với **một record key có thành phần null**. `new GroupKey(null, "Sách")` vẫn là một đối tượng `GroupKey` khác null. Record mặc định cho phép thành phần null; `equals`/`hashCode` của record có thể xử lý thành phần đó. Tuy nhiên, để dữ liệu rõ nghĩa, nên kiểm tra đầu vào hoặc tạo quy ước giá trị thiếu:

```java
record StrictKey(String region, String category) {
    StrictKey {
        java.util.Objects.requireNonNull(region, "region");
        java.util.Objects.requireNonNull(category, "category");
    }
}
```

Compact constructor ở trên từ chối thiếu trường ngay khi tạo khóa. Nếu nghiệp vụ cho phép khu vực chưa xác định, có thể ánh xạ `null` thành một `enum UNKNOWN` hoặc một giá trị đại diện có quy ước rõ ràng. Không nên âm thầm gộp mọi dạng dữ liệu lỗi vào cùng nhóm nếu người dùng cần phân biệt nguyên nhân.

Lưu ý thêm: `Map.copyOf` và các collector `toUnmodifiableMap` từ chối khóa hoặc giá trị null; trong khi một số `Map` mutable có thể hỗ trợ null. Chính sách của Map đầu ra là một vấn đề riêng với yêu cầu classifier của `groupingBy`.

## 12. Thứ tự nhóm, thứ tự phần tử và cách chọn Map

Mặc định, `groupingBy(classifier)` không bảo đảm loại Map hay thứ tự lặp các khóa. Nếu cần **thứ tự xuất hiện đầu tiên của các nhóm** từ Stream tuần tự có thứ tự, dùng overload ba tham số với `LinkedHashMap::new`:

```java
Map<GroupKey, List<Order>> insertionOrderGroups = orders.stream()
        .collect(Collectors.groupingBy(
                o -> new GroupKey(o.region(), o.category()),
                LinkedHashMap::new,
                Collectors.toList()
        ));

insertionOrderGroups.keySet().forEach(System.out::println);
// GroupKey[region=Bắc, category=Sách]
// GroupKey[region=Bắc, category=Bút]
// GroupKey[region=Nam, category=Sách]
```

`Collectors.toList()` thu thập các phần tử trong từng nhóm; với Stream nguồn có encounter order và collector thông thường, danh sách của mỗi nhóm giữ thứ tự tương ứng. Nhưng `Collectors.toList()` **không cam kết** khả năng chỉnh sửa hoặc lớp triển khai cụ thể của danh sách kết quả.

Nếu cần **thứ tự sắp xếp theo khóa** thay vì thứ tự xuất hiện, có thể cung cấp `TreeMap` với comparator:

```java
Comparator<GroupKey> byKey = Comparator
        .comparing(GroupKey::region)
        .thenComparing(GroupKey::category);

Map<GroupKey, Long> sortedGroupCounts = orders.stream()
        .collect(Collectors.groupingBy(
                o -> new GroupKey(o.region(), o.category()),
                () -> new TreeMap<>(byKey),
                Collectors.counting()
        ));
```

Ở Map có thứ tự sắp xếp như `TreeMap`, comparator quyết định hai khóa có được coi là cùng một khóa hay không khi kết quả so sánh bằng 0. Cần bảo đảm comparator **phù hợp với định nghĩa bằng nhau của khóa** để không vô tình gộp hoặc tách nhóm khác với `equals`.

Ví dụ comparator chỉ so sánh `region` là **sai** với khóa ghép `(region, category)`: hai loại hàng khác nhau cùng khu vực sẽ bị coi như một khóa trong `TreeMap`.

## 13. Parallel Stream và groupingByConcurrent

Viết:

```java
Map<GroupKey, Long> countsParallel = orders.parallelStream()
        .collect(Collectors.groupingBy(
                o -> new GroupKey(o.region(), o.category()),
                Collectors.counting()
        ));
```

`groupingBy` không phải **concurrent collector**. Với Stream song song, framework có thể tạo nhiều Map kết quả từng phần rồi **kết hợp** nội dung chúng. Kết quả có thể đúng theo hợp đồng, nhưng số lượng nhóm lớn hoặc dữ liệu nhiều có thể khiến thao tác gộp Map trở thành chi phí đáng kể.

Nếu thứ tự không quan trọng và bài toán phù hợp, có thể xem xét `groupingByConcurrent`:

```java
ConcurrentMap<GroupKey, Long> concurrentCounts =
        orders.parallelStream()
                .collect(Collectors.groupingByConcurrent(
                        o -> new GroupKey(o.region(), o.category()),
                        Collectors.counting()
                ));
```

`groupingByConcurrent` trả về `ConcurrentMap` và là collector **concurrent, unordered**. Nó có thể hỗ trợ tích lũy song song theo cách khác với việc gộp nhiều Map. Tuy nhiên:

- Không kỳ vọng thứ tự lặp khóa hay thứ tự phần tử trong nhóm là cố định.
- Downstream collector và đặc điểm dữ liệu quyết định hiệu quả thực tế; dùng concurrent không mặc nhiên nhanh hơn.
- Không dùng classifier sửa nguồn, phụ thuộc vào biến đếm dùng chung hoặc tạo khóa mutable.
- Nếu cần List nhóm có thứ tự ổn định, ưu tiên phương án giữ encounter order và xác nhận tính đúng đắn trước khi tối ưu.

`ConcurrentMap` và `Collectors.counting` trong ví dụ chỉ biểu đạt kết quả tổng hợp; khi ứng dụng có **thread khác cập nhật chính nguồn** trong lúc Stream duyệt, phải xét riêng hợp đồng an toàn của nguồn. `parallelStream()` không biến `ArrayList` thành cấu trúc cho phép sửa đồng thời.

## 14. Độ phức tạp và lựa chọn thiết kế

Phân nhóm theo khóa ghép có các chi phí thực tế:

| Yếu tố | Ảnh hưởng | Cách cân nhắc |
| --- | --- | --- |
| Tạo khóa mới | Thường tạo một object khóa cho mỗi phần tử được phân loại | Đo trên tập dữ liệu lớn; ưu tiên khóa có trường đơn giản và đúng ngữ nghĩa |
| Số nhóm duy nhất | Map cần lưu một entry cho mỗi tổ hợp khác nhau | Số tổ hợp có thể tăng nhanh khi thêm trường khóa |
| Giữ toàn bộ phần tử | `groupingBy` mặc định xây `List<T>` cho mỗi nhóm | Dùng `counting`/`summingLong` nếu chỉ cần số liệu |
| Chuẩn hóa chuỗi | `strip`, `toUpperCase` có thể cấp phát và xử lý nhiều lần | Chuẩn hóa tại tầng nhập liệu hoặc trước khi nhóm khi có thể |
| Stream song song | Có chi phí chia việc và gộp Map | Đo bằng benchmark có dữ liệu và cấu hình thực tế |
| Thứ tự kết quả | Map thường không hứa thứ tự, Set cũng có thể unordered | Chọn `LinkedHashMap` hoặc `TreeMap` khi thực sự cần |
| Sai số và tràn số | Các phép tổng `long` có thể tràn; `double` có sai số | Chọn kiểu số phù hợp, quy tắc làm tròn và kiểm tra overflow |

Với số lượng phần tử `n` và số tổ hợp nhóm `g`, việc phân loại và đưa vào hash-based Map **thường** có chi phí kỳ vọng gần `O(n)` khi hash phân bố tốt; lưu toàn bộ phần tử theo nhóm cần bộ nhớ tăng theo `n`, còn chỉ đếm nhóm cần bộ nhớ tăng theo `g`. Đây không phải cam kết thời gian chạy trong mọi tình huống: chi phí tính hash, so sánh, nguồn dữ liệu và việc chạy song song cũng tham gia.

Các pipeline Stream là lazy cho tới khi terminal operation `collect` chạy. Sau khi `collect` kết thúc, Stream không được tiêu thụ lại. Nếu cần hai dạng báo cáo từ cùng nguồn, tạo hai Stream mới hoặc cân nhắc collector tổng hợp để gom trong một lượt duyệt.

## 15. Ví dụ hoàn chỉnh: báo cáo đơn hàng theo tháng và khu vực

Giả sử mỗi đơn chứa mã, khu vực, tháng báo cáo, số lượng và trạng thái đã hoàn tất. Cần tổng hợp **số đơn và tổng số lượng** theo **(khu vực, tháng)**. Dùng khóa ghép để mỗi tổ hợp là một nhóm độc lập.

Ví dụ Java 17+ có thể chạy độc lập:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.stream.Collectors;

public class CompositeGroupingDemo {
    record Order(
            String id,
            String region,
            int month,
            int quantity,
            boolean completed
    ) {}

    record GroupKey(String region, int month) {}
    record Summary(long orderCount, long totalQuantity) {}

    static String normalizeRegion(String region) {
        return region.strip().toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("O01", " Bắc ", 1, 3, true),
                new Order("O02", "Nam", 1, 7, true),
                new Order("O03", "BẮC", 1, 2, true),
                new Order("O04", "Nam", 2, 5, true),
                new Order("O05", "Bắc", 1, 99, false),
                new Order("O06", "Bắc", 2, 4, true)
        );

        Map<GroupKey, Summary> report = orders.stream()
                .filter(Order::completed)
                .collect(Collectors.groupingBy(
                        order -> new GroupKey(
                                normalizeRegion(order.region()),
                                order.month()
                        ),
                        LinkedHashMap::new,
                        Collectors.collectingAndThen(
                                Collectors.summarizingLong(Order::quantity),
                                stats -> new Summary(
                                        stats.getCount(),
                                        stats.getSum()
                                )
                        )
                ));

        report.forEach((key, summary) ->
                System.out.printf(
                        "%s | tháng %d | số đơn=%d | số lượng=%d%n",
                        key.region(),
                        key.month(),
                        summary.orderCount(),
                        summary.totalQuantity()
                )
        );

        // BẮC | tháng 1 | số đơn=2 | số lượng=5
        // NAM | tháng 1 | số đơn=1 | số lượng=7
        // NAM | tháng 2 | số đơn=1 | số lượng=5
        // BẮC | tháng 2 | số đơn=1 | số lượng=4

        System.out.println(report.get(new GroupKey("BẮC", 1)));
        // Summary[orderCount=2, totalQuantity=5]
    }
}
```

Phân tích:

1. `filter(Order::completed)` loại đơn chưa hoàn tất trước khi nhóm.
2. `normalizeRegion` giúp `" Bắc "` và `"BẮC"` tạo cùng một trường khóa `"BẮC"`.
3. `GroupKey` dùng `record` nên equality/hash code tính theo khu vực **và** tháng.
4. `groupingBy` phân loại và đưa phần tử cùng khóa vào chung một bộ tích lũy.
5. `summarizingLong` tính số lượng đơn và tổng số lượng; `collectingAndThen` chốt kết quả thành `Summary` bất biến.
6. `LinkedHashMap::new` giữ thứ tự xuất hiện đầu tiên của các khóa trong Stream tuần tự.
7. Câu lệnh `report.get(new GroupKey("BẮC", 1))` tìm đúng nhóm dù object key vừa tạo là instance khác với key đã được lưu.

Ví dụ giả định `region` không phải `null` và `month` hợp lệ từ 1 đến 12. Nếu đầu vào không bảo đảm các điều kiện đó, hãy validate hoặc đưa ra quy ước rõ ràng trước khi tạo GroupKey. Với báo cáo tài chính, chọn kiểu dữ liệu và cách cộng phù hợp đơn vị tiền, sai số và yêu cầu nghiệp vụ.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Các nhóm bị gộp ngoài ý muốn | Chỉ classifier theo một trong hai trường | Tạo `GroupKey` gồm toàn bộ thành phần danh tính nhóm |
| Cùng nội dung nhưng thành nhiều nhóm | Khóa không override `equals`/`hashCode` | Dùng `record` hoặc lớp giá trị bất biến đúng hợp đồng |
| Nối chuỗi làm mất phân biệt tổ hợp | Chuỗi thành phần chứa dấu phân cách hoặc quy ước không thống nhất | Dùng khóa ghép có kiểu rõ ràng |
| Dùng mảng làm khóa và không tra cứu được | Mảng so sánh theo tham chiếu, không theo nội dung | Dùng record chứa trường bất biến, không dùng array trực tiếp |
| `map.get(key)` bất ngờ trả `null` sau khi sửa key | Thành phần khóa mutable bị thay đổi | Không sửa giá trị tham gia `equals`/`hashCode` của khóa đã lưu |
| `NullPointerException` trong `groupingBy` | Classifier trả về nguyên đối tượng khóa `null` hoặc thao tác chuẩn hóa trên null | Chuẩn hóa/kiểm tra trước, tạo khóa không-null |
| Nhóm bị tách do chữ hoa/chữ thường hoặc khoảng trắng | Dữ liệu chưa chuẩn hóa theo quy tắc nghiệp vụ | Xây dựng hàm chuẩn hóa rõ nghĩa |
| Map kết quả in thứ tự khác mong muốn | `groupingBy` không bảo đảm thứ tự Map | Dùng `LinkedHashMap` hoặc `TreeMap` với comparator phù hợp |
| `TreeMap` gộp hai nhóm khác category | Comparator chỉ so sánh region, trả 0 cho hai khóa khác nhau | So sánh đủ mọi trường xác định danh tính |
| Kết quả có nhiều List lớn gây áp lực bộ nhớ | `groupingBy` mặc định giữ toàn bộ phần tử | Dùng downstream `counting`, `summingLong`, `summarizingLong` |
| `parallelStream` chậm hơn tuần tự | Chi phí tạo/gộp Map và số nhóm quá lớn | Đo hiệu năng thực tế, chỉ chọn concurrent collector khi phù hợp |

## 17. Bài tập và lời giải tham khảo

Cho dữ liệu chấm công:

```java
record Worklog(String team, int year, int hours, boolean approved) {}

List<Worklog> logs = List.of(
        new Worklog("Backend", 2025, 4, true),
        new Worklog("Backend", 2025, 6, true),
        new Worklog("Frontend", 2025, 5, true),
        new Worklog("Backend", 2026, 3, true),
        new Worklog("Backend", 2025, 10, false)
);
```

**Yêu cầu:**

1. Tạo `record WorklogKey(String team, int year)` làm khóa ghép.
2. Bỏ các worklog chưa duyệt, phân nhóm theo `(team, year)`.
3. Với mỗi nhóm, tính số worklog đã duyệt và tổng số giờ.
4. Tra cứu tổng giờ của nhóm `("Backend", 2025)` bằng một instance khóa mới.
5. Thay dữ liệu nhóm bằng `Map<String, Map<Integer, ...>>` và so sánh hai cách biểu diễn.
6. Nếu `team` có dạng `" backend "` hoặc `"BACKEND"`, thêm chính sách chuẩn hóa để chúng thuộc một nhóm khi phù hợp với nghiệp vụ.

**Lời giải mẫu:**

```java
record WorklogKey(String team, int year) {}
record WorklogSummary(long count, long totalHours) {}

Map<WorklogKey, WorklogSummary> report = logs.stream()
        .filter(Worklog::approved)
        .collect(Collectors.groupingBy(
                log -> new WorklogKey(log.team(), log.year()),
                Collectors.collectingAndThen(
                        Collectors.summarizingLong(Worklog::hours),
                        stats -> new WorklogSummary(
                                stats.getCount(),
                                stats.getSum()
                        )
                )
        ));

System.out.println(report.get(
        new WorklogKey("Backend", 2025)
));
// WorklogSummary[count=2, totalHours=10]

Map<String, Map<Integer, Long>> nestedHours = logs.stream()
        .filter(Worklog::approved)
        .collect(Collectors.groupingBy(
                Worklog::team,
                Collectors.groupingBy(
                        Worklog::year,
                        Collectors.summingLong(Worklog::hours)
                )
        ));

System.out.println(nestedHours.get("Backend").get(2025)); // 10
```

Với yêu cầu 6, có thể dùng `log.team().strip().toUpperCase(Locale.ROOT)` ngay trong classifier và phải dùng **cùng giá trị chuẩn hóa khi tra cứu**. Trong ứng dụng lớn, tốt hơn nên chuẩn hóa/validate ở ranh giới nhập liệu hoặc trong một hàm dựng khóa được dùng nhất quán giữa các nơi.

**Thử nghiệm mở rộng:** Nếu chuyển nguồn sang `parallelStream()`, bản ghi có giá trị bất biến và downstream collector đúng hợp đồng vẫn có thể tạo số liệu hợp lệ. Tuy nhiên, đừng khẳng định thứ tự lặp khóa cố định. Hãy so sánh nội dung Map theo từng khóa và đo hiệu năng thay vì so chuỗi `toString` của toàn Map.

## Ghi nhớ

Khi phân nhóm theo nhiều thuộc tính, hãy tạo một **khóa ghép có ngữ nghĩa giá trị** thay vì ghép chuỗi hoặc dùng đối tượng mutable. `record GroupKey(a, b)` mang theo những trường định danh, tự cung cấp `equals` và `hashCode`, giúp `Collectors.groupingBy` gom đúng các phần tử có cùng tổ hợp khóa.

Sử dụng downstream collector như `counting`, `summingLong`, `mapping` hoặc `summarizingLong` nếu báo cáo chỉ cần số liệu thay vì toàn bộ danh sách. Chuẩn hóa và kiểm tra `null` trước khi phân nhóm; chọn `LinkedHashMap`/`TreeMap` khi yêu cầu thứ tự rõ ràng. Với Stream song song, giữ classifier stateless và không can thiệp nguồn, đánh giá chi phí kết hợp Map và chỉ dùng `groupingByConcurrent` khi ngữ nghĩa unordered phù hợp.
