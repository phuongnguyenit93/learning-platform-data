# Thiết kế khóa nhóm ổn định và xử lý khóa thiếu trong Java Stream

## Mục tiêu

Khi nhóm dữ liệu với `Collectors.groupingBy(...)`, kết quả không chỉ phụ thuộc vào phép đếm hoặc danh sách phần tử: nó phụ thuộc trước hết vào **khóa nhóm** do classifier tạo ra. Hai bản ghi đáng lẽ thuộc cùng nhóm sẽ bị tách ra nếu khóa không được chuẩn hóa nhất quán; hai nhóm khác nhau có thể bị gộp nhầm nếu dùng một giá trị thay thế gây xung đột. Đặc biệt, **classifier của `groupingBy` không được trả `null`**. Điều này vẫn đúng ngay cả khi loại Map bạn muốn dùng có hỗ trợ khóa null.

Bài học tập trung vào ba nguyên tắc:

1. **Khóa có ý nghĩa ổn định:** biểu diễn đúng tiêu chí phân nhóm, có `equals()`/`hashCode()` nhất quán, không thay đổi trong lúc nằm trong Map.
2. **Khóa được chuẩn hóa theo chính sách rõ ràng:** xử lý hoa/thường, khoảng trắng, mã định danh và thành phần tổ hợp một cách có chủ đích.
3. **Thiếu khóa được biểu diễn rõ:** dùng `Optional.empty()`, một loại trạng thái riêng hoặc phương án dữ liệu phù hợp, thay vì trả `null` trực tiếp cho `groupingBy`.

Sau bài này, bạn có thể thiết kế khóa nhóm đơn/tổ hợp, phân biệt bản ghi không có khóa với chuỗi khóa hợp lệ, đọc kết quả `Map<K,List<T>>`, tổng hợp dữ liệu bằng downstream collector, chọn `partitioningBy` khi chỉ cần hai nhóm và tránh các lỗi về mutable key, thứ tự, comparator và xử lý đồng thời.

## 1. groupingBy sử dụng classifier như thế nào?

Chữ ký dạng đơn giản của `Collectors.groupingBy`:

```java
static <T, K> Collector<T, ?, Map<K, List<T>>> groupingBy(
        Function<? super T, ? extends K> classifier);
```

Đây là **chữ ký API rút gọn**, không phải phương thức cần tự viết trong dự án. `T` là kiểu phần tử đầu vào, `K` là kiểu khóa do classifier trả về. Trong một pipeline:

```java
Map<String, List<String>> byFirstLetter =
        Stream.of("An", "Anh", "Bình")
                .collect(Collectors.groupingBy(
                        name -> name.substring(0, 1)
                ));
```

`name -> name.substring(0, 1)` là classifier. Hai tên bắt đầu bằng `A` thuộc nhóm `"A"`; tên `"Bình"` thuộc nhóm `"B"`. Giá trị Map là danh sách các phần tử gốc vì overload này dùng downstream collector tương đương `toList()`.

Điểm cần hiểu:

- Nếu hai phần tử tạo các khóa **bằng nhau theo hợp đồng của Map**, chúng được đưa vào cùng một nhóm.
- Nếu tạo các khóa khác nhau, chúng được đưa vào hai nhóm, dù người dùng có thể nhìn hai chuỗi như “cùng nghĩa”.
- Thứ tự lặp qua Map **không được bảo đảm** ở overload mặc định; muốn chọn Map cụ thể, dùng overload có `mapFactory`.
- `groupingBy` không làm sạch dữ liệu đầu vào hoặc tự quyết định cách chuẩn hóa chữ.
- `groupingBy` không cho classifier trả `null`: với một phần tử tạo khóa null, phép thu thập phát sinh `NullPointerException`.

Ví dụ quan trọng:

```java
record Sale(String category, int units) {}

List<Sale> sales = List.of(
        new Sale("Food", 2),
        new Sale("food", 3),
        new Sale(" Food ", 4)
);

Map<String, List<Sale>> groups = sales.stream()
        .collect(Collectors.groupingBy(Sale::category));
```

Đây là **đoạn minh họa** cần import `List`, `Map`, `Collectors`. Map sẽ có ba khóa String khác nhau: `"Food"`, `"food"` và `" Food "`. Mặc định `String.equals()` phân biệt chữ hoa/chữ thường và khoảng trắng; Java không biết yêu cầu nghiệp vụ có coi ba chuỗi ấy tương đương hay không.

## 2. Thế nào là một khóa nhóm ổn định?

Một khóa nhóm tốt cần đáp ứng cả **đúng nghĩa** và **đúng hợp đồng kiểu dữ liệu**.

| Thuộc tính | Ý nghĩa thực tế | Khi vi phạm |
| --- | --- | --- |
| Biểu diễn đúng tiêu chí | Hai bản ghi cùng nhóm tạo khóa bằng nhau | Nhóm bị chia nhỏ hoặc gộp nhầm |
| `equals()` đúng | Hai khóa cùng giá trị nghiệp vụ so sánh bằng nhau | Map có các khóa “trông giống nhau” |
| `hashCode()` nhất quán | Khóa bằng nhau có cùng mã băm | `HashMap`/`LinkedHashMap`/`groupingBy` có thể tìm sai nhóm |
| Không thay đổi khi nằm trong Map | Những trường tham gia so sánh giữ nguyên | `get`, `containsKey` có thể không tìm lại được khóa |
| Xử lý trạng thái thiếu minh bạch | Thiếu dữ liệu không gây NPE hoặc đụng khóa hợp lệ | Mất bản ghi hoặc kết quả sai |
| Chuẩn hóa theo chính sách | Case, dấu cách, định dạng mã được xử lý nhất quán | Dữ liệu phân mảnh hoặc mất phân biệt cần thiết |

### 2.1. String là khóa tốt nếu đã chọn rõ quy tắc so sánh

`String` là kiểu bất biến và đã triển khai `equals`/`hashCode` theo nội dung. Nếu dữ liệu là **mã phân loại** không phân biệt hoa/thường và không coi khoảng trắng đầu/cuối là quan trọng, có thể chuẩn hóa:

```java
String normalized = raw.strip().toLowerCase(Locale.ROOT);
```

`strip()` (Java 11+) xử lý khoảng trắng theo định nghĩa Unicode của Java; `toLowerCase(Locale.ROOT)` tránh phụ thuộc locale mặc định của máy khi chuẩn hóa **mã định danh kỹ thuật**. Cần import `java.util.Locale`.

Tuy nhiên, **đừng chuẩn hóa mọi trường dữ liệu theo cùng cách**. Mã quốc gia, SKU, địa chỉ email, mã sản phẩm, tên riêng ngôn ngữ tự nhiên có hợp đồng so sánh khác nhau. Việc lower-case hoặc bỏ dấu có thể làm gộp hai thực thể vốn phải phân biệt. Hãy căn cứ tài liệu domain và quy định dữ liệu.

### 2.2. Khóa object mutable là lựa chọn nguy hiểm

Giả sử dùng một class có trường `category` có thể sửa, và `equals`/`hashCode` dựa trên trường đó. Sau khi object được thêm làm key của `HashMap`, nếu đổi `category`, mã băm có thể thay đổi. Khi đó `map.get(key)` hoặc `map.containsKey(key)` có thể thất bại, dù chính tham chiếu object vẫn tồn tại ở một bucket cũ.

Không cần nhiều thread mới phát sinh lỗi này; chỉ một lệnh cập nhật field sai thời điểm là đủ. **Không sửa những trường tham gia `equals`/`hashCode` của key đã được lưu trong Map**.

Nếu phải dùng một entity mutable làm dữ liệu, hãy **trích khóa bất biến** như String ID đã chuẩn hóa, enum hoặc một record chỉ chứa các thành phần bất biến. Tách identity của entity ra khỏi dữ liệu trình bày hoặc dữ liệu có thể thay đổi.

## 3. record làm khóa tổ hợp ổn định

Giả sử cần nhóm giao dịch theo **khu vực** và **danh mục**. Chỉ nhóm theo khu vực sẽ gộp đồ ăn với sách; chỉ nhóm theo danh mục sẽ gộp các khu vực khác nhau. Khóa phải mang đủ hai thành phần.

Java record là lựa chọn gọn khi dữ liệu khóa mang tính giá trị:

```java
record GroupKey(String region, String category) {}
```

Compiler tự tạo constructor, accessor, `equals`, `hashCode` và `toString` dựa trên các thành phần record. Hai record có cùng nội dung ở cả hai thành phần sẽ so sánh bằng nhau theo ngữ nghĩa giá trị. Ví dụ:

```java
GroupKey a = new GroupKey("north", "food");
GroupKey b = new GroupKey("north", "food");
System.out.println(a.equals(b)); // true
```

Đây là hai câu lệnh minh họa bên trong phương thức có `GroupKey` đã được định nghĩa. Dù `a` và `b` là hai object riêng, `equals` theo giá trị của record trả true.

**Record bất biến ở mức tham chiếu thành phần, không tự deep-immutable.** Nếu một record chứa `List` mutable và `equals/hashCode` phụ thuộc nội dung List, việc sửa List sau khi dùng record làm key vẫn có thể phá tính ổn định. Với khóa nhóm, ưu tiên thành phần đã bất biến như String, enum, số nguyên, `Optional<String>` hoặc record bất biến lồng nhau.

### 3.1. Giữ nguyên cả ý nghĩa dữ liệu thiếu

Một record có thể chứa thành phần null; bản thân `new GroupKey(null, "food")` là một object key **khác null**, nên không phạm trực tiếp điều kiện “classifier không được trả null”. Tuy nhiên, nếu nhiều chỗ trong code tự xử lý null theo cách khác nhau, logic so sánh và trình bày sẽ khó bảo trì.

Có thể thiết kế rõ hơn:

```java
record GroupKey(
        Optional<String> region,
        Optional<String> category
) {}
```

Mỗi thành phần `Optional.empty()` nghĩa là **chưa có dữ liệu hợp lệ theo chính sách đã chọn**. Bản thân `GroupKey` luôn là một object khác null. Trong bài minh họa này, String và Optional giữ giá trị bất biến nên khóa phù hợp để lưu vào Map.

Dùng Optional trong thành phần record ở đây là một lựa chọn mô hình hóa có chủ đích cho bài học. Với mô hình domain lớn hoặc dữ liệu cần serialize, có thể chọn enum trạng thái thiếu, một kiểu tổng (*sum type*) hoặc record khác có hợp đồng rõ; không coi Optional trong mọi field là quy tắc bắt buộc.

## 4. Xử lý khóa thiếu: tránh trả null từ classifier

### 4.1. Vì sao groupingBy với key null gây lỗi?

Với dữ liệu:

```java
record Sale(String category, int units) {}

List<Sale> sales = List.of(
        new Sale("food", 2),
        new Sale(null, 1)
);

Map<String, List<Sale>> grouped =
        sales.stream().collect(
                Collectors.groupingBy(Sale::category));
```

Khi gặp bản ghi có `category() == null`, classifier trả null và `Collectors.groupingBy` ném `NullPointerException`. Điều này vẫn đúng với overload dùng `HashMap::new` hay `LinkedHashMap::new`, mặc dù hai Map đó có thể chứa khóa null trong những thao tác khác.

**Phải phân biệt:** “`HashMap` cho phép key null” không đồng nghĩa “`groupingBy` cho phép classifier trả null”. `groupingByConcurrent` cũng không phải giải pháp để nhóm trực tiếp bằng classifier null.

### 4.2. Phương án A — sentinel có tên rõ, khi chắc chắn không đụng dữ liệu hợp lệ

```java
String key = rawCategory == null
        ? "__MISSING_CATEGORY__"
        : rawCategory;
```

Đây là một cách biểu diễn trạng thái thiếu bằng một chuỗi đặc biệt. Nó có thể đơn giản, nhưng có **nguy cơ đụng khóa**: nếu dữ liệu hợp lệ thực sự chứa chuỗi `"__MISSING_CATEGORY__"`, các bản ghi có giá trị thật và bản ghi thiếu sẽ bị gộp vào nhau.

Chỉ dùng sentinel dạng String khi **domain bảo đảm chắc chắn** chuỗi này không thể là giá trị hợp lệ, và toàn hệ thống dùng chung quy tắc. Với báo cáo liên hệ thống, khả năng xung đột tăng lên khi danh mục mới được bổ sung.

### 4.3. Phương án B — Optional như một phần của kiểu khóa

```java
Map<Optional<String>, List<Sale>> grouped =
        sales.stream().collect(Collectors.groupingBy(
                sale -> Optional.ofNullable(sale.category())
        ));
```

Khi category null, classifier vẫn trả một object `Optional.empty()` khác null; khi có category, trả `Optional.of(category)`. Nhờ vậy không đụng với giá trị String hợp lệ dù nội dung bằng chuỗi `"unknown"` hoặc `"__MISSING_CATEGORY__"`.

Nếu còn cần coi chuỗi trống/blank là thiếu, hãy dùng hàm chuẩn hóa trả `Optional<String>` theo chính sách:

```java
static Optional<String> normalize(String raw) {
    if (raw == null) return Optional.empty();

    String normalized = raw.strip().toLowerCase(Locale.ROOT);
    return normalized.isEmpty()
            ? Optional.empty()
            : Optional.of(normalized);
}
```

Đây là phương thức độc lập cần đặt trong class có import `Optional` và `Locale`. Chú ý: quyết định coi chuỗi `"  "` là thiếu là **chính sách nghiệp vụ** của ví dụ này. Nếu hệ thống cần phân biệt “không được cung cấp” và “được cung cấp nhưng rỗng”, dùng các trạng thái riêng thay vì gộp chung thành Optional.empty().

### 4.4. Phương án C — một kiểu trạng thái riêng

Nếu code cần phân biệt rõ nhiều loại thiếu:

- Không có field trong nguồn.
- Có field nhưng toàn khoảng trắng.
- Có field không vượt qua validation.
- Giá trị thuộc nhóm `"unknown"` thật sự.

Một wrapper hoặc kiểu trạng thái riêng sẽ biểu diễn chính xác hơn một String sentinel. Trong Java 17, có thể dùng `sealed interface` cùng record triển khai để biểu đạt các trạng thái, hoặc dùng record có hai trường `status` và `value`. Điều quan trọng là **classifier luôn trả một key object không null** với `equals/hashCode` phù hợp.

Đừng bỏ mất khác biệt nghiệp vụ chỉ để tránh `NullPointerException`; chính sách thiếu dữ liệu cần được thiết kế trước khi code grouping.

### 4.5. Phương án D — loại bản ghi thiếu, khi thật sự được phép

```java
Map<String, List<Sale>> grouped = sales.stream()
        .filter(sale -> sale.category() != null)
        .collect(Collectors.groupingBy(Sale::category));
```

Đoạn minh họa này bỏ qua bản ghi thiếu category. Nó có thể đúng cho báo cáo chỉ thống kê dữ liệu hợp lệ, nhưng **không đúng** cho báo cáo phải bảo toàn tổng số bản ghi. Nếu bỏ bản ghi, phải nêu rõ số lượng bị loại hoặc chuyển sang luồng xử lý lỗi phù hợp.

## 5. Chuẩn hóa khóa theo một điểm duy nhất

Một lỗi phổ biến là chỉ chuẩn hóa ở chỗ kiểm tra mà không chuẩn hóa ở chỗ nhóm:

```java
String normalized = input.trim().toLowerCase();
// Nhưng classifier vẫn trả rawCategory chưa chuẩn hóa.
```

Nếu nhiều module tự xử lý khác nhau, sự khác biệt `"Food"` và `" food "` dễ tái xuất hiện. Thay vì lặp quy tắc, tạo một hàm chuẩn hóa dùng lại:

```java
static Optional<String> normalize(String raw) {
    if (raw == null) return Optional.empty();
    String key = raw.strip().toLowerCase(Locale.ROOT);
    return key.isEmpty() ? Optional.empty() : Optional.of(key);
}
```

Sau đó luôn xây khóa thông qua cùng một hàm:

```java
static GroupKey keyOf(Sale sale) {
    return new GroupKey(
            normalize(sale.region()),
            normalize(sale.category())
    );
}
```

Đây là các phương thức của chương trình hoàn chỉnh bên dưới. `GroupKey` là một record có hai `Optional<String>`.

**Khi chuẩn hóa, hãy xác định:**

1. Có phân biệt chữ hoa/thường không? Nếu có, **không lower-case**.
2. Có được loại khoảng trắng đầu/cuối không? Với mã kỹ thuật thường có thể; với chuỗi văn bản tùy yêu cầu.
3. Có cần Unicode normalization (NFC/NFKC) không? Các lựa chọn có thể làm đồng nhất những chuỗi khác nhau; phải theo định nghĩa dữ liệu.
4. Có được gộp null và blank không? Nếu cần phân biệt, dùng hai trạng thái khác nhau.
5. Có cần giữ giá trị gốc để hiển thị hoặc truy vết không? Nếu có, giữ raw value trong bản ghi gốc, chỉ chuẩn hóa **khóa để nhóm**.

`Locale.ROOT` hợp lý khi chuẩn hóa identifier không phụ thuộc ngôn ngữ; với tên riêng và quy tắc so sánh ngôn ngữ tự nhiên có thể cần một chính sách khác. Đừng tự tiện bỏ dấu tiếng Việt hoặc chuyển các ký tự có dấu thành ký tự không dấu chỉ để giảm số nhóm.

## 6. Chương trình Java 17 đầy đủ

Chương trình sau dùng dữ liệu bán hàng có trường khu vực/danh mục khác cách viết và có dữ liệu thiếu. Nó chứng minh bốn điểm:

- Hai biến thể `"North"` và `" north "` tạo cùng một khóa nhóm.
- Một `record GroupKey` bất biến chứa `Optional<String>` để phân biệt thành phần không có dữ liệu.
- `groupingBy` có thể kết hợp với `mapping`, `summingInt`, `counting` và `partitioningBy` để thu nhiều loại kết quả.
- Classifier trả `null` gây `NullPointerException`, nhưng cách chuẩn hóa trả key object hợp lệ tránh được lỗi.

Tạo file **`StableGroupingKeyDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;

public class StableGroupingKeyDemo {
    record Sale(String region, String category, String product, int units) {}

    record GroupKey(Optional<String> region,
                    Optional<String> category) {}

    static Optional<String> normalize(String raw) {
        if (raw == null) return Optional.empty();
        String normalized = raw.strip().toLowerCase(Locale.ROOT);
        return normalized.isEmpty()
                ? Optional.empty() : Optional.of(normalized);
    }

    static GroupKey keyOf(Sale sale) {
        return new GroupKey(normalize(sale.region()),
                            normalize(sale.category()));
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("North", "Food", "Apples", 2),
                new Sale(" north ", "food", "Pears", 3),
                new Sale("South", null, "Tea", 1),
                new Sale(null, "Books", "Guide", 4),
                new Sale(" ", "  ", "Missing", 5),
                new Sale("South", "Food", "Cake", 2)
        );

        Map<GroupKey, List<String>> grouped = sales.stream().collect(
                Collectors.groupingBy(
                        StableGroupingKeyDemo::keyOf,
                        LinkedHashMap::new,
                        Collectors.mapping(
                                Sale::product, Collectors.toList())
                )
        );
        System.out.println("Groups: " + grouped);

        Map<GroupKey, Integer> units = sales.stream().collect(
                Collectors.groupingBy(
                        StableGroupingKeyDemo::keyOf,
                        LinkedHashMap::new,
                        Collectors.summingInt(Sale::units)
                )
        );
        System.out.println("Units: " + units);

        Map<Optional<String>, Long> counts = sales.stream().collect(
                Collectors.groupingBy(
                        s -> normalize(s.category()),
                        LinkedHashMap::new,
                        Collectors.counting()
                )
        );
        System.out.println("Category counts: " + counts);

        Map<Boolean, List<String>> partition = sales.stream().collect(
                Collectors.partitioningBy(
                        s -> normalize(s.category()).isEmpty(),
                        Collectors.mapping(
                                Sale::product, Collectors.toList())
                )
        );
        System.out.println("Missing category: " + partition.get(true));
        System.out.println("Present category: " + partition.get(false));

        try {
            sales.stream().collect(
                    Collectors.groupingBy(Sale::category)
            );
        } catch (NullPointerException ex) {
            System.out.println("Raw nullable key: NullPointerException");
        }

        System.out.println("Key equals: " + keyOf(sales.get(0))
                .equals(keyOf(sales.get(1))));
    }
}
```

Biên dịch/chạy bằng **JDK 17 trở lên**:

```bash
javac StableGroupingKeyDemo.java
java StableGroupingKeyDemo
```

**Stdout chính xác:**

```text
Groups: {GroupKey[region=Optional[north], category=Optional[food]]=[Apples, Pears], GroupKey[region=Optional[south], category=Optional.empty]=[Tea], GroupKey[region=Optional.empty, category=Optional[books]]=[Guide], GroupKey[region=Optional.empty, category=Optional.empty]=[Missing], GroupKey[region=Optional[south], category=Optional[food]]=[Cake]}
Units: {GroupKey[region=Optional[north], category=Optional[food]]=5, GroupKey[region=Optional[south], category=Optional.empty]=1, GroupKey[region=Optional.empty, category=Optional[books]]=4, GroupKey[region=Optional.empty, category=Optional.empty]=5, GroupKey[region=Optional[south], category=Optional[food]]=2}
Category counts: {Optional[food]=3, Optional.empty=2, Optional[books]=1}
Missing category: [Tea, Missing]
Present category: [Apples, Pears, Guide, Cake]
Raw nullable key: NullPointerException
Key equals: true
```

### 6.1. Vì sao kết quả đúng?

**Nhóm 1:** `Sale("North","Food","Apples",2)` và `Sale(" north ","food","Pears",3)` tạo cùng `GroupKey(Optional[north], Optional[food])`. `strip` bỏ khoảng trắng, `toLowerCase(Locale.ROOT)` thống nhất chữ thường. Danh sách nhóm là `[Apples, Pears]` và tổng `units` là `2 + 3 = 5`.

**Nhóm 2:** `Sale("South",null,"Tea",1)` có category `Optional.empty()`, nhưng region `Optional[south]`. Đây là khóa tổ hợp hợp lệ và khác nhóm `South/Food`.

**Nhóm 3:** `Sale(null,"Books","Guide",4)` có region thiếu nhưng category `Optional[books]`.

**Nhóm 4:** `Sale(" ","  ","Missing",5)` có cả hai chuỗi blank. Theo chính sách của `normalize`, cả hai đều thành `Optional.empty()`; bản ghi vẫn được bảo toàn trong nhóm riêng.

**Nhóm 5:** `Sale("South","Food","Cake",2)` có khóa `South/Food`, khác nhóm `North/Food` nên không bị gộp nhầm.

**Đếm category:** nhóm `Optional[food]` có ba bản ghi (Apples, Pears, Cake), `Optional.empty` có hai bản ghi (Tea, Missing), và `Optional[books]` có một bản ghi (Guide). `Collectors.counting()` trả kiểu `Long`.

**Phân vùng:** `partitioningBy(predicate)` tạo hai nhóm boolean: `true` với bản ghi có category thiếu và `false` với category có giá trị. Vì predicate chỉ kiểm tra thiếu category, nhóm `true` gồm Tea và Missing; nhóm `false` gồm Apples, Pears, Guide, Cake.

**NPE:** gọi `groupingBy(Sale::category)` trực tiếp với dữ liệu có category null vi phạm hợp đồng non-null classifier. Chương trình bắt `NullPointerException` nhằm minh họa vị trí lỗi, không phải khuyến nghị dùng exception như luồng nhóm dữ liệu thông thường.

**equals:** hai bản ghi đầu tiên có cùng khóa chuẩn hóa, vì thế `keyOf(sales.get(0)).equals(keyOf(sales.get(1)))` trả `true`.

### 6.2. Vì sao kết quả Map có thứ tự?

Chương trình dùng:

```java
Collectors.groupingBy(
        StableGroupingKeyDemo::keyOf,
        LinkedHashMap::new,
        downstream
)
```

`LinkedHashMap::new` chọn Map giữ thứ tự chèn khóa. Trong chương trình **tuần tự** với nguồn `List.of` có encounter order, nhóm xuất hiện theo lần đầu gặp khóa nên có đầu ra xác định. Không dựa vào thứ tự in của overload mặc định `groupingBy(classifier)`, vì nó không cam kết loại Map.

Với parallel stream, có thể có các bước kết hợp Map từng phần; đừng xem thứ tự log của các callback hoặc thời điểm tạo key như một hợp đồng ổn định giữa các lần chạy.

## 7. Chọn downstream collector để bảo toàn ý nghĩa nhóm

Classifier trả khóa; **downstream collector** quyết định dữ liệu giữ cho mỗi khóa. Không phải lúc nào cũng cần `List<T>` chứa toàn bộ bản ghi.

### 7.1. Đếm số bản ghi mỗi nhóm

```java
Map<GroupKey, Long> counts = sales.stream().collect(
        Collectors.groupingBy(
                StableGroupingKeyDemo::keyOf,
                Collectors.counting()
        )
);
```

Kết quả mỗi khóa là số lượng bản ghi kiểu `Long`, không phải danh sách `Sale`. Nếu chỉ cần đếm, không cần lưu toàn bộ bản ghi rồi gọi `list.size()`.

### 7.2. Cộng số lượng theo nhóm

```java
Map<GroupKey, Integer> totals = sales.stream().collect(
        Collectors.groupingBy(
                StableGroupingKeyDemo::keyOf,
                Collectors.summingInt(Sale::units)
        )
);
```

Downstream `summingInt` cộng `units`. Nếu tổng có thể vượt phạm vi `int`, cân nhắc `summingLong(s -> s.units())` hoặc cơ chế kiểm soát tràn theo dữ liệu. `Collectors` không thay thế việc chọn kiểu số đúng nghiệp vụ.

### 7.3. Chỉ lưu tên sản phẩm

```java
Map<GroupKey, List<String>> names = sales.stream().collect(
        Collectors.groupingBy(
                StableGroupingKeyDemo::keyOf,
                Collectors.mapping(
                        Sale::product,
                        Collectors.toList()
                )
        )
);
```

Kết quả là `Map<GroupKey,List<String>>`. `Collectors.toList()` không bảo đảm khả năng sửa được của List; nếu cần collection cụ thể, dùng `Collectors.toCollection(ArrayList::new)` làm downstream.

### 7.4. Lấy danh sách không trùng

```java
Map<GroupKey, Set<String>> uniqueNames = sales.stream().collect(
        Collectors.groupingBy(
                StableGroupingKeyDemo::keyOf,
                Collectors.mapping(
                        Sale::product,
                        Collectors.toSet()
                )
        )
);
```

Đây là mã minh họa cần import `Set`. `toSet()` không bảo đảm thứ tự lặp; muốn giữ thứ tự xuất hiện đầu tiên trong pipeline có thứ tự, dùng `toCollection(LinkedHashSet::new)`.

**Quan trọng:** key normalization và downstream collection là **hai quyết định độc lập**. Chuẩn hóa key để ghép đúng nhóm không đồng nghĩa tự động chuẩn hóa hoặc thay đổi nội dung của từng Sale.

## 8. groupingBy hay partitioningBy?

`Collectors.partitioningBy(predicate)` phù hợp khi yêu cầu chia thành **hai phân vùng** theo điều kiện boolean, ví dụ “danh mục bị thiếu” và “danh mục đã có”.

```java
Map<Boolean, List<Sale>> partitions = sales.stream()
        .collect(Collectors.partitioningBy(
                s -> normalize(s.category()).isEmpty()
        ));
```

Kết quả có hai khóa boolean `true` và `false`. `partitioningBy` có hợp đồng hai phân vùng; ngay cả khi một phía không có phần tử, phía đó vẫn là một phân vùng với kết quả downstream phù hợp. Đây là một khác biệt với `groupingBy(s -> booleanCondition)`, vốn thường chỉ tạo khóa có xuất hiện trong nguồn.

Chọn:

- **`partitioningBy`** khi bài toán thật sự có đúng hai trạng thái theo một predicate.
- **`groupingBy`** khi cần nhiều giá trị khóa, khóa tổ hợp hoặc nhánh thiếu dữ liệu là một trong nhiều nhóm.
- **`filter`** khi được phép loại bỏ hẳn các bản ghi không đủ điều kiện; phải cân nhắc tác động lên tính đầy đủ của báo cáo.

Ví dụ nguồn có `null` category nhưng region khác nhau: nếu dùng `partitioningBy(categoryMissing)`, mọi bản ghi thiếu category vào cùng phân vùng. Nếu dùng `groupingBy(GroupKey)`, chúng vẫn có thể tách theo region. Vì vậy hai API không thay nhau trong mọi nhu cầu.

## 9. Khóa tổ hợp và tính ổn định qua nhiều hệ thống

Một khóa nhóm có thể dùng nhiều thành phần:

```java
record ReportKey(
        String regionCode,
        String productCode,
        int fiscalYear
) {}
```

Với `record` chứa String và int bất biến, Java tạo `equals/hashCode` theo cả ba giá trị. Nhưng nếu một hệ thống dùng region code `"VN-S"` còn hệ thống khác dùng `"vn-s"`, record **không tự hiểu** đó là cùng mã. Cần một tầng chuẩn hóa đã thỏa thuận.

### 9.1. Dùng ID ổn định thay cho tên hiển thị

Đừng nhóm theo một tên khách hàng có thể sửa nếu thực chất muốn nhóm theo **cùng khách hàng qua các lần đổi tên**. Một ID nghiệp vụ ổn định thường là khóa đúng hơn:

```java
Map<Long, List<Order>> byCustomerId = orders.stream()
        .collect(Collectors.groupingBy(Order::customerId));
```

Đây là ví dụ minh họa, giả định class `Order` có accessor `customerId()`. Nếu ID là kiểu wrapper có thể null, vẫn phải xử lý thiếu dữ liệu trước khi trả key. Không nhầm với bản ghi `Order` có `long customerId()` primitive, vốn không thể nhận null nhưng có thể có giá trị sentinel sai như `0` nếu domain không cho phép.

### 9.2. Thứ tự của Map không phải tính ổn định của key

`HashMap` có thể chứa các khóa ổn định mà thứ tự lặp không xác định. `LinkedHashMap` có thể giữ thứ tự chèn trong một pipeline phù hợp. `TreeMap` dùng comparator hoặc thứ tự tự nhiên của key để sắp xếp.

Cần phân biệt:

- **Ổn định key**: cùng thực thể/cùng nhóm luôn tạo khóa tương đương.
- **Ổn định thứ tự output**: khi in hoặc serialize Map, các nhóm xuất hiện theo thứ tự được xác định.

Nếu báo cáo cần thứ tự alphabet, hãy chọn comparator phù hợp hoặc sắp xếp các entry sau khi nhóm. Đừng dựa vào thứ tự ngẫu nhiên của `HashMap` để kiểm tra kết quả.

### 9.3. Cẩn thận với comparator của TreeMap

Với `TreeMap<K,V>`, điều kiện hai khóa được coi là trùng để lưu vào Map dựa trên **comparator** hoặc thứ tự tự nhiên. Nếu comparator coi hai khóa khác nhau theo `equals()` là tương đương, chúng có thể bị gộp vào một entry. Để đảm bảo ý nghĩa của `Map` và hợp đồng nhóm nhất quán, comparator nên nhất quán với `equals` khi đó là yêu cầu của dữ liệu.

Ví dụ comparator chỉ so sánh `region` và bỏ qua `category` sẽ gộp những `GroupKey` cùng region nhưng category khác nhau khi dùng `TreeMap`. Nếu mục tiêu là nhóm theo **hai thành phần**, comparator phải xét cả hai theo thứ tự đã chọn.

Nếu key là `Optional<String>`, không dùng `TreeMap` với natural ordering mặc định vì Optional không phải Comparable; cần comparator rõ ràng hoặc dùng `HashMap`/`LinkedHashMap`.

## 10. Xử lý dữ liệu null, blank, invalid và “unknown” đúng nghĩa

Cả bốn trường hợp sau **không nhất thiết giống nhau**:

| Giá trị đầu vào | Ý nghĩa có thể có | Cách xử lý cần quyết định |
| --- | --- | --- |
| `null` | Không có giá trị | Nhóm thiếu, loại bỏ hoặc báo lỗi |
| `""` | Chuỗi rỗng được cung cấp | Có thể coi là thiếu hoặc lỗi validation |
| `"   "` | Chỉ có khoảng trắng | Có thể `strip` rồi coi là thiếu |
| `"unknown"` | Một giá trị String thật | Có thể là category hợp lệ mang tên unknown |

Nếu dùng sentinel `"unknown"` cho tất cả dữ liệu thiếu, bản ghi thật sự có category `"unknown"` bị gộp nhầm. Dùng `Optional.empty()` trong key giúp tránh **đụng với chuỗi thật**, nhưng nếu chính sách cần phân biệt null và blank, vẫn cần hai trạng thái khác nhau.

Một số domain yêu cầu phân loại thêm **invalid** (ví dụ mã chứa ký tự cấm). Khi đó không nên lẳng lặng chuyển invalid thành missing: cần báo lỗi, nhóm riêng hoặc trả một cấu trúc trạng thái rõ ràng. Cách biểu diễn phải hỗ trợ chất lượng dữ liệu và thống kê thiếu thông tin.

### 10.1. Phần tử Sale bằng null

Nếu Stream chứa **bản ghi null**, lời gọi `Sale::category` hoặc `keyOf(sale)` sẽ gây NPE vì dereference null, độc lập với việc thành phần category có thể null. `List.of(...)` không chấp nhận phần tử null, nhưng nhiều nguồn khác có thể chứa.

Chọn chính sách trước khi nhóm:

```java
Stream<Sale> input = ...; // minh họa nguồn do caller cung cấp
Map<GroupKey, List<Sale>> grouped = input
        .filter(Objects::nonNull)
        .collect(Collectors.groupingBy(
                StableGroupingKeyDemo::keyOf));
```

Đoạn trên **chỉ minh họa** và cần import `Objects`. Nếu null record là lỗi dữ liệu nghiêm trọng, nên xác thực và báo lỗi thay vì lọc âm thầm. Phân biệt **phần tử null** với **field null của một object không null**.

### 10.2. Khóa missing vẫn phải là một object hợp lệ

`Optional.empty()` là object đại diện cho trạng thái không có giá trị. `new GroupKey(Optional.empty(), Optional.empty())` cũng là object key hợp lệ. Nhưng `GroupKey key = null` **không hợp lệ** làm classifier return của `groupingBy`. Đừng xem có chứa Optional là được phép trả object null.

### 10.3. Phần tử null trong downstream List

`Collectors.toList()` có thể thu phần tử null ở một số trường hợp, nhưng điều đó không khiến classifier được phép trả null. Đây là hai luồng dữ liệu khác nhau:

- Classifier key: `groupingBy` yêu cầu **khác null**.
- Downstream value: tùy collector/kiểu collection và phép mapping, có thể có quy tắc khác về null.

Nếu cần output List không null, phải kiểm tra và thiết kế downstream/pipeline tương ứng.

## 11. Xử lý song song và tính kết hợp

### 11.1. groupingByConcurrent không sửa lỗi thiết kế key

`Collectors.groupingByConcurrent` tạo Collector cho việc phân nhóm concurrent theo hợp đồng của nó, nhưng classifier vẫn phải trả khóa không null. Nó không chuẩn hóa chữ, không tự sửa `equals/hashCode` của key và không tự biến key mutable thành bất biến.

Nếu yêu cầu **độ ổn định thứ tự output**, `groupingByConcurrent` thường không phải lựa chọn đầu tiên; kết quả có thể không bảo đảm thứ tự encounter order như pipeline tuần tự dùng `LinkedHashMap`. Hãy đo và thiết kế theo nhu cầu thứ tự, hiệu năng và tính đúng đắn.

### 11.2. Khóa được giữ ổn định khi Map được chia/gộp

Trong parallel stream, framework có thể tạo nhiều Map trung gian rồi gộp. Nếu classifier tạo key mà `equals/hashCode` dựa vào trạng thái có thể thay đổi, hai bản ghi cùng nhóm có thể tạo khóa không tương đương giữa các nhánh hoặc mất khả năng tra cứu sau khi gộp.

Dùng immutable value key với hàm chuẩn hóa **thuần** (không sửa state bên ngoài) làm kết quả dễ dự đoán hơn. Một classifier đọc đồng hồ, bộ đếm mutable hoặc gọi một dịch vụ thay đổi kết quả mỗi lần sẽ không biểu diễn một nhóm ổn định.

### 11.3. Không sửa key hoặc collection nguồn đang duyệt

Ví dụ sai về thiết kế:

```java
// Không nên: classifier thay đổi Sale hoặc dữ liệu ngoài
// để quyết định khóa trong quá trình grouping.
sales.parallelStream().collect(Collectors.groupingBy(s -> {
    mutateSale(s);
    return keyOf(s);
}));
```

Đoạn này là **minh họa anti-pattern**: `mutateSale` cần do ứng dụng định nghĩa, không phải lời khuyên để triển khai. Tác dụng phụ có thể gây race hoặc phụ thuộc thứ tự. Nên chuẩn hóa từ dữ liệu đầu vào và trả immutable key mà không làm thay đổi bản ghi.

## 12. Thiết kế nhóm theo khóa: kiểm thử thế nào?

### 12.1. Kiểm thử tương đương về dữ liệu

Với quy tắc không phân biệt hoa/thường và bỏ khoảng trắng:

```java
GroupKey a = keyOf(new Sale("North", "Food", "A", 1));
GroupKey b = keyOf(new Sale(" north ", "food", "B", 1));

System.out.println(a.equals(b)); // true
System.out.println(a.hashCode() == b.hashCode()); // true
```

Đây là đoạn minh họa dùng `GroupKey` và `Sale` trong chương trình. Nếu `a.equals(b) == true` nhưng `hashCode()` khác nhau, key class không đáp ứng hợp đồng HashMap/Map. Record với các thành phần String/Optional bất biến giải quyết đúng phần triển khai so sánh, miễn các thành phần được chuẩn hóa nhất quán.

### 12.2. Kiểm thử dữ liệu thiếu và xung đột sentinel

Tạo hai bản ghi:

- `category = null`.
- `category = "__MISSING_CATEGORY__"`.

Nếu dùng String sentinel như trên, chúng có thể bị gộp sai. Nếu dùng `Optional.empty()` và `Optional.of("__missing_category__")` sau chuẩn hóa, chúng là **hai key khác nhau**. Đây là test quan trọng khi dữ liệu bên ngoài có thể cung cấp các giá trị khác dự kiến.

### 12.3. Kiểm thử tổng số bản ghi trước và sau nhóm

Với `groupingBy` không lọc phần tử, tổng số phần tử trong các danh sách nhóm phải bằng số phần tử đầu vào:

```java
long groupedCount = groups.values().stream()
        .mapToLong(List::size)
        .sum();
```

Nếu `groups` là `Map<K,List<Sale>>` hoặc `Map<K,List<String>>` và tất cả phần tử được đưa vào đúng một nhóm, `groupedCount` phải bằng tổng số phần tử ban đầu. Nếu bạn chọn `filter` để bỏ dữ liệu thiếu, phải cộng số bản ghi loại bỏ để giải thích chênh lệch.

### 12.4. Kiểm thử thứ tự nếu báo cáo yêu cầu

Nếu API công bố thứ tự nhóm, hãy chọn Map factory/comparator thích hợp và test rõ. Nếu API **không** công bố thứ tự, chỉ kiểm tra nội dung và số lượng mà không mặc định thứ tự iteration của HashMap.

### 12.5. Kiểm thử trên nguồn lớn và nhiều thread

Nếu dữ liệu cần chạy song song, tính cùng một kết quả bằng pipeline tuần tự và song song trên các phép tổng kết có tính kết hợp như `counting`/`summingInt` với phạm vi số phù hợp. So sánh **nội dung Map** thay vì thứ tự in. Nếu thấy khác biệt, kiểm tra các hàm chuẩn hóa có phụ thuộc state, key mutable, collector không đúng hợp đồng hoặc tràn số trước khi kết luận runtime bị lỗi.

## 13. Bảng quyết định nhanh

| Nhu cầu | Thiết kế khóa | Phương án xử lý |
| --- | --- | --- |
| Nhóm theo mã danh mục kỹ thuật có phân biệt chữ | `String` giữ nguyên hợp đồng | `groupingBy(Sale::category)` khi chắc chắn non-null |
| Nhóm theo mã không phân biệt hoa/thường | `String` chuẩn hóa thống nhất | `groupingBy(s -> normalizeRequired(...))` |
| Nhóm theo nhiều thuộc tính | `record CompositeKey(...)` | `groupingBy(this::keyOf)` |
| Chấp nhận null/blank là một nhóm riêng | `Optional<String>` hoặc key state | Classifier luôn trả object không null |
| Cần phân biệt null, blank, invalid | Kiểu trạng thái nhiều nhánh | Không dùng chung một sentinel |
| Chỉ cần hai nhóm theo điều kiện | `Boolean` | `partitioningBy(predicate)` |
| Chỉ cần số lượng trên mỗi nhóm | Key bất biến + `counting()` | Không thu toàn bộ List |
| Cần tổng thuộc tính số trên mỗi nhóm | Key bất biến + `summingInt/Long` | Kiểm tra phạm vi số |
| Cần duyệt nhóm theo thứ tự gặp đầu tiên | Key ổn định + `LinkedHashMap::new` | Ưu tiên pipeline tuần tự có thứ tự |
| Cần Map sắp theo key | Key/comparator tương thích | Dùng `TreeMap` với comparator đủ thành phần |
| Muốn nhóm song song | Key bất biến + collector phù hợp | Không dựa vào thứ tự callback |
| Nguồn có thể có bản ghi null | Kiểm tra trước classifier | Bỏ qua hoặc báo lỗi theo nghiệp vụ |

**Nguyên tắc:** quyết định **định nghĩa “cùng nhóm”** trước, rồi mới chọn collector. API giúp thực hiện hợp đồng đã chọn, không tự suy ra định nghĩa nghiệp vụ từ dữ liệu thô.

## 14. Các lỗi phổ biến

1. **Classifier trả `null`:** `Collectors.groupingBy` ném `NullPointerException`, dù `HashMap` cho phép key null.
2. **Dùng `"unknown"` làm sentinel tùy tiện:** có thể trùng với giá trị hợp lệ `"unknown"`.
3. **Không chuẩn hóa nhất quán:** `"Food"`, `"food"`, `" Food "` thành ba nhóm dù domain coi là một.
4. **Chuẩn hóa quá mức:** gộp những mã khác nhau mà nghiệp vụ cần phân biệt.
5. **Dùng entity mutable làm key:** thay đổi trường trong `equals/hashCode` làm Map không tìm lại được entry.
6. **Chỉ ghi đè equals mà quên hashCode:** không đáp ứng hợp đồng Map dựa trên hash.
7. **Dùng TreeMap comparator thiếu thành phần:** gộp khóa khác nhau theo equals thành một entry.
8. **Dựa vào HashMap iteration order:** báo cáo hoặc test có thể thay đổi giữa môi trường.
9. **Coi groupingByConcurrent cho phép khóa null:** không; phải xử lý thiếu khóa riêng.
10. **Bỏ bản ghi thiếu mà không thống kê:** tổng số bản ghi báo cáo giảm nhưng không giải thích.
11. **Trộn null record với null field:** cần chọn ranh giới kiểm tra khác nhau.
12. **Nhầm key normalization với việc thay dữ liệu gốc:** nên giữ raw value khi cần truy vết.
13. **Quên xử lý khóa tổ hợp:** nhóm theo một thành phần có thể làm mất chiều phân tích quan trọng.
14. **Ngầm coi phần tử nhóm là List mutable:** Collector cụ thể phải quyết định hợp đồng.
15. **Dùng classifier có side effect:** hành vi khó dự đoán khi Stream song song hoặc khi xử lý lại dữ liệu.
16. **Không kiểm thử khóa thiếu/blank/invalid riêng:** lỗi chất lượng dữ liệu có thể ẩn trong một nhóm tưởng là hợp lệ.

## 15. Bài tập tự luyện

**Bài 1.** Cho danh mục `"Food"`, `" food "` và `"FOOD"`. Viết một classifier gom thành một nhóm, khi domain coi ba chuỗi là cùng mã. Vì sao nên dùng `Locale.ROOT`?

**Bài 2.** Cho `List<Sale>` có `category() == null` ở một phần tử. Vì sao `groupingBy(Sale::category)` có thể ném NPE, dù `HashMap` hỗ trợ khóa null?

**Bài 3.** Thiết kế một key kiểu `Optional<String>` để phân biệt category thiếu với chuỗi có giá trị `"unknown"`. Trình bày kết quả `equals` giữa hai key đó.

**Bài 4.** Viết một `record GroupKey(String region, String category)`. Nếu nhóm theo region và category, `equals` của record xét những thành phần nào?

**Bài 5.** Một class key có field tham gia `hashCode` và field đó có thể sửa. Điều gì có thể xảy ra khi object đã nằm trong `HashMap` rồi field đổi?

**Bài 6.** Dùng `Collectors.groupingBy` với `Collectors.counting()` để tạo `Map<K,Long>` đếm số phần tử theo khóa. Vì sao không cần thu `List`?

**Bài 7.** Dùng `Collectors.groupingBy` với `Collectors.summingInt(...)` để lấy số lượng bán theo khu vực/danh mục. Nếu tổng có thể vượt `int`, nên chọn kiểu nào?

**Bài 8.** Cho `Sale` có region và category, category có thể thiếu. Dùng `partitioningBy` chia thành “thiếu category” và “có category”. So sánh với nhóm theo `GroupKey` hai thành phần.

**Bài 9.** Bạn muốn xuất báo cáo nhóm theo thứ tự gặp đầu tiên. Overload `groupingBy` nào cho phép chọn `LinkedHashMap::new`? Vì sao vẫn phải xét tính ordered của nguồn?

**Bài 10.** Với khóa tổ hợp record dùng `Optional<String>`, hãy viết hai bản ghi có cùng key sau chuẩn hóa và kiểm tra `equals`, `hashCode`.

**Bài 11.** Một TreeMap comparator chỉ xét region nhưng key thực tế gồm region và category. Hệ quả có thể xảy ra khi hai bản ghi cùng region, khác category?

**Bài 12.** Một báo cáo có 100 bản ghi, 7 bản ghi category null. Nếu pipeline lọc null trước `groupingBy`, tổng các kích thước List nhóm là bao nhiêu? Vì sao phải ghi nhận 7 bản ghi bị loại?

**Bài 13.** Với `Map<GroupKey,List<Sale>>`, viết pipeline tính tổng số phần tử trên tất cả nhóm để đối chiếu số lượng bản ghi gốc.

**Bài 14.** Nêu hai lỗi vẫn có thể xảy ra khi đổi `groupingBy` sang `groupingByConcurrent` nếu key là mutable và classifier trả null.

### Gợi ý đáp án

1. `s -> s.strip().toLowerCase(Locale.ROOT)` với tiền điều kiện non-null; `Locale.ROOT` tránh phụ thuộc locale mặc định khi chuẩn hóa mã.
2. `groupingBy` yêu cầu classifier return khác null; điều này độc lập khả năng cho null key của một Map cụ thể.
3. `Optional.empty()` khác `Optional.of("unknown")`; không có xung đột sentinel.
4. Cả `region` và `category` tham gia so sánh giá trị theo record.
5. `get/containsKey` có thể không tìm lại khóa, nhóm mất ổn định; nên tạo immutable key.
6. `groupingBy(keyOf, counting())` trả Map chứa số lượng, không lưu toàn bộ object.
7. `summingLong(...)` hoặc kiểu số lớn/kiểm tra tràn theo phạm vi nghiệp vụ.
8. `partitioningBy` chỉ hai nhánh; `GroupKey` vẫn tách theo region và category.
9. `groupingBy(classifier, LinkedHashMap::new, downstream)`; thứ tự chèn có ý nghĩa rõ khi nguồn tuần tự ordered.
10. `keyOf(new Sale("North","Food",...))` và `keyOf(new Sale(" north ","food",...))` có `equals == true`, `hashCode` bằng nhau.
11. TreeMap có thể coi hai khóa tương đương theo comparator và gộp vào một entry, không phản ánh nhóm hai chiều.
12. 93 nếu mỗi phần tử còn lại được gom một lần; 7 bản ghi thiếu cần được giải thích trong báo cáo chất lượng dữ liệu.
13. `groups.values().stream().mapToLong(List::size).sum()`.
14. Mutable key phá `equals/hashCode` ổn định; classifier null vẫn gây NPE, concurrent không tự sửa.

## Kết luận

**Thiết kế khóa nhóm tốt là điều kiện để `Collectors.groupingBy` cho kết quả đúng.** Một key phải diễn đạt đúng định nghĩa “cùng nhóm”, có `equals/hashCode` ổn định và không thay đổi trong lúc được lưu vào Map. Quy tắc chuẩn hóa phải được xác định từ domain, không tự ý loại bỏ những khác biệt có ý nghĩa.

Khi khóa hoặc thành phần khóa có thể thiếu, **đừng trả `null` trực tiếp từ classifier của `groupingBy`**. Thay vào đó, dùng một trạng thái khóa hợp lệ như `Optional.empty()`, một kiểu riêng hoặc một sentinel đã được bảo đảm không xung đột; hoặc loại bản ghi với chính sách minh bạch. Sau đó chọn downstream collector, Map factory và chế độ thực thi theo mục tiêu báo cáo. Điều này giúp nhóm dữ liệu đúng, kiểm thử được và bền vững khi ứng dụng phát triển.
