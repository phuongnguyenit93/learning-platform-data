# Java 10 — Xây dựng bảng tra cứu từ Stream với chính sách xung đột rõ ràng

## 1. Mục tiêu bài học

Một **bảng tra cứu** (*lookup table*) dạng `Map<K, V>` cho phép tìm dữ liệu nhanh theo khóa: mã sản phẩm → sản phẩm, mã nhân viên → hồ sơ, mã địa điểm → thông tin cấu hình. Khi chuyển một `Stream<T>` thành `Map<K, V>`, việc quan trọng không chỉ là chọn `keyMapper` và `valueMapper`. Ta còn phải quyết định **điều gì xảy ra nếu hai phần tử tạo cùng một khóa**.

Java 8 có `Collectors.toMap(...)` và `Collectors.groupingBy(...)`. Java 10 bổ sung `Collectors.toUnmodifiableMap(...)`, phù hợp khi kết quả là bảng tra cứu được công bố theo hợp đồng **không cho thay đổi các cặp khóa–giá trị**. Các API này vẫn là công cụ chuẩn trong Java hiện đại.

Sau bài học, bạn sẽ:

1. Nhận diện thế nào là xung đột khóa theo `equals` và vì sao dữ liệu đầu vào có thể phát sinh khóa trùng sau bước chuẩn hóa.
2. Dùng chính sách **báo lỗi, giữ bản đầu, giữ bản sau, cộng dồn, chọn theo ưu tiên** hoặc **giữ tất cả giá trị** một cách minh bạch.
3. So sánh `toMap` (Java 8), `toUnmodifiableMap` (Java 10) và `groupingBy` khi tạo bảng tra cứu.
4. Xử lý đúng `null`, tính duy nhất của khóa, thứ tự duyệt, tính bất biến của kết quả và dữ liệu đồng thời.
5. Viết chương trình Java 17+ chạy được, dự đoán đúng stdout và tạo kiểm thử xác nhận chính sách xung đột.
6. Tránh chính sách “giữ bản cuối” mang nghĩa mơ hồ khi stream không có thứ tự hoặc chạy song song.

**Trọng tâm:** bài này dạy thiết kế **hợp đồng xung đột rõ ràng**, không phải chỉ chọn một overload ngắn nhất. Ví dụ dùng `record` để gọn và an toàn trong Java 17+; `record` là tính năng Java 16, còn collector `toUnmodifiableMap` mới là phần ra đời ở Java 10.

## 2. Tư duy đúng: mỗi khóa ứng với một giá trị

`Map<K, V>` không lưu hai mapping khác nhau có cùng khóa theo quan hệ bằng nhau của khóa. Nếu có hai dòng:

```text
sku="A-1", name="alpha",     quantity=2
sku="A-1", name="alpha-new", quantity=5
```

thì ánh xạ `sku -> item` có **xung đột**. Không thể đưa cả hai object thành hai giá trị độc lập dưới cùng key `"A-1"` trong kiểu `Map<String, Item>`.

Quy tắc xác định trùng là quan hệ `equals` của khóa. Với các implementation hash-map phổ biến, `hashCode` cũng phải nhất quán với `equals`. Hai chuỗi `"a-1"` và `"A-1"` không bằng nhau theo `String.equals`, nhưng nếu ứng dụng chuẩn hóa khóa bằng `toUpperCase(Locale.ROOT)` trước khi gom, cả hai có thể trở thành **cùng khóa** `"A-1"`.

**Hợp đồng cần chọn trước khi viết collector:**
- Khóa có **bắt buộc duy nhất** không?
- Nếu trùng, đó là **lỗi dữ liệu**, hay hai bản ghi hợp lệ cần hợp nhất?
- Nếu giữ một bản, **bản nào thắng**, dựa trên thứ tự nguồn hay ưu tiên nghiệp vụ?
- Nếu cần mọi bản ghi, kiểu giá trị có nên là `List<V>` thay cho `V`?
- Bảng sau khi xây có được phép cập nhật không?
- Có cần thứ tự hiển thị cố định, hoặc chỉ cần tra cứu theo key?

Không có một chính sách xung đột mặc định nào thích hợp cho mọi dữ liệu.

## 3. Ba họ API quan trọng

### 3.1. `Collectors.toMap` — Java 8

Những overload phổ biến:

```java
Collectors.toMap(keyMapper, valueMapper)
Collectors.toMap(keyMapper, valueMapper, mergeFunction)
Collectors.toMap(keyMapper, valueMapper, mergeFunction, mapFactory)
```

Đây là **chữ ký sử dụng**, không phải các lời gọi hoàn chỉnh nếu thiếu đối số.

- **Hai đối số:** nếu hai phần tử tạo khóa trùng theo `equals`, quá trình `collect` ném `IllegalStateException`.
- **Ba đối số:** khi trùng khóa, dùng `mergeFunction` để kết hợp hai giá trị.
- **Bốn đối số:** như trên, thêm `mapFactory` để chọn implementation của map kết quả, ví dụ `LinkedHashMap::new`.

**Đừng dựa vào việc `toMap` trả về `HashMap` mutable.** Javadoc không cam kết loại implementation, mutability, serializability hay thread-safety của map từ các overload không chỉ định factory. Nếu cần map mutable có kiểu cụ thể, hãy nêu factory; nếu cần map không cho sửa, dùng `toUnmodifiableMap` hoặc đóng băng kết quả phù hợp.

### 3.2. `Collectors.toUnmodifiableMap` — Java 10

Hai overload:

```java
Collectors.toUnmodifiableMap(keyMapper, valueMapper)
Collectors.toUnmodifiableMap(keyMapper, valueMapper, mergeFunction)
```

- Cả hai tạo map **không cho thêm, xóa hoặc thay mapping**.
- Overload **hai đối số** ném `IllegalStateException` khi có khóa trùng.
- Overload **ba đối số** dùng `mergeFunction` giải quyết giá trị khi trùng.
- Cả hai **từ chối khóa null và giá trị null**, ném `NullPointerException` nếu mapper trả null.
- Map kết quả **không cam kết thứ tự duyệt**; không dùng `toString()` làm hợp đồng thứ tự.
- Unmodifiable không có nghĩa **deep immutable**: object key/value mutable vẫn có thể đổi thuộc tính qua tham chiếu khác.

Đây là điểm gắn với Java 10: nhóm có thể công bố bảng tra cứu read-only ngay tại terminal collector, thay vì thu một map rồi dựa vào một quy ước không được API bảo đảm.

### 3.3. `Collectors.groupingBy` — Java 8

Khi **một khóa hợp lệ có nhiều giá trị**, bài toán không phải “chọn người thắng” mà là **giữ nhóm**:

```java
Collectors.groupingBy(classifier)
Collectors.groupingBy(classifier, downstreamCollector)
Collectors.groupingBy(classifier, mapFactory, downstreamCollector)
```

Ví dụ kết quả là `Map<String, List<Item>>`; các item trùng SKU chuẩn hóa được đặt chung trong một list. `groupingBy` không mặc nhiên trả unmodifiable map hoặc unmodifiable lists; nếu cần một lookup read-only, hãy chọn downstream phù hợp và đóng băng map bên ngoài một cách có chủ đích.

**Tiêu chí chọn:**
- Một khóa **phải có một** giá trị → `toMap`/`toUnmodifiableMap` và xử lý xung đột.
- Một khóa **có thể có nhiều** giá trị hợp lệ → `groupingBy`.
- Cần đếm/cộng dồn mỗi khóa → có thể dùng merge collector hoặc `groupingBy(..., summingInt(...))`, chọn cách dễ đọc với yêu cầu nghiệp vụ.

## 4. Bảng chính sách xung đột

| Chính sách | Merge function thường gặp | Khi phù hợp | Rủi ro cần nhớ |
|---|---|---|---|
| **Báo lỗi** | Không truyền mergeFunction cho overload hai đối số | Khóa được yêu cầu duy nhất tuyệt đối | Dữ liệu lỗi làm `collect` ném `IllegalStateException` |
| **Giữ bản gặp trước** | `(existing, incoming) -> existing` | Nguồn **có thứ tự xác định** và ưu tiên bản xuất hiện sớm | Không nên dùng khi thứ tự không xác định |
| **Giữ bản gặp sau** | `(existing, incoming) -> incoming` | Dữ liệu có thứ tự rõ, bản sau được phép ghi đè | Không đồng nghĩa “mới nhất theo thời gian” nếu chưa sort |
| **Cộng dồn số** | `Integer::sum` | Tổng số lượng/giá trị theo khóa | Xem tràn số, kiểu dữ liệu, quy tắc làm tròn |
| **Chọn ưu tiên cao** | `BinaryOperator.maxBy(comparator)` | Dùng timestamp, version, mức độ ưu tiên rõ | Comparator cần xác định đủ quy tắc tie-break |
| **Giữ mọi bản** | Không dùng một `V`; dùng `groupingBy` để nhận `List<V>` | Một khóa trùng vẫn hợp lệ | Phải thiết kế phần tử và danh sách con có được sửa hay không |
| **Gộp danh sách** | Merge các giá trị danh sách thành danh sách mới | Muốn Map<K, List<V>> với cấu trúc theo ý định | Cần rõ thứ tự và tránh làm biến đổi shared list trong merge |

**Lưu ý quan trọng:** `mergeFunction` trong các overload trên nhận **hai giá trị `V`**, không nhận khóa `K`. Nó không phải là `(key, old, new) -> ...`. Nếu thông báo lỗi cần nêu chính xác khóa bị trùng, hãy cân nhắc kiểm tra trùng từ trước, giữ key trong value, hoặc group theo key rồi xác thực; đừng tự tưởng tượng mergeFunction có tham số key thứ ba.

## 5. Chuẩn hóa key trước khi kiểm tra xung đột

Ví dụ mã sản phẩm có khoảng trắng thừa và không phân biệt chữ hoa/thường:

```java
static String canonicalSku(String raw) {
    return raw.strip().toUpperCase(Locale.ROOT);
}
```

Đây là method minh họa đặt trong class, cần import `java.util.Locale`. `String.strip()` có từ **Java 11**, còn `Locale.ROOT` là cách chỉ định locale độc lập ngôn ngữ cho chuẩn hóa chuỗi. Nếu code phải target **Java 10**, thay `strip()` bằng cách xử lý whitespace phù hợp API lúc đó; không gọi nhầm `strip()` là tính năng của Java 10.

Từ:

```text
" A-1 " -> "A-1"
"b-2"   -> "B-2"
"a-1"   -> "A-1"
```

hai giá trị đầu/ cuối cùng trong ví dụ có thể va chạm **chỉ sau chuẩn hóa**. Nếu thu bằng `toMap(Item::sku, ...)` khi không chuẩn hóa, chương trình dễ bỏ sót lỗi trùng logic.

**Quy ước tốt cho lookup table:**

1. Xác định kiểu key và quy tắc equality của domain.
2. Chuẩn hóa key **một lần**, nhất quán cho lúc xây map và lúc tra cứu.
3. Xác thực key không rỗng, không null, có định dạng được phép, nếu nghiệp vụ yêu cầu.
4. Chọn chính sách trùng dựa trên **khóa đã chuẩn hóa**.
5. Không dùng `toLowerCase()`/`toUpperCase()` mà quên yếu tố locale và đặc thù Unicode khi đây là identifier quan trọng. Các quy tắc canonicalization thực tế cần được domain định nghĩa rõ, không chỉ thao tác chuỗi tùy tiện.

Nếu key là object tự định nghĩa, hãy bảo đảm `equals/hashCode` ổn định; sửa field dùng làm key sau khi đưa vào hash-map có thể khiến tra cứu không còn đúng.

## 6. Ví dụ Java 17+ đầy đủ: báo lỗi, giữ đầu, giữ sau, cộng số

Tệp: **`LookupPolicyDemo.java`**

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

public class LookupPolicyDemo {

    // record từ Java 16; ví dụ này target Java 17+.
    record Item(String sku, String name, int quantity) {}

    static String canonical(Item item) {
        return item.sku().strip().toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        var items = List.of(
            new Item(" A-1 ", "alpha", 2),
            new Item("b-2", "beta", 3),
            new Item("a-1", "alpha-new", 5),
            new Item("C-3", "gamma", 4)
        );

        // 1. Chính sách duy nhất: không cho trùng khóa.
        try {
            items.stream().collect(Collectors.toUnmodifiableMap(
                LookupPolicyDemo::canonical, Function.identity()));
            System.out.println("duplicateRejected=false");
        } catch (IllegalStateException ex) {
            System.out.println("duplicateRejected=true");
        }

        // 2. Giữ bản xuất hiện trước trong nguồn List có thứ tự.
        var first = items.stream().collect(Collectors.toUnmodifiableMap(
            LookupPolicyDemo::canonical,
            Function.identity(),
            (oldValue, newValue) -> oldValue));

        // 3. Giữ bản xuất hiện sau trong nguồn List có thứ tự.
        var last = items.stream().collect(Collectors.toUnmodifiableMap(
            LookupPolicyDemo::canonical,
            Function.identity(),
            (oldValue, newValue) -> newValue));

        // 4. Tổng số lượng theo SKU; giá trị trong Map là Integer.
        var totals = items.stream().collect(Collectors.toUnmodifiableMap(
            LookupPolicyDemo::canonical,
            Item::quantity,
            Integer::sum));

        // 5. Khi muốn giữ thứ tự thêm key, chọn factory rõ ràng.
        var ordered = items.stream().collect(Collectors.toMap(
            LookupPolicyDemo::canonical,
            Function.identity(),
            (oldValue, newValue) -> oldValue,
            LinkedHashMap::new));

        System.out.println("keys=" + first.size());
        System.out.println("firstA=" + first.get("A-1").name());
        System.out.println("lastA=" + last.get("A-1").name());
        System.out.println("totalA=" + totals.get("A-1"));
        System.out.println("orderedKeys="
                + new ArrayList<>(ordered.keySet()));

        // Map Java 10 không cho sửa mapping.
        try {
            first.put("X", new Item("X", "x", 1));
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable=true");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac --release 17 LookupPolicyDemo.java
java LookupPolicyDemo
```

**Stdout chính xác**:

```text
duplicateRejected=true
keys=3
firstA=alpha
lastA=alpha-new
totalA=7
orderedKeys=[A-1, B-2, C-3]
unmodifiable=true
```

### 6.1. Đọc từng kết quả

- Khóa `A-1` xuất hiện hai lần sau `canonical`. Overload hai đối số không có chính sách gộp nên ném `IllegalStateException`.
- `first.get("A-1")` cho `alpha` vì chính sách giữ giá trị cũ khi đọc nguồn tuần tự theo thứ tự `List`.
- `last.get("A-1")` cho `alpha-new` vì chính sách chọn giá trị mới khi gặp khóa trùng trong nguồn tuần tự.
- `totals.get("A-1")` là `2 + 5 = 7`. Hai bản ghi cùng SKU được cộng dồn thay vì chọn một object.
- `first.size() == 3`, tương ứng ba khóa đã chuẩn hóa `A-1`, `B-2`, `C-3`. Code không in trực tiếp map nên không dựa vào thứ tự iterator của unmodifiable map.
- `ordered` được tạo bằng overload bốn đối số `toMap(..., LinkedHashMap::new)`. Nguồn List được xử lý tuần tự và `LinkedHashMap` duyệt theo thứ tự thêm key đầu tiên, nên thứ tự key là `[A-1, B-2, C-3]`.
- `first.put(...)` bị chặn vì `toUnmodifiableMap` cung cấp map không cho sửa.

**Lưu ý:** `ordered` là một `LinkedHashMap` mutable; nếu gửi cho caller không được phép sửa, hãy đặt hợp đồng phù hợp. `Map.copyOf(ordered)` tạo unmodifiable map nhưng **không cam kết giữ thứ tự duyệt**. Nếu yêu cầu thứ tự hiển thị, sử dụng một danh sách đã sắp xếp hay một wrapper chỉ đọc trên `LinkedHashMap` có backing không bị làm lộ.

### 6.2. Vì sao bản “sau” chưa chắc “mới nhất”?

`(oldValue, newValue) -> newValue` chỉ nói **giá trị được xử lý sau trong quá trình gộp sẽ thắng**. Nó không tự so sánh `timestamp`, `version` hay độ tin cậy của bản ghi.

Nếu stream nguồn là một tập `HashSet` không có encounter order, hoặc upstream có `unordered()`, không được coi “last” là bản ghi mới nhất. Ngay cả khi nguồn có thứ tự, cần chứng minh thứ tự ấy có ý nghĩa nghiệp vụ.

Nếu cần **mới nhất theo thời gian**, hãy định nghĩa comparator theo `updatedAt`, thêm tie-break thích hợp và dùng hàm lựa chọn theo comparator (ví dụ `BinaryOperator.maxBy(comparator)`) thay vì dựa vào vị trí cuối một cách ngầm định.

## 7. Khi cần xung đột rõ ràng hơn: chọn theo comparator

Một chính sách theo domain giúp giảm phụ thuộc vào encounter order:

```java
var byPriority = items.stream().collect(
    Collectors.toUnmodifiableMap(
        LookupPolicyDemo::canonical,
        Function.identity(),
        java.util.function.BinaryOperator.maxBy(
            java.util.Comparator
                .comparingInt(LookupPolicyDemo.Item::quantity)
                .thenComparing(LookupPolicyDemo.Item::name)
        )
    )
);
```

Đây là **mảnh code đặt trong `main` của `LookupPolicyDemo`**, dùng record `Item` và `items` đã khai báo ở mục 6. Comparator ưu tiên `quantity` lớn hơn, rồi dùng `name` để phá hòa. Với ví dụ trên, SKU `A-1` chọn bản `alpha-new` do số lượng 5 lớn hơn 2.

Nếu hai bản ghi vẫn bằng nhau theo tất cả tiêu chí so sánh nhưng khác nhau ở thông tin quan trọng, hãy bổ sung tie-break hoặc báo lỗi. Một comparator tốt phải **bao trùm mọi tiêu chí quyết định người thắng**; không dựa vào thứ tự merge nếu ý định là chọn theo ưu tiên.

Đối với parallel stream, một merge **kết hợp được** (*associative*) và không có side effect như phép cộng số hay chọn giá trị lớn nhất theo thứ tự tổng xác định phù hợp hơn “giữ bản đến cuối” dựa trên lịch duyệt không rõ. Đồng thời cần xét tính kết hợp, tràn số và độ ổn định của comparator.

### 7.1. Khi trùng là lỗi: thất bại sớm và thông báo tốt

Nếu khóa được cam kết duy nhất, cấu trúc dễ đọc nhất thường là:

```java
var byCode = items.stream().collect(
    Collectors.toUnmodifiableMap(
        LookupPolicyDemo::canonical,
        Function.identity()
    )
);
```

Nó ném `IllegalStateException` nếu xuất hiện khóa trùng. Trình biên dịch vẫn chấp nhận lời gọi; ngoại lệ phát sinh **lúc thực hiện terminal operation**. Không cố catch rồi lặng lẽ giữ dữ liệu tùy ý nếu đó là lỗi đầu vào.

Đôi khi cần exception tùy biến mô tả rõ “mã sản phẩm trùng”. Có thể viết merge function ném lỗi:

```java
(oldValue, newValue) -> {
    throw new IllegalArgumentException(
        "Duplicate items: " + oldValue + " / " + newValue);
}
```

Đây là **mảnh lambda dùng làm `mergeFunction`**, không phải chương trình độc lập. Nó có access tới **hai value**, **không** tự nhận tham số key. Muốn in key chính xác, hãy lấy key từ value nếu có, hoặc làm bước prevalidation riêng; và không dựa vào toàn bộ nội dung exception mặc định của JDK.

## 8. Null: phải quyết định trước khi collect

`Collectors.toUnmodifiableMap` (Java 10) **từ chối null key và null value**. Trong dữ liệu thực tế:
- Key có thể null do thiếu mã định danh.
- Value có thể null do mapper trả null khi nguồn chưa có thông tin.
- Nếu method chuẩn hóa như `raw.strip()` được gọi trên null, `NullPointerException` xảy ra **ngay trong keyMapper**, trước khi collector hoàn tất.

Không dùng `Map.of("key", null)` để thử tình huống này vì `Map.of` tự từ chối null trước bước collect. Dùng record/đối tượng nguồn có field null nếu muốn kiểm tra collector.

**Quy ước kiểm soát null:**
1. Xác thực và ghi nhận dữ liệu thiếu trước khi gom, nếu thiếu là lỗi nghiệp vụ.
2. Nếu nghiệp vụ cho phép bỏ bản ghi không hợp lệ, lọc với điều kiện rõ ràng và có thống kê/cảnh báo phù hợp; đừng lọc âm thầm.
3. Nếu cần đại diện cho “không có dữ liệu”, cân nhắc kiểu value có ý nghĩa (ví dụ một sealed result hoặc một trạng thái domain), thay vì tạo một Map với null thiếu hợp đồng.
4. Không dựa vào việc `Collectors.toMap` với implementation hiện tại có thể chấp nhận hay từ chối null trong một số đường đi. Hợp đồng của `toUnmodifiableMap` mới là cam kết rõ ràng **không-null**.

## 9. Nhiều giá trị hợp lệ cho cùng khóa: dùng groupingBy

Nếu một SKU có nhiều lần xuất hiện và ứng dụng cần **giữ tất cả lần xuất hiện** để tra cứu, không nên viết `(old, next) -> old` hoặc `-> next` rồi mất dữ liệu.

Tạo kiểu `Map<String, List<Item>>`:

```java
var grouped = items.stream().collect(
    Collectors.groupingBy(
        LookupPolicyDemo::canonical,
        Collectors.toUnmodifiableList()
    )
);
var readOnlyGrouped = Map.copyOf(grouped);
```

Mảnh code này đặt trong `LookupPolicyDemo.main`, cần `Map` và `Collectors` đã import. `groupingBy` thu các item cùng key thành list. `Collectors.toUnmodifiableList()` (Java 10) giúp list con không cho sửa; `Map.copyOf(...)` (Java 10) làm map ngoài không cho sửa và không phản ánh các thay đổi cấu trúc của `grouped` sau đó. Không có deep copy của bản ghi.

**Bẫy:** chỉ dùng `Collectors.groupingBy(..., Collectors.toUnmodifiableList())` **không đủ để bảo đảm map ngoài unmodifiable**. Tương tự, chỉ bọc map ngoài mà list con vẫn mutable thì người nhận có thể sửa nội dung từng list. Phải xác định mức độ read-only mong muốn ở **cả hai lớp**.

**Thứ tự:** nếu stream có encounter order, list con có thể giữ thứ tự của các bản ghi trong nhóm theo downstream List collector; tuy nhiên **không được dựa vào thứ tự duyệt các key của Map** khi dùng mặc định. Nếu cần thứ tự key ổn định, xét map factory hoặc một bước biểu diễn đầu ra có thứ tự riêng.

### 9.1. Grouping vs merging

- `groupingBy(Item::sku)`: giữ mọi item, cho phép xử lý lịch sử hoặc nhiều record hợp lệ cho mỗi khóa.
- `toUnmodifiableMap(Item::sku, Item::quantity, Integer::sum)`: nén thành **tổng số lượng** theo khóa, không giữ lại từng bản ghi.
- `toUnmodifiableMap(Item::sku, Function.identity(), (a,b)->a)`: giữ một bản và **mất các bản còn lại**.

Trước khi chọn, hãy hỏi yêu cầu là **tra cứu duy nhất**, **tổng hợp số liệu** hay **tra cứu mọi bản ghi**. Dùng sai cấu trúc dữ liệu sẽ tạo bug nghiệp vụ dù Java vẫn biên dịch.

## 10. Chương trình đầy đủ Java 17+: null và grouping

Tệp: **`LookupEdgeCasesDemo.java`**

```java
import java.util.List;
import java.util.Map;
import java.util.function.Supplier;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class LookupEdgeCasesDemo {

    record Row(String key, Integer quantity) {}

    static String run(Supplier<?> task) {
        try {
            task.get();
            return "accepted";
        } catch (NullPointerException ex) {
            return "rejected";
        }
    }

    public static void main(String[] args) {
        System.out.println("nullKey=" + run(() ->
                Stream.of(new Row(null, 1))
                    .collect(Collectors.toUnmodifiableMap(
                        Row::key, Row::quantity))));

        System.out.println("nullValue=" + run(() ->
                Stream.of(new Row("a", null))
                    .collect(Collectors.toUnmodifiableMap(
                        Row::key, Row::quantity))));

        var events = List.of(
            new Row("a", 1),
            new Row("a", 2),
            new Row("b", 3)
        );

        var grouped = events.stream().collect(
            Collectors.groupingBy(
                Row::key,
                Collectors.mapping(
                    Row::quantity,
                    Collectors.toUnmodifiableList()
                )
            )
        );

        var frozen = Map.copyOf(grouped);
        System.out.println("groupA=" + frozen.get("a"));
        System.out.println("groupB=" + frozen.get("b"));
        System.out.println("groupSize=" + frozen.size());

        // Map.merge quy định nếu merge function trả null,
        // mapping tương ứng bị loại bỏ: phải tránh nếu không chủ ý.
        var removed = Stream.of(
            new Row("a", 1),
            new Row("a", 2)
        ).collect(Collectors.toUnmodifiableMap(
            Row::key, Row::quantity, (left, right) -> null));

        System.out.println("nullMergeRemoved=" + removed.isEmpty());
    }
}
```

```bash
javac --release 17 LookupEdgeCasesDemo.java
java LookupEdgeCasesDemo
```

**Stdout chính xác**:

```text
nullKey=rejected
nullValue=rejected
groupA=[1, 2]
groupB=[3]
groupSize=2
nullMergeRemoved=true
```

Giải thích:

1. Trường `Row.key` hoặc `Row.quantity` là null; hai collector Java 10 từ chối theo hợp đồng.
2. `groupingBy` giữ **hai số lượng cho khóa a**, được đưa vào list `[1, 2]`; `b` có `[3]`. Map ngoài đã được đóng băng bằng `Map.copyOf`.
3. `mergeFunction` trả null là một bẫy dễ bỏ sót. Vì collector gọi cơ chế gộp có ngữ nghĩa như `Map.merge`, giá trị null từ merge **loại mapping** cho key đó; kết quả có thể trở thành map rỗng. Điều này **không giống** khóa/valueMapper trả null (bị từ chối).
4. Đừng sử dụng `(left,right) -> null` như cách “chọn bỏ” bản ghi nếu không có quy tắc nghiệp vụ rõ. Thường tốt hơn là lọc input trước hoặc định nghĩa một loại kết quả rõ nghĩa.

Trong mã chính, có thể tránh `run(Supplier<?>)` và bắt lỗi ở ranh giới dữ liệu với message thích hợp; helper chỉ phục vụ việc làm nổi bật quy tắc trong ví dụ.

## 11. Thứ tự key, bản “đầu/cuối” và tính xác định

### 11.1. Map là cấu trúc tra cứu, không mặc nhiên là danh sách có thứ tự

`toUnmodifiableMap` không cam kết thứ tự duyệt các mapping. Vì vậy:

```java
System.out.println(myMap);
```

không nên được dùng như một định dạng xuất tuần tự ổn định khi cần so sánh byte-for-byte, ký số, hoặc hiển thị thứ tự cố định.

Nếu cần thứ tự, có thể:
- Dùng `Collectors.toMap(..., LinkedHashMap::new)` trong luồng tuần tự có encounter order để bảo toàn thứ tự chèn key; không làm lộ backing mutable map nếu chỉ muốn đọc.
- Sắp xếp key khi xuất kết quả: `map.keySet().stream().sorted()...`.
- Dùng `TreeMap` nếu thứ tự key theo comparator phù hợp nghiệp vụ; chú ý comparator ảnh hưởng quan hệ key duy nhất.
- Với Java 21+, có `SequencedMap` và API xử lý thứ tự tương ứng ở những collection hỗ trợ, nhưng đó là phần mở rộng **Java 21**, không phải tính năng Java 10.

### 11.2. Tránh định nghĩa “last wins” trên nguồn thiếu encounter order

Chính sách `(existing, incoming) -> incoming` dễ đọc trong **stream tuần tự của List có thứ tự**. Nhưng trên stream không có thứ tự, hoặc khi pipeline xử lý bất đồng bộ, khái niệm “cuối” có thể không có nghĩa nghiệp vụ ổn định.

Nếu cần “bản mới nhất”, hãy dựa trên `Instant updatedAt` hoặc version nghiệp vụ và comparator tie-break xác định. Nếu cần “bản ưu tiên cao nhất”, hãy xét độ ưu tiên. **Đừng dùng vị trí xử lý ngẫu nhiên làm quyết định nghiệp vụ.**

### 11.3. Parallel stream và hàm merge

`Collectors.toMap` và `toUnmodifiableMap` không đồng nghĩa với collector concurrent. Khi chạy song song, framework có thể kết hợp các map trung gian; vì thế một hàm merge cần có các thuộc tính tốt:
- Không gây side effect lên input hoặc trạng thái dùng chung.
- Có hành vi xác định.
- Tính **kết hợp** phù hợp với cách các phần kết quả được gộp: `sum`, `min/max` có tie-break tốt thường dễ lý giải hơn phép nối tùy thứ tự.
- Nếu phép cộng có thể tràn số, dùng kiểu/phép toán phát hiện hoặc xử lý tràn theo nghiệp vụ, ví dụ `Math.addExact` khi phù hợp.

**Không tự động chuyển sang `toConcurrentMap` chỉ để tăng tốc** nếu bản ghi cần có chính sách “first/last” phụ thuộc thứ tự. `toConcurrentMap` là nhóm collector concurrent/unordered với các cam kết khác; phải xem lại ý nghĩa xung đột và tính xác định.

## 12. Xung đột do key object mutable

Một khóa trong map có thể là object tùy biến. Với hash-based map, nếu đối tượng key thay đổi dữ liệu tham gia `equals()` hoặc `hashCode()` sau khi collect, việc tra cứu có thể thất bại hoặc trả kết quả không mong muốn.

**Quy ước:** dùng key bất biến, ví dụ `String` đã canonicalize, `UUID`, enum, hoặc một value object bất biến phù hợp. Nếu dùng record làm key, nhớ rằng record **không tự làm các object component tham chiếu trở thành bất biến sâu**; tránh chứa state mutable tham gia equality.

Tương tự, map unmodifiable **không** đóng băng giá trị object. Một `Map<String, MutableCustomer>` vẫn cho phép khách hàng bên trong bị sửa qua tham chiếu. Nếu yêu cầu snapshot bất biến về dữ liệu, phải snapshot các value riêng theo thiết kế domain.

## 13. Cách kiểm thử bảng tra cứu đúng hợp đồng

### 13.1. Test chính sách không cho trùng

Dùng dữ liệu có cùng canonical key và kiểm tra `IllegalStateException` khi gọi `collect` không có mergeFunction. Không kiểm tra **chính xác chuỗi message** của exception, vì nội dung message có thể thay đổi theo JDK.

### 13.2. Test giữ đầu/giữ sau bằng nguồn có thứ tự xác định

Với danh sách:

```text
A-1: alpha(2)
B-2: beta(3)
A-1: alpha-new(5)
```

- Assert `first.get("A-1").name().equals("alpha")`.
- Assert `last.get("A-1").name().equals("alpha-new")`.
- Assert `first.size() == 2`.
- Nêu rõ test dùng **nguồn List tuần tự**, không chuyển sang `HashSet` rồi vẫn giữ kỳ vọng.

### 13.3. Test cộng dồn và lựa chọn ưu tiên

- Assert `totals.get("A-1") == 7` với dữ liệu quantity 2 và 5.
- Nếu dùng comparator, kiểm tra bản ghi thắng theo **giá trị comparator**, không so sánh map theo thứ tự iterator.
- Thêm case bằng điểm/timestamp để kiểm tra tie-break, không để kết quả phụ thuộc cách gộp.

### 13.4. Test unmodifiable và null

Ví dụ mảnh code trong method, giả định `result` là unmodifiable map và `value` có kiểu tương ứng:

```java
boolean blocked = false;
try {
    result.put("new-key", value);
} catch (UnsupportedOperationException expected) {
    blocked = true;
}
if (!blocked) {
    throw new AssertionError("Map unexpectedly mutable");
}
```

Đây là mã minh họa, không phải file chạy độc lập nếu thiếu biến. Với null, kiểm tra `NullPointerException` ở collector Java 10 thay vì dựa vào cách xử lý null của một implementation khác.

### 13.5. Đừng so sánh trực tiếp Map.toString để kiểm tra

Thay vì:

```java
// Không nên dùng làm test xác định thứ tự:
assert text.equals("{A-1=..., B-2=...}");
```

hãy kiểm tra:
- `map.size()`;
- `map.containsKey(key)`;
- `map.get(key)`;
- `map.equals(expectedMap)` nếu chỉ quan tâm các cặp khóa–giá trị.

Thứ tự duyệt của map không được đảm bảo nếu API không hứa hẹn.

## 14. Checklist thiết kế và code review

- [ ] Key đã được định nghĩa đúng theo domain, có canonicalization nhất quán?
- [ ] Có thể xuất hiện duplicate key sau normalization hoặc join nhiều nguồn không?
- [ ] Nếu trùng là lỗi, có dùng overload hai mapper và test lỗi rõ ràng không?
- [ ] Nếu trùng hợp lệ, mergeFunction mô tả **chính sách** (first/last/sum/max), không chỉ được thêm vào để “hết lỗi”?
- [ ] Chính sách first/last có nguồn tuần tự và thứ tự thực sự được xác định không?
- [ ] Nếu cần chọn latest, đã xét timestamp/version và tie-break chưa?
- [ ] Nếu cần mọi record, có dùng `groupingBy` và `List<V>` thay vì vô tình làm mất bản ghi không?
- [ ] Nếu cần unmodifiable map, có dùng `toUnmodifiableMap` hoặc đóng băng sau collect không?
- [ ] Nếu dùng `groupingBy`, đã xét cả mutability của **map ngoài** và **list con** chưa?
- [ ] Có key hoặc value null không; dữ liệu thiếu đã được xử lý đúng nghiệp vụ?
- [ ] Nếu cần thứ tự hiển thị, đã có contract riêng thay vì dựa vào `HashMap`/`toUnmodifiableMap`?
- [ ] Key có immutable về `equals/hashCode` và value mutable có bị chia sẻ ngoài ý muốn không?
- [ ] Nếu chạy song song, mergeFunction có side effect không, có tính kết hợp/tính xác định không?
- [ ] Các kiểm thử có cover collision, empty input, duplicate, null, tie-break và tính unmodifiable không?

**Gợi ý review có cơ sở:** “Ở đây chuẩn hóa SKU thành chữ hoa sẽ làm A-1 và a-1 thành cùng key. `toMap` hai đối số sẽ lỗi khi dữ liệu này xuất hiện; đề xuất xác định xem đó là duplicate bất hợp lệ hay cần cộng dồn quantity, rồi thể hiện chính sách bằng overload/kiểu đầu ra rõ ràng.”

**Không nên review:** “Thêm `(a,b)->b` vào mọi `toMap` để hết lỗi duplicate.” Cách này có thể âm thầm làm mất dữ liệu và che lỗi nghiệp vụ.

## 15. Các sai lầm thường gặp

| Sai lầm | Cách sửa |
|---|---|
| Nghĩ mọi item có mã riêng trước chuẩn hóa | Chuẩn hóa key trước, test duplicate sau chuẩn hóa |
| Dùng `toMap(key,value)` trên dữ liệu có thể trùng mà không định nghĩa chính sách | Xác định duplicate là lỗi hay hợp lệ; chọn merge hoặc grouping |
| Dùng `(a,b)->b` để “lấy bản mới nhất” | So sánh timestamp/version với tie-break thực sự |
| Mong mergeFunction nhận key | Merge function chỉ nhận hai **value**; key cần lấy từ value hoặc tiền xử lý |
| Cộng dồn số bằng merge nhưng bỏ qua tràn số | Chọn kiểu số và quy tắc kiểm tra tràn phù hợp |
| Dùng `toMap` và giả định luôn trả `HashMap` mutable | Nếu cần map cụ thể, dùng overload có factory; nếu cần read-only, dùng `toUnmodifiableMap` |
| Dùng `toUnmodifiableMap` với null | Xử lý key/value null trước collect theo hợp đồng |
| Nghĩ unmodifiable map khiến mọi value bất biến | Value mutable vẫn có thể thay đổi |
| Nghĩ `groupingBy(..., toUnmodifiableList())` làm cả map unmodifiable | Phải đóng băng map ngoài riêng khi cần |
| Dùng `Map.copyOf(LinkedHashMap)` và đòi giữ iteration order | Không có cam kết thứ tự của unmodifiable map kết quả |
| Merge function trả null nhưng không biết nó xóa mapping | Xem ngữ nghĩa `Map.merge`, tránh null nếu muốn luôn giữ key |
| So sánh chuỗi `Map.toString()` làm contract | Test membership/value thay vì thứ tự không được bảo đảm |
| Dùng key mutable có `hashCode` đổi theo trạng thái | Chọn key bất biến, kiểm soát hash/equality |
| Dùng concurrent collector nhưng giữ policy phụ thuộc “bản cuối” | Rà soát lại encounter order, side effect và tính kết hợp |

## 16. Tự kiểm tra có đáp án

**Câu 1.** Với `List.of("a","a")` và `Collectors.toUnmodifiableMap(Function.identity(), String::length)`, kết quả là map một phần tử hay ném lỗi?

**Đáp án:** `IllegalStateException` vì có duplicate key và overload hai đối số không có mergeFunction.

**Câu 2.** `(oldValue, newValue) -> oldValue` có nghĩa gì?

**Đáp án:** Giữ giá trị đang có khi gặp cùng key. Nếu dùng để biểu đạt “bản đầu”, cần nguồn có thứ tự xác định và cách xử lý phù hợp.

**Câu 3.** `(oldValue, newValue) -> newValue` có bảo đảm chọn bản ghi có timestamp lớn nhất không?

**Đáp án:** Không. Đây là lựa chọn theo thứ tự gộp, không theo timestamp; muốn newest cần comparator/logic theo timestamp.

**Câu 4.** Nếu hai bản ghi quantity 2 và 5 cùng key, `Integer::sum` cho kết quả nào?

**Đáp án:** 7, nếu giá trị mapper là các số `Integer` tương ứng và phép cộng không tràn.

**Câu 5.** `toUnmodifiableMap` có cho key hoặc value null không?

**Đáp án:** Không. Mapper trả null khiến collector ném `NullPointerException`.

**Câu 6.** Muốn một key tra cứu mọi event liên quan, chọn `Map<String, Event>` hay `Map<String, List<Event>>`?

**Đáp án:** `Map<String, List<Event>>` và thường dùng `groupingBy`, thay vì bỏ bớt event bằng một merge chọn thắng.

**Câu 7.** `groupingBy(..., toUnmodifiableList())` đã làm map ngoài read-only chưa?

**Đáp án:** Chưa. Nó chỉ tạo các list con không cho sửa; có thể dùng `Map.copyOf` để đóng băng map ngoài khi đầu vào phù hợp.

**Câu 8.** Tại sao `Map.copyOf(LinkedHashMap)` không thể dùng làm cam kết thứ tự key?

**Đáp án:** Unmodifiable map từ `Map.copyOf` không hứa giữ iteration order của nguồn.

**Câu 9.** Nếu `mergeFunction` trả null trong collector có quy tắc `Map.merge`, chuyện gì có thể xảy ra?

**Đáp án:** Mapping có khóa trùng tương ứng có thể bị loại bỏ. Đừng dùng null để “ưu tiên bản ghi” nếu nghiệp vụ không muốn xóa mapping.

**Câu 10.** Vì sao cần key bất biến về `equals/hashCode`?

**Đáp án:** Nếu các field dùng tính hash/equality thay đổi khi key đã nằm trong hash-map, tra cứu theo key có thể cho kết quả sai hoặc không tìm thấy.

**Câu 11.** Khi chạy parallel stream, có thể giả định hàm merge với side effect lên shared list an toàn không?

**Đáp án:** Không. Cần chính sách kết hợp không side effect, có tính xác định và phù hợp xử lý song song.

**Câu 12.** Nếu code cần map có thứ tự chèn key và cho sửa, dùng overload nào?

**Đáp án:** `Collectors.toMap(keyMapper, valueMapper, mergeFunction, LinkedHashMap::new)`, với stream có encounter order phù hợp và xử lý xung đột rõ ràng.

## 17. Nguồn chính thức

- [Oracle Java SE 21 — `Collectors.toMap` và `toUnmodifiableMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collectors.html): overload hai/ba/bốn đối số, `IllegalStateException` khi duplicate key, mergeFunction, null và `Since: 10` của `toUnmodifiableMap`.
- [Oracle Java SE 21 — `Collectors.groupingBy`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collectors.html#groupingBy(java.util.function.Function,java.util.stream.Collector)): nhiều giá trị cho cùng key, downstream collector.
- [Oracle Java SE 21 — `Map.merge`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html#merge(K,V,java.util.function.BiFunction)): quy tắc kết hợp giá trị và xóa mapping nếu kết quả merge null.
- [Oracle Java SE 21 — `Map.copyOf`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): tạo map không cho sửa từ map đã có.
- [Oracle Java SE 21 — `LinkedHashMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html): thứ tự duyệt key theo insertion-order hoặc access-order được cấu hình.
- [Oracle Java SE 21 — `Stream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html): encounter order và quy tắc pipeline/collect.
- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395): record là cú pháp ổn định từ Java 16 được dùng cho ví dụ Java 17+, không phải một tính năng của Java 10.

**Ghi nhớ:** Một lookup table từ Stream chỉ đúng khi **khóa được định nghĩa chuẩn**, **chính sách duplicate được viết rõ** và **kiểu kết quả phản ánh đúng yêu cầu**. `toUnmodifiableMap` (Java 10) thích hợp cho map read-only, ném lỗi nếu trùng mà không có merge và từ chối null. Hãy chọn fail-fast, first, last, aggregate, comparator hoặc grouping dựa trên nghiệp vụ; đừng để một merge tùy tiện âm thầm che mất dữ liệu.