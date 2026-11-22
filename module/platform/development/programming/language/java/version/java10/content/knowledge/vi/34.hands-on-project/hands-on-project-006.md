# Tạo bảng tra cứu bằng `Collectors.toUnmodifiableMap` với chính sách khóa trùng

*Chủ đề cha: Thực hành tổng hợp — Java 10. Bài Knowledge này hướng dẫn biến một luồng bản ghi thành **bảng tra cứu `Map<K,V>` không cho sửa** bằng `Collectors.toUnmodifiableMap`, đồng thời **xác định trước chính sách xử lý các bản ghi có cùng khóa**. Đây là API được giới thiệu trong Java 10 và vẫn áp dụng trong Java 17/21+; các ví dụ độc lập biên dịch với `javac --release 17`. Nội dung không dựa vào hành vi legacy hoặc các chi tiết implementation chưa được API bảo đảm.*

## 1. Bài toán thực tế

Giả sử một ứng dụng nhận danh sách sản phẩm từ file cấu hình, API hoặc database:

| SKU đầu vào | Tên hiển thị | Phiên bản | Giá (đơn vị nhỏ nhất) |
| --- | --- | ---: | ---: |
| `" a-1 "` | `"Ban cu"` | 1 | 9900 |
| `"A-1"` | `"Ban moi"` | 2 | 12500 |
| `"b-2"` | `"San pham B"` | 1 | 5000 |

Bạn muốn tra cứu sản phẩm theo mã SKU:

```java
Offer offer = lookup.get("A-1");
```

Nhưng có một vấn đề: `" a-1 "` và `"A-1"` **trùng nhau sau khi chuẩn hóa khóa**. Không thể đồng thời gán hai giá trị khác nhau cho một khóa trong `Map<String,Offer>` mà không đưa ra quyết định. Ứng dụng cần chính sách rõ ràng:

- **Từ chối dữ liệu trùng** và báo lỗi thay vì âm thầm mất bản ghi.
- **Giữ bản ghi đầu tiên** nếu thứ tự nguồn đáng tin.
- **Giữ bản ghi cuối cùng** khi nguồn được định nghĩa là log cập nhật tuần tự.
- **Chọn phiên bản mới nhất** bằng tiêu chí nghiệp vụ độc lập với thứ tự đọc.
- **Gộp giá trị** bằng phép tính phù hợp, ví dụ cộng số lượng.
- **Giữ toàn bộ bản ghi theo khóa** bằng `Map<K,List<V>>` nếu duplicate không phải lỗi.

`Collectors.toUnmodifiableMap` là một công cụ để hiện thực lựa chọn cuối của quá trình giảm `Stream` thành `Map`. Nó **không tự biết** phải chọn bản ghi nào tốt nhất hoặc vì sao khóa trùng được phép. **Chính sách khóa trùng là hợp đồng nghiệp vụ do bạn thiết kế**, không phải một “tham số tối ưu” JVM tự suy.

## 2. Mục tiêu học tập

Sau bài này, bạn sẽ:

1. Hiểu nguồn gốc và hai overload Java 10 của `Collectors.toUnmodifiableMap`.
2. Viết `keyMapper` và `valueMapper` đúng kiểu generic.
3. Nhận diện khóa trùng theo `Object.equals` sau khi mapping, không theo identity hoặc số dòng.
4. Dùng overload hai tham số để **fail-fast** bằng `IllegalStateException` khi có duplicate.
5. Dùng overload ba tham số và `BinaryOperator<U> mergeFunction` để chọn first/last/newest/aggregate.
6. Thiết kế chuẩn hóa SKU nhất quán bằng `strip()` và `Locale.ROOT`, đồng thời hiểu khi nào không nên fold case.
7. Biết `null` keys/values không được phép và phân biệt `null` do mapper với `null` mà merge function trả về.
8. Hiểu `Map.merge` có thể **xóa mapping khi hàm merge trả `null`** — một bẫy khó thấy.
9. Tạo một chương trình Java 17+ có đầy đủ bản ghi, duplicate, policy và bảng tra cứu cuối.
10. Xác minh Map không thể `put/remove/clear`, nhưng đối tượng value mutable vẫn có thể thay đổi từ ngoài.
11. Biết `toUnmodifiableMap` **không bảo đảm thứ tự duyệt** keys/entries.
12. Tránh merge policies thiếu tính associative/commutative trên parallel/unordered streams.
13. Biết khi nào phải dùng `groupingBy` hoặc `LinkedHashMap` thay vì ép `toUnmodifiableMap` giải mọi bài toán.
14. Kiểm tra lỗi dữ liệu nguồn, version conflicts, thứ tự, null, equality và khả năng dùng trong ứng dụng đa luồng.
15. Viết unit tests theo contract thay vì snapshot `Map.toString()` hoặc tên implementation class.

## 3. API Java 10 và hai cách gọi quan trọng

Trong `java.util.stream.Collectors` có hai overload đã được giới thiệu từ **Java 10**:

```java
public static <T, K, U>
Collector<T, ?, Map<K, U>> toUnmodifiableMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper);

public static <T, K, U>
Collector<T, ?, Map<K, U>> toUnmodifiableMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper,
        BinaryOperator<U> mergeFunction);
```

*Hai khai báo trên chỉ để đọc chữ ký generic; chúng không phải methods bạn định nghĩa lại trong class ứng dụng.*

Ý nghĩa của các tham số:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `T` | Kiểu phần tử đầu vào của stream | `Offer` |
| `K` | Kiểu khóa cuối | `String` SKU chuẩn hóa |
| `U` | Kiểu giá trị cuối | `Offer` hoặc `Integer` |
| `keyMapper` | Đổi phần tử `T` thành khóa `K` | `Offer::sku` hay `LookupPolicyDemo::canonicalSku` |
| `valueMapper` | Đổi phần tử `T` thành giá trị `U` | `Function.identity()` |
| `mergeFunction` | Gộp **hai giá trị U** khi khóa trùng | `(oldValue,newValue)->newValue` |
| Kết quả | Một `Map<K,U>` không cho sửa cấu trúc | `Map<String,Offer>` |

Đọc đúng luồng xử lý:

```text
  List<Offer> nguồn
         |
         v
  stream()
         |
         +--> keyMapper: Offer -> canonical SKU
         |
         +--> valueMapper: Offer -> value
         |
         v
  Collector tích lũy từng mapping
         |
         +--> key mới: thêm mapping
         |
         +--> key trùng: FAIL hoặc gọi mergeFunction
         |
         v
  Finisher / Map kết quả
         |
         v
  unmodifiable lookup Map<K,V>
```

**Không có overload `toUnmodifiableMap` nhận `mapSupplier` như một đối số thứ tư**. Nếu cần điều khiển loại Map hay thứ tự, xem phương án `Collectors.toMap(..., mapFactory)` kết hợp bước làm bất biến ở mục 14.

### 3.1. Kết quả không sửa được là hợp đồng API

Collector trả về `unmodifiable Map`: các thao tác mutator như `put`, `remove`, `clear` và `Map.Entry.setValue` không phải cách hợp lệ để cập nhật nó; chúng sẽ ném `UnsupportedOperationException` theo hợp đồng unmodifiable Map.

Nhưng **unmodifiable không tự bằng deeply immutable**: nếu value là một đối tượng mutable và một nơi khác vẫn giữ tham chiếu, nó có thể thay nội dung của value mà Map đang trỏ tới. Bài thực hành sử dụng Java `record` với String và các giá trị primitive để giảm rủi ro.

### 3.2. Đừng suy thứ tự Map từ nguồn stream

`Map` cuối của `toUnmodifiableMap` **không bảo đảm iteration order**. Nếu input theo `A-1` rồi `B-2`, đừng viết test:

```java
assertEquals("{A-1=..., B-2=...}", lookup.toString());
```

Đây là kiểu test mong manh vì thứ tự Map không được cam kết. Nên tra trực tiếp theo key, so với Map expected bằng `equals`, hoặc **sort keys trước khi in**.

## 4. Khóa trùng được định nghĩa bằng `equals`

Hai khóa được coi trùng khi chúng bằng nhau theo `Object.equals` trong hợp đồng `Map`. Ví dụ:

```java
String a = new String("A-1");
String b = new String("A-1");

System.out.println(a.equals(b)); // true
System.out.println(a == b);      // false
```

Đoạn trên là snippet trong method; output thứ hai là false vì hai String được tạo bởi hai `new` riêng biệt. Một collector phải xử lý trùng theo **equality contract**, không theo `==`.

Nếu khóa là class tự viết, hãy tuân thủ cặp `equals/hashCode`. Với khóa mutable, sửa các field tham gia `equals/hashCode` sau khi đưa vào Map có thể làm tra cứu không còn nhất quán. Một unmodifiable Map **không “đóng băng” object key mutable**.

### 4.1. Duplicate sau khi chuẩn hóa

Trong bảng mẫu, raw keys khác nhau:

```text
" a-1 " != "A-1"
```

nhưng sau `strip()` và `toUpperCase(Locale.ROOT)`:

```text
" a-1 " -> "A-1"
"A-1"   -> "A-1"
```

và đã trùng thật sự ở **khóa được gửi vào collector**.

Điều quan trọng: khi chuẩn hóa khóa, bạn đang **định nghĩa lại miền identity nghiệp vụ**. Với SKU ASCII không phân biệt chữ hoa/chữ thường, cách này có thể phù hợp. Với access tokens, identifiers phân biệt case, chuỗi Unicode có quy tắc locale đặc thù hoặc user handles được đặc tả khác, **không tùy tiện upper-case**, bởi có thể gây collision ngoài ý muốn.

### 4.2. Dùng `Locale.ROOT` khi rules không theo ngôn ngữ người dùng

`String.toUpperCase()` không truyền locale có thể chịu ảnh hưởng default locale của JVM. Với SKU/machine identifier đã quy định case-folding một cách culture-neutral, `Locale.ROOT` giúp tránh phụ thuộc locale cài đặt.

**Nhưng `Locale.ROOT` không tự giải quyết mọi Unicode normalization**. Nếu domain có NFC/NFKC hoặc quy tắc identifier riêng, thiết kế/kiểm thử thêm để mọi hệ thống tạo key thống nhất. Không biến “uppercase và trim” thành giải pháp toàn năng cho tên người, mã quốc tế hay chuỗi bảo mật.

## 5. Chính sách mặc định: khóa trùng là lỗi dữ liệu

Overload hai tham số:

```java
Map<String, Offer> lookup = offers.stream()
        .collect(Collectors.toUnmodifiableMap(
                Offer::sku, Function.identity()));
```

Đây là **snippet** cần biến `offers` và record `Offer` đã khai báo. Nếu hai phần tử tạo cùng key, collector sẽ ném **`IllegalStateException`** khi thực hiện `collect`.

Thực tế nghiệp vụ có nhiều tình huống nên **không tự ghi đè**:

- Mã product ID được tuyên bố unique.
- Country code, currency code, permission ID được quản trị duy nhất.
- Mã cấu hình routing, tên event type hoặc tên feature flag.
- Một khóa bị trùng có thể cho thấy dữ liệu nguồn bị hỏng hoặc tích hợp sai.

**Fail-fast** giúp phát hiện vấn đề trước khi công bố bảng tra cứu. Nó tránh “last write wins” âm thầm làm thất thoát dữ liệu.

### 5.1. Ngoại lệ khác với `Map.of`

Lưu ý:

| API | Khi trùng khóa |
| --- | --- |
| `Collectors.toUnmodifiableMap(k,v)` | `IllegalStateException` |
| `Collectors.toUnmodifiableMap(k,v,merge)` | Gọi `mergeFunction`; có thể trả kết quả hoặc ném lỗi riêng |
| `Collectors.toMap(k,v)` | `IllegalStateException` |
| `Map.of(...)` / `Map.ofEntries(...)` | `IllegalArgumentException` do duplicate khi tạo factory Map |
| `Map.copyOf(existingMap)` | Bản thân input Map đã có key duy nhất theo cấu trúc Map, nên không tồn tại “hai entries cùng một key” trong một Map hợp lệ |

Không gộp mọi trường hợp thành một exception type và không assert exact exception message, vì thông điệp lỗi có thể thay đổi giữa các bản JDK.

### 5.2. Không đồng nghĩa Stream sẽ “sửa bản ghi trùng”

Khi collector ném lỗi, **không có Map kết quả thành công để caller sử dụng**. Nó không tự de-duplicate, không giữ tất cả values và không báo lại một danh sách đầy đủ những duplicate keys.

Nếu muốn một **báo cáo tất cả khóa trùng**, nên có bước validate/`groupingBy` riêng trước khi build lookup, thay vì chỉ dựa vào việc catch một exception đầu tiên.

## 6. Chính sách có chủ đích: `mergeFunction`

Overload ba tham số:

```java
Map<K, V> result = source.stream().collect(
        Collectors.toUnmodifiableMap(
                keyMapper,
                valueMapper,
                (oldValue, nextValue) -> choose(oldValue, nextValue)));
```

Đây là schematic snippet: `source`/`choose`/types phải được khai báo theo ứng dụng; không copy thành file Java chạy độc lập.

Mỗi khi collector gặp một key đã có mapping, các values tương ứng được xử lý bằng `BinaryOperator<V>`. **Hàm chỉ nhận hai values**, không trực tiếp nhận key. Nếu cần log chính xác key, bạn có thể giữ key trong value object hoặc chạy bước validate trước.

### 6.1. Bảng chính sách thường dùng

| Chính sách | Hàm merge | Khi phù hợp | Cảnh báo |
| --- | --- | --- | --- |
| **Fail on duplicate** | Không có merge, overload 2 tham số | Unique key là bất biến | Dừng collect bằng IllegalStateException |
| **First wins** | `(oldV,newV) -> oldV` | Dòng đầu có quyền ưu tiên theo nguồn có encounter order | Không mặc định có “first” trên unordered stream |
| **Last wins** | `(oldV,newV) -> newV` | Dữ liệu là chuỗi updates đã được sắp thứ tự rõ | Không dựa vào last khi thứ tự input không đáng tin |
| **Highest version** | `BinaryOperator.maxBy(comparator)` | Có version/timestamp/priority được định nghĩa | Phải xử lý ties và data conflicts |
| **Sum** | `Math::addExact` khi `V=Integer` | Đếm/sum số lượng | Có thể ném ArithmeticException khi overflow |
| **Combine list** | Ưu tiên `groupingBy` + freeze list | Muốn giữ mọi bản ghi | Không làm mất thông tin rồi gọi là “dedup” |
| **Strict equality** | Nếu values giống hệt giữ một; nếu khác ném lỗi | Duplicate giống nhau được phép, conflict bị chặn | Phải xác định tiêu chí “giống hệt” |
| **Domain-specific priority** | Comparator từ quy tắc nghiệp vụ | Giá trị có trạng thái/nguồn ưu tiên | Không được dùng “newer” nếu timestamp không đáng tin |

Một hàm merge nên **pure**, tức không thay đổi state bên ngoài, không phụ thuộc thứ tự scheduling và có hành vi thống nhất với các permutations/partitions có thể xảy ra nếu bạn muốn dùng parallel reduction.

### 6.2. First wins

```java
var first = ordered.stream().collect(
        Collectors.toUnmodifiableMap(
                keyMapper, valueMapper,
                (left, right) -> left));
```

Đây là snippet minh họa. Nó giữ value được truyền là **left** tại phép merge. Với một **sequential, ordered stream** và collector làm việc theo thứ tự nguồn, đây là policy thường được gọi first-wins.

**Không đồng nhất “first-wins” với ưu tiên version thấp, dữ liệu mới hay bản ghi có priority cao.** Nếu thứ tự nguồn không có tính nghiệp vụ, first-wins chỉ là cách làm mất một giá trị tùy thuộc vào thứ tự đầu vào. Với một unordered stream, kết quả giữ “đầu tiên” có thể không xác định như bạn kỳ vọng.

### 6.3. Last wins

```java
var last = ordered.stream().collect(
        Collectors.toUnmodifiableMap(
                keyMapper, valueMapper,
                (left, right) -> right));
```

Nó chọn value được truyền là **right** tại phép merge. Để diễn giải là “bản ghi mới nhất trong feed”, feed phải có **encounter order** nhất quán và thực sự đại diện thứ tự cập nhật.

Nếu dữ liệu đến từ database query không có `ORDER BY`, hoặc từ một `HashSet`, không thể gọi phần tử cuối là “latest” chỉ vì nó được xử lý sau trong một lần chạy.

### 6.4. Chọn phiên bản cao nhất

```java
Comparator<Offer> ranking =
        Comparator.comparingInt(Offer::version)
                .thenComparing(Offer::label)
                .thenComparingLong(Offer::priceCents)
                .thenComparing(Offer::sku);

BinaryOperator<Offer> newest =
        BinaryOperator.maxBy(ranking);
```

Đây là snippet sử dụng record `Offer` định nghĩa ở mục 8. Nó chọn maximum theo `version`, nếu bằng version thì tiếp tục so `label`, `priceCents` và raw `sku` để tạo **tie-breaker** có thứ tự cho các trường trong record.

Trong hệ thống thực, việc dùng **label theo thứ tự từ điển làm tie-breaker** chỉ là quy tắc minh họa có tính xác định, **không tự trở thành quy tắc nghiệp vụ tốt nhất**. Có thể cần thay bằng source priority hoặc ID ổn định. Nếu hai bản cùng version nhưng giá khác nhau được xem là conflict, hãy ném lỗi thay vì âm thầm chọn tên “lớn hơn” theo từ điển.

### 6.5. Gộp số lượng bằng phép cộng

```java
Map<String, Integer> counts = Stream.of("a", "a", "b")
        .collect(Collectors.toUnmodifiableMap(
                Function.identity(),
                s -> 1,
                Math::addExact));
```

Đây là snippet trong method, cần imports `java.util.Map`, `java.util.function.Function`, `java.util.stream.Stream` và `Collectors`.

Kết quả theo lookup:

```text
counts.get("a") == 2
counts.get("b") == 1
```

`Math.addExact` không lặng lẽ wrap khi tổng vượt `int`. Nếu lượng count có thể rất lớn, cân nhắc `Long`/`Math.addExact` cho long, big integers hoặc streaming aggregation phù hợp.

## 7. Chính sách phải được xác định **trước khi** collect

Một cách thiết kế thực tế:

1. **Khóa có được phép trùng không?** Nếu không: dùng overload 2 tham số, dừng bằng lỗi.
2. **Bản ghi trùng giống hệt nhau có được bỏ bớt không?** Nếu có: định nghĩa equality giá trị.
3. **Có tiêu chí “mới nhất” thật sự?** So version, timestamp hoặc business priority có quy tắc tie.
4. **Có cần giữ toàn bộ lịch sử?** Chuyển sang `Map<K,List<V>>`, không chọn một `V`.
5. **Có cần thứ tự hiển thị cố định?** Dùng sorted keys khi render hoặc cấu trúc Map có hợp đồng order riêng.
6. **Có cần cập nhật liên tục?** Unmodifiable snapshot là cấu trúc đọc; cập nhật bằng build snapshot mới, không `put` trực tiếp.
7. **Có duplicate conflicts đáng báo lỗi?** Ghi số liệu/validation, không chỉ silent last-wins.
8. **Có khả năng chạy parallel/unordered?** Dùng merge associative và tốt nhất commutative, hoặc tạo một order rõ trước khi chọn.

**Đây là phần thiết kế nghiệp vụ, không phải việc JVM sẽ “tự tối ưu” thành một chính sách đúng.**

## 8. Chương trình Java 17+ chạy độc lập: `LookupPolicyDemo.java`

Ví dụ chính sử dụng record `Offer`: nó chỉ giữ các field đơn giản `String`, `int`, `long`, giúp value gần với immutable snapshot. Input gồm cùng SKU xuất hiện hai lần với version khác nhau.

Tạo file **`LookupPolicyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public final class LookupPolicyDemo {
    record Offer(String sku, String label,
                 int version, long priceCents) {}

    static String canonicalSku(Offer offer) {
        String key = offer.sku().strip()
                .toUpperCase(Locale.ROOT);
        if (key.isBlank()) {
            throw new IllegalArgumentException("blank sku");
        }
        return key;
    }

    public static void main(String[] args) {
        var input = new ArrayList<>(List.of(
                new Offer(" a-1 ", "Ban cu", 1, 9900),
                new Offer("A-1", "Ban moi", 2, 12500),
                new Offer("b-2", "San pham B", 1, 5000)));

        // 1. Strict mode: có collision sau chuẩn hóa.
        try {
            input.stream().collect(
                    Collectors.toUnmodifiableMap(
                            LookupPolicyDemo::canonicalSku,
                            Function.identity()));
        } catch (IllegalStateException ex) {
            System.out.println("strictDuplicate="
                    + ex.getClass().getSimpleName());
        }

        // 2. Chính sách chọn version/giá trị theo ranking.
        Comparator<Offer> ranking =
                Comparator.comparingInt(Offer::version)
                        .thenComparing(Offer::label)
                        .thenComparingLong(Offer::priceCents)
                        .thenComparing(Offer::sku);
        BinaryOperator<Offer> newest =
                BinaryOperator.maxBy(ranking);

        Map<String, Offer> index = input.stream()
                .collect(Collectors.toUnmodifiableMap(
                        LookupPolicyDemo::canonicalSku,
                        Function.identity(), newest));

        // Luôn sort keys trước khi in: Map không hứa order.
        System.out.println("keys="
                + index.keySet().stream().sorted().toList());
        System.out.println("A-1=" + index.get("A-1").label());
        System.out.println("B-2=" + index.get("B-2").label());

        try {
            index.put("C-3",
                    new Offer("C-3", "Khac", 1, 100));
        } catch (UnsupportedOperationException ex) {
            System.out.println("writeBlocked="
                    + ex.getClass().getSimpleName());
        }

        // Thêm bản ghi vào source không tự thay snapshot.
        input.add(new Offer("C-3", "Them sau", 1, 100));
        System.out.println("snapshotHasC3="
                + index.containsKey("C-3"));

        // 3. First/last chỉ có ý nghĩa khi source ordered.
        var ordered = List.of("a:1", "a:2", "b:3");
        Map<String, String> first = ordered.stream()
                .collect(Collectors.toUnmodifiableMap(
                        s -> s.split(":")[0],
                        s -> s.split(":")[1],
                        (left, right) -> left));
        Map<String, String> last = ordered.stream()
                .collect(Collectors.toUnmodifiableMap(
                        s -> s.split(":")[0],
                        s -> s.split(":")[1],
                        (left, right) -> right));

        System.out.println("firstA=" + first.get("a"));
        System.out.println("lastA=" + last.get("a"));

        // 4. Gộp các giá trị nguyên.
        var sum = Stream.of("a", "a", "b")
                .collect(Collectors.toUnmodifiableMap(
                        Function.identity(), s -> 1,
                        Math::addExact));
        System.out.println("countA=" + sum.get("a"));

        // 5. Mapper null bị từ chối.
        try {
            Stream.of("a").collect(
                    Collectors.toUnmodifiableMap(
                            s -> null,
                            Function.identity()));
        } catch (NullPointerException ex) {
            System.out.println("nullKey="
                    + ex.getClass().getSimpleName());
        }
        try {
            Stream.of("a").collect(
                    Collectors.toUnmodifiableMap(
                            Function.identity(),
                            s -> null));
        } catch (NullPointerException ex) {
            System.out.println("nullValue="
                    + ex.getClass().getSimpleName());
        }

        // 6. Trả null từ merge: xóa mapping đang có.
        var removed = Stream.of("a", "a", "a")
                .collect(Collectors.toUnmodifiableMap(
                        Function.identity(), s -> 1,
                        (left, right) -> null));
        System.out.println("nullMergeThird="
                + removed.get("a"));

        System.out.println("parallelStable="
                + input.parallelStream().collect(
                        Collectors.toUnmodifiableMap(
                                LookupPolicyDemo::canonicalSku,
                                Function.identity(), newest))
                        .get("A-1").label());
    }
}
```

**Điều kiện:** Java 17+ (records và `Stream.toList()` đã là APIs ổn định). Không cần Maven/Gradle hoặc thư viện ngoài JDK.

Biên dịch/chạy:

```bash
javac --release 17 LookupPolicyDemo.java
java LookupPolicyDemo
```

Stdout đã kiểm thử trên OpenJDK 24, khi source như trên:

```text
strictDuplicate=IllegalStateException
keys=[A-1, B-2]
A-1=Ban moi
B-2=San pham B
writeBlocked=UnsupportedOperationException
snapshotHasC3=false
firstA=1
lastA=2
countA=2
nullKey=NullPointerException
nullValue=NullPointerException
nullMergeThird=1
parallelStable=Ban moi
```

**Tại sao output tin cậy?** Các dòng truy vấn dùng khóa cụ thể hoặc danh sách keys được `sorted()`; không phụ thuộc `Map.toString()` hay iteration order. Dữ liệu `A-1` có version 1 và 2 nên hàm maxBy chọn version 2. `parallelStable` đúng trên dữ liệu này nhờ ranking có thứ tự xác định và không dựa vào arrival order để chọn phiên bản.

### 8.1. Phân tích chi tiết strict collision

`canonicalSku` chuyển `" a-1 "` và `"A-1"` thành cùng key `"A-1"`. Overload hai tham số không có merge function nên phát hiện duplicate và ném `IllegalStateException` khi terminal operation `collect` chạy.

Không có nghĩa bản ghi đầu tiên được giữ hoặc loại khỏi kết quả. **Không có kết quả Map thành công** trong nhánh strict này. Ngoại lệ được catch và trình diễn; code production có thể đẩy lỗi lên bước import/validation thay vì chỉ in tên exception.

### 8.2. Vì sao version 2 thắng?

`BinaryOperator.maxBy(ranking)` giữ một value có ranking cao nhất. Version 2 lớn hơn version 1 nên `index.get("A-1")` là bản ghi `"Ban moi"`. Key cuối vẫn là canonical `"A-1"`, không phải raw SKU có dấu cách.

Với records cùng version, ranking tiếp tục qua label/price/sku. Việc này làm chọn lựa reproducible theo một thứ tự, nhưng sản phẩm thật cần quyết định **nếu cùng version có metadata khác nhau thì có chấp nhận hay báo conflict**. Không dùng so tên từ điển làm tie-breaker nếu domain yêu cầu reject.

### 8.3. Kết quả sau khi mutate nguồn

Sau khi `index` được tạo, code thêm `"C-3"` vào `input`. `index.containsKey("C-3")` vẫn false. Đây là hành vi snapshot của quá trình stream reduction; Map không là một live view của danh sách nguồn.

Tuy nhiên, collector dùng `Function.identity()` nên value objects ban đầu vẫn có cùng tham chiếu với objects của source. Trong demo, `Offer` là record có fields String/primitive nên không có mutable nested state; với một value chứa `List` mutable, nội dung bên trong vẫn có thể thay dù Map không cho `put`.

### 8.4. Why `firstA` là 1 và `lastA` là 2?

Nguồn `List.of("a:1","a:2","b:3")` có encounter order rõ. Với **sequential stream**, hai bản `a` theo thứ tự 1 rồi 2. Merge first trả left (1); merge last trả right (2).

Nếu chuyển sang unordered source hoặc dùng a database query không có order contract, những tên policy first/last có thể không phản ánh “sớm nhất”/“mới nhất” về nghiệp vụ. Nên lưu timestamp/version và chọn theo comparator khi điều đó mới là ý nghĩa thật.

### 8.5. Vì sao `countA=2`?

Mỗi phần tử tạo value 1. Với key `a` xuất hiện hai lần, `Math.addExact(1,1)` trả 2. Đây là phép giảm kết quả thành `Map<String,Integer>`; map không có key trùng, chỉ có key `a` gắn với tổng 2.

### 8.6. Vì sao `nullMergeThird=1`?

Đây là bẫy cố ý:

- Phần tử `a` thứ nhất tạo mapping `a->1`.
- Phần tử `a` thứ hai gọi merge function, trả `null`, **xóa mapping a** theo semantics `Map.merge`.
- Phần tử `a` thứ ba lại gặp key hiện **không tồn tại**, nên chèn value 1 như một mapping mới.
- Kết quả `removed.get("a")==1`.

**Không** diễn giải hàm merge trả `null` là “bỏ qua phần tử mới và giữ giá trị cũ”. Đó là behavior khác, cần `(old,next)->old`.

## 9. Null policy: `null` key/value không được phép

Cả hai overload `Collectors.toUnmodifiableMap` **không chấp nhận khóa hoặc giá trị `null`** từ các mapping functions. Nếu `keyMapper` hoặc `valueMapper` trả `null`, `collect` ném `NullPointerException`.

Cần phân biệt ba loại `null`:

1. **Mapper function object `null`**: truyền `null` thay cho `Function` hoặc `mergeFunction` ở overload 3 gây `NullPointerException` theo contract tạo collector.
2. **Mapped key/value là `null`**: bị từ chối khi collect theo `Collectors.toUnmodifiableMap`.
3. **`mergeFunction` trả `null`**: theo semantics của `Map.merge` có thể **loại bỏ mapping đang có**, như ví dụ ba lần `a`; đây không phải một stored null value trong result.

Điểm (3) đặc biệt dễ nhầm. Kết quả unmodifiable Map vẫn không lưu `null` values. Nhưng một merge callback trả null có thể khiến một khóa biến mất khỏi bảng.

### 9.1. Kiểm tra dữ liệu trước khi collect

Với bản ghi nguồn:

```java
static String requireSku(Offer offer) {
    Objects.requireNonNull(offer, "offer");
    String raw = Objects.requireNonNull(
            offer.sku(), "sku");
    String key = raw.strip().toUpperCase(Locale.ROOT);
    if (key.isBlank()) {
        throw new IllegalArgumentException("blank sku");
    }
    return key;
}
```

Đây là snippet cần `import java.util.Objects;` và record `Offer`. Nó cho lỗi cụ thể hơn với row thiếu SKU hoặc SKU trống.

**Không** làm `Objects.toString(value)` để tự biến null thành chuỗi `"null"` làm key: như vậy có thể tạo một key chung và che lỗi dữ liệu. Nếu source có optional field thật, hãy thiết kế chính sách **bỏ qua bản ghi không đủ điều kiện** bằng `filter`/validation có báo cáo, chứ không mặc định gộp chúng vào key `null`.

### 9.2. Stream có phần tử `null`

Nếu `Stream<Offer>` chứa chính phần tử null, `Offer::sku`/`canonicalSku` có thể ném `NullPointerException` trước khi collector hoàn thành. `toUnmodifiableMap` không phải một “null sanitizer” toàn năng. Hãy xác định contract input: chấp nhận null elements không, bỏ hay reject ở đâu, và có cần biết số dòng lỗi không.

### 9.3. `Map.get` và missing key

Do `toUnmodifiableMap` không có stored null values, `lookup.get("MISSING")==null` thường được diễn giải là **không có mapping**. Nếu muốn API rõ ý nghĩa:

```java
Optional<Offer> found =
        Optional.ofNullable(lookup.get("MISSING"));
```

Đây là snippet cần `java.util.Optional`. Nó không sửa Map, chỉ biểu diễn kết quả tra cứu có thể vắng mặt. Không nói `getOrDefault` hoặc `Optional` sẽ xử lý duplicate trong bước build; đó là hai giai đoạn khác.

## 10. `Map.merge` là nền tảng ngữ nghĩa của overload ba tham số

Tài liệu `Collectors.toUnmodifiableMap(k,v,mergeFunction)` chỉ rõ merge function dùng để xử lý các values cùng key theo hợp đồng `Map.merge`.

Khái niệm:

```text
Nếu key chưa có mapping:
  map[key] = newValue

Nếu key đã có oldValue:
  merged = mergeFunction(oldValue, newValue)
  nếu merged != null:
      map[key] = merged
  nếu merged == null:
      loại bỏ mapping key
```

Đây là pseudocode giải thích, **không** là mã nguồn triển khai bên trong `Collectors` hay cách nó phải chia partitions.

### 10.1. Hệ quả với ba/bao nhiêu phần tử trùng

Nếu dùng `(old,next)->null`, số lần xuất hiện chẵn có thể làm mapping biến mất, số lần lẻ có thể còn một value. Khi thay đổi thứ tự/grouping của parallel reduction, behavior phức tạp hơn. Đó hiếm khi là chính sách business mong muốn.

**Không dùng null return như policy “không ghi đè”**. Nếu muốn giữ old value, trả `old`. Nếu muốn xóa vì business yêu cầu, phải thiết kế chính xác cancellation/tombstone semantics, phân biệt rõ “không có mapping” với “một value có trạng thái deleted”, và kiểm thử parallel/ordering.

### 10.2. Merge function không thể tự nhận key

`BinaryOperator<U>` chỉ nhận `U` và `U`. Nếu cần conflict message kiểu “SKU A-1 trùng ở dòng 4 và 9”, không thể trông đợi một tham số key có sẵn trong merge lambda.

Các cách phù hợp:

- Giữ canonical key/row/source metadata trong `U` (value record).
- Chạy pre-validation bằng grouping/counting theo key trước rồi tạo Map.
- Dùng một quá trình imperative index-building có thông tin key nếu cần chi tiết lỗi theo dòng.
- Chuyển sang `Map<K,List<U>>` để audit nguồn trước khi chọn.

Đừng dùng side-effect global counter/log trong merge function rồi giả định số lần gọi và thứ tự callback là một hợp đồng cố định, nhất là với parallel streams.

## 11. Xây policy latest đúng cách: version, ties và consistency

Một comparator tốt cần phản ánh **quy tắc nghiệp vụ**:

```java
Comparator<Offer> priority =
        Comparator.comparingInt(Offer::version)
                .thenComparingLong(Offer::priceCents)
                .thenComparing(Offer::label)
                .thenComparing(Offer::sku);

BinaryOperator<Offer> choose =
        BinaryOperator.maxBy(priority);
```

Đây là snippet sử dụng record `Offer` đã định nghĩa. Version là tiêu chí chính; các trường còn lại ở ví dụ chỉ tạo tie-break order. Trên production, nếu giá cao hơn **không** có nghĩa bản ghi tốt hơn, đừng đặt giá làm tiêu chí nghiệp vụ.

### 11.1. Khi phải fail nếu cùng version có conflict

Giả sử hai bản ghi có cùng canonical SKU và cùng version nhưng values khác:

```text
(A-1, "Ban moi", version=2, price=12500)
(A-1, "Ban moi", version=2, price=13000)
```

Nếu domain quy định một version có **một payload duy nhất**, nên reject conflict thay vì chọn giá lớn hơn. Ví dụ merge logic schematic:

```java
(oldValue, nextValue) -> {
    if (oldValue.version() == nextValue.version()) {
        if (!oldValue.equals(nextValue)) {
            throw new IllegalArgumentException(
                    "conflicting records at same version");
        }
        return oldValue;
    }
    return oldValue.version() > nextValue.version()
            ? oldValue : nextValue;
}
```

Đây là lambda snippet có kiểu value `Offer`. Nó chỉ an toàn khi bạn đã quy định rõ thế nào là “giống hệt”, và khi các values cho cùng canonical key thật sự có comparable version fields. Nếu chọn version cao hơn rồi bỏ bản conflict của version thấp, lỗi lịch sử có thể không bị phát hiện; chính sách audit có thể cần kiểm tra **tất cả** duplicates trước khi giảm.

### 11.2. Nếu timestamp bằng nhau?

Không suy `Instant.now()` tại lúc collect là “thời điểm bản ghi được tạo”, cũng không dựa vào network arrival order khi đồng hồ nguồn có thể lệch. Với event streams, thường cần event ID, logical sequence number, source priority hoặc timestamp có contract rõ. Quy tắc tie phải nằm trong thiết kế API và test.

### 11.3. “Mới nhất” không có nghĩa “cuối cùng trong stream”

- **Latest version**: chọn bản ghi có field version lớn nhất theo comparator.
- **Last encountered**: chọn phần tử đến sau trong encounter order.
- **Most recent timestamp**: chọn theo timestamp trong dữ liệu.
- **Highest source priority**: chọn theo ranking nguồn (ví dụ admin overrides automation).

Bốn chính sách có thể cho **bốn kết quả khác nhau**. Không đặt tên lambda `lastWins` rồi mô tả nó là “luôn lấy version mới nhất”.

## 12. Algebra của merge và kết quả parallel streams

Trong stream reduction, `mergeFunction` có thể được áp khi tích lũy hoặc khi ghép các partial results. Nếu phép kết hợp thiếu tính **associative**, kết quả có thể lệch khi chia data theo partitions.

### 12.1. Tính kết hợp (associative)

Một hàm merge `f` associative khi:

```text
f(f(a, b), c) == f(a, f(b, c))
```

theo ngữ nghĩa values. Những ví dụ thường phù hợp:

- Chọn maximum theo một **total ordering ổn định**.
- Cộng số nguyên trong miền không overflow, hoặc dùng phép cộng có xử lý overflow rõ.
- Ghép danh sách theo một thứ tự có contract (khi lưu ý vấn đề concurrency/order).
- First-wins hay last-wins là các phép chọn associative theo thứ tự toán hạng, **nhưng không commutative**.

Ví dụ **không associative**: `(a,b)->a-b`. Với a=10,b=3,c=1:

```text
(10 - 3) - 1 = 6
10 - (3 - 1) = 8
```

Không dùng phép trừ làm merge aggregator rồi kỳ vọng kết quả parallel giống sequential trong mọi phân hoạch.

### 12.2. Tính giao hoán (commutative)

`f(a,b)==f(b,a)` là tính giao hoán. Nếu muốn giảm phụ thuộc thứ tự trên unordered streams, chọn hàm kết hợp **cả associative và commutative** khi có thể.

Ví dụ `maxBy` với comparator có thứ tự toàn phần rõ cho các giá trị khác nhau thường có hai tính chất trên đối với **giá trị được chọn**. Nếu comparator trả 0 cho hai **records khác nhau**, `maxBy` có thể chọn một trong hai theo thứ tự; vậy hãy thiết kế tie policy sao cho tie chỉ xảy ra khi values thực sự tương đương hoặc đặt điều kiện fail conflict.

**First/last wins không commutative**. Nếu nguồn không có encounter order, đừng xem kết quả là xác định theo ý “bản đầu” hoặc “bản cuối”.

### 12.3. Side effects trong merge nguy hiểm

Không dùng:

```java
(oldValue, nextValue) -> {
    System.out.println("duplicate happened");
    globalCounter++;
    return nextValue;
}
```

làm bộ đếm duy nhất trong parallel collector rồi kỳ vọng một số lượt gọi/thứ tự in giống nhau trên mọi JDK; đoạn này chỉ minh họa anti-pattern, không phải code production. Đặc biệt, `globalCounter++` không an toàn nếu nhiều threads cùng cập nhật.

Hãy dùng một pass pre-validation/grouping hoặc metrics pipeline riêng có semantic độc lập; giữ merge function **pure và stateless**.

### 12.4. Parallel không mặc định nhanh hơn

`toUnmodifiableMap` là non-concurrent reduction. Khi chạy parallel, worker có thể tạo partial maps và **combiner** phải gộp keys — có thể tốn chi phí lớn với nhiều khóa. Không mặc định `parallelStream()` nhanh hơn `stream()`.

Nếu throughput thật sự cần parallel, benchmark đúng workload và so với `toConcurrentMap`, nhưng nhớ `toConcurrentMap` có **hợp đồng map mutability khác** và không tự trả unmodifiable result. Sau khi collect có thể dùng `Map.copyOf` nếu cần snapshot không sửa được và không có null keys/values. Luôn kiểm tra merge semantics và thread-safety của các functions.

### 12.5. Với unordered input, sắp thứ tự nếu cần

Nếu domain thật sự yêu cầu “bản ghi có timestamp lớn nhất”, comparator theo timestamp sẽ ổn hơn dựa vào encounter order. Nếu yêu cầu “bản ghi đầu tiên theo sequence number tăng”, hãy sort theo sequence number **được dữ liệu cung cấp** hoặc validate uniqueness/sequence, rồi xử lý tuần tự theo policy. Không dùng `HashMap`/`Set` iteration làm thứ tự nghiệp vụ.

## 13. Unmodifiable Map không phải deep immutable object graph

`toUnmodifiableMap` bảo đảm không sửa được **cấu trúc Map**. Nhưng value có thể là mutable:

```java
record Folder(String id, List<String> files) {}

List<String> mutableFiles = new ArrayList<>();
mutableFiles.add("a.txt");
Folder value = new Folder("folder-1", mutableFiles);
```

Đây là snippet, cần imports List/ArrayList. Record không cho gán lại field `files`, nhưng **List bên trong vẫn mutable** nếu bạn lưu nó trực tiếp.

Để tạo value snapshot chắc chắn hơn:

```java
Folder safe = new Folder(
        value.id(), List.copyOf(value.files()));
```

`List.copyOf` tạo danh sách unmodifiable và từ chối null elements; nếu elements là mutable objects, chỉ có sự bất biến nông. Tùy domain có thể cần các immutable records và nested snapshots.

### 13.1. Map snapshot và source alias

Collector tạo result mới, nhưng `Function.identity()` **không clone value objects**. Nếu source array/list thêm phần tử sau collect, result không cập nhật. Nếu source vẫn giữ tham chiếu tới một mutable value object đã đưa vào Map, các method của object đó vẫn có thể sửa state.

**Đừng gọi `Map.copyOf` hoặc `toUnmodifiableMap` là deep copy của toàn bộ object graph.** Chỉ những lớp có immutable value semantics thật sự mới giúp bảng tra cứu gần với immutable snapshot.

### 13.2. Thread safety

Unmodifiable Map có key/values immutable và được **safe publication** thì thường rất tiện để chia sẻ làm lookup read-only giữa nhiều threads. Nhưng collector **không tự cung cấp giao thức hot update thread-safe**. Nếu cần reload bảng tra cứu, xây **snapshot mới** và publish qua một `volatile` reference, `AtomicReference<Map<K,V>>` hoặc synchronization theo contract, thay vì cố sửa Map cũ.

Không dùng chính đối tượng returned Map làm lock/identity dựa trên class implementation; unmodifiable Map có thể là value-based, không nên giả định object identity ổn định giữa các constructions.

## 14. Khi phải giữ thứ tự: `LinkedHashMap` và unmodifiable view

`Collectors.toUnmodifiableMap` không nhận map supplier và không hứa encounter-order iteration. Nếu business muốn hiển thị **khóa theo thứ tự xuất hiện**, một cách rõ ràng:

```java
Map<String, Item> ordered = input.stream()
        .collect(Collectors.toMap(
                GroupAndAuditDemo::key,
                Function.identity(),
                (oldValue, next) -> oldValue,
                LinkedHashMap::new));

Map<String, Item> index =
        Collections.unmodifiableMap(
                new LinkedHashMap<>(ordered));
```

Đây là snippet sử dụng class/record của mục 16. Với **sequential, ordered input**, `LinkedHashMap` giữ insertion order trong cách dùng này; result unmodifiable view của một **copy riêng** nên caller không còn alias đến mutable backing map.

**Không lầm `Collections.unmodifiableMap(original)` với snapshot nếu caller còn giữ `original`**: unmodifiable view sẽ phản ánh thay đổi do người khác thực hiện trên backing map. Sao chép bằng `new LinkedHashMap<>(original)` trong một scope không để lộ backing reference giúp tránh rủi ro đó.

Nếu thứ tự mong muốn là **theo key tự nhiên**, không cần LinkedHashMap; có thể lấy `index.keySet().stream().sorted()` khi render, hoặc dùng cấu trúc sorted Map có hợp đồng riêng. Việc `Map.copyOf`/`toUnmodifiableMap` không hứa thứ tự vẫn giữ nguyên.

### 14.1. Vì sao không dùng `Map.copyOf` để bảo toàn order?

`Map.copyOf` cho unmodifiable Map, nhưng iteration order **không được đặc tả bảo đảm** như LinkedHashMap. Do đó pipeline:

```java
Map.copyOf(ordered)
```

không phải cách đáng tin để giữ thứ tự duyệt của `ordered`. Nếu order có ý nghĩa nghiệp vụ, phải chọn API có contract order rõ ở lớp tiêu thụ hoặc wrapper phù hợp.

## 15. Khi duplicate phải được giữ lại: `groupingBy`

Một bài toán khác: nhiều bản ghi có cùng SKU đều hợp lệ và phải xem được toàn bộ lịch sử. `Map<String,Offer>` với first/last/newest sẽ **mất các bản ghi khác** ở kết quả. Nếu muốn giữ mọi thứ, thiết kế:

```java
Map<String, List<Offer>> bySku = source.stream()
        .collect(Collectors.groupingBy(
                thisOrStaticKeyMapper));
```

Đây là pseudocode snippet; `thisOrStaticKeyMapper` cần thay bằng Function thật. `Collectors.groupingBy` mặc định cho map và lists mà **không hứa unmodifiable**, nên hãy freeze các lists và map khi dùng làm read-only lookup.

## 16. Chương trình Java 17+ thứ hai: audit trùng và giữ dữ liệu

Tạo file **`GroupAndAuditDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

public class GroupAndAuditDemo {
    record Item(String sku, String name, int version) {}

    static String key(Item x) {
        return x.sku().strip().toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        List<Item> input = List.of(
                new Item(" a-1 ", "Old", 1),
                new Item("B-2", "Second", 1),
                new Item("A-1", "New", 2));

        // Giữ tất cả rows theo canonical key.
        Map<String, List<Item>> groups = input.stream()
                .collect(Collectors.groupingBy(
                        GroupAndAuditDemo::key));

        // Freeze nested lists lẫn outer Map.
        Map<String, List<Item>> frozen =
                groups.entrySet().stream().collect(
                        Collectors.toUnmodifiableMap(
                                Map.Entry::getKey,
                                entry -> List.copyOf(
                                        entry.getValue())));

        System.out.println("duplicateKeys="
                + groups.entrySet().stream()
                        .filter(e -> e.getValue().size() > 1)
                        .map(Map.Entry::getKey)
                        .sorted().toList());
        System.out.println("groupA="
                + frozen.get("A-1").size());
        try {
            frozen.get("A-1").add(
                    new Item("A-1", "Third", 3));
        } catch (UnsupportedOperationException ex) {
            System.out.println("nestedWriteBlocked="
                    + ex.getClass().getSimpleName());
        }

        // Nếu thực sự cần encounter-order iteration:
        Map<String, Item> ordered = input.stream()
                .collect(Collectors.toMap(
                        GroupAndAuditDemo::key,
                        Function.identity(),
                        (oldValue, next) -> oldValue,
                        LinkedHashMap::new));

        Map<String, Item> index =
                Collections.unmodifiableMap(
                        new LinkedHashMap<>(ordered));

        System.out.println("orderedKeys="
                + new ArrayList<>(index.keySet()));
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 GroupAndAuditDemo.java
java GroupAndAuditDemo
```

Output đã kiểm thử trên OpenJDK 24:

```text
duplicateKeys=[A-1]
groupA=2
nestedWriteBlocked=UnsupportedOperationException
orderedKeys=[A-1, B-2]
```

### 16.1. Vì sao ví dụ thứ hai hữu ích?

- `groupingBy` giữ cả hai bản `A-1` trong list thay vì chọn một.
- `duplicateKeys` liệt kê đúng khóa có group size lớn hơn 1; sort để output ổn định.
- `List.copyOf` làm nested list không cho thêm/xóa.
- `toUnmodifiableMap` freeze outer map (các group keys đã unique từ bước `groupingBy`).
- `LinkedHashMap` là lựa chọn tường minh khi cần duyệt theo thứ tự khóa xuất hiện trong ordered source.
- `Collections.unmodifiableMap(new LinkedHashMap<>(ordered))` tránh để caller giữ alias trực tiếp đến backing map của wrapper.

**Không gọi `groupingBy` tự động là một immutable collector.** Nó chỉ được “đóng băng” sau các bước copy của ví dụ. Nếu `Item` có nested mutable state, vẫn cần deep-copy theo contract nghiệp vụ.

## 17. So sánh `toUnmodifiableMap` với các công cụ gần giống

| Công cụ | Duplicate policy | Mutable result? | Thứ tự | Khi dùng |
| --- | --- | --- | --- | --- |
| `toUnmodifiableMap(k,v)` | Fail `IllegalStateException` | Unmodifiable | Không bảo đảm | Build strict lookup |
| `toUnmodifiableMap(k,v,merge)` | Do merge function | Unmodifiable | Không bảo đảm | Chọn/gộp duplicate |
| `toMap(k,v)` | Fail `IllegalStateException` | Không có hợp đồng mutability cụ thể | Không bảo đảm | Reduction chung, sau đó xử lý tiếp |
| `toMap(k,v,merge,supplier)` | Do merge function | Phụ thuộc mapFactory và contract | Có thể dùng `LinkedHashMap` | Cần map type/order |
| `groupingBy(key)` | Gom thành `List` | Mặc định không hứa unmodifiable | Không bảo đảm Map iteration | Giữ toàn bộ duplicates |
| `Map.ofEntries(...)` | Fail `IllegalArgumentException` | Unmodifiable | Không bảo đảm | Tạo Map thủ công từ entries |
| `Map.copyOf(map)` | Input Map đã unique keys | Unmodifiable copy/snapshot về mappings | Không bảo đảm | Freeze một Map đã build |
| `Collections.unmodifiableMap(map)` | Input Map đã unique keys | Unmodifiable **view** | Theo backing Map | Bọc view; cẩn thận alias tới map gốc |

Lưu ý `Collectors.toMap` nói “no guarantees on type, mutability, serializability or thread safety” trong API docs; nhiều bản HotSpot hiện thực bằng `HashMap`, nhưng **không dùng chi tiết đó làm hợp đồng** khi code yêu cầu một loại Map cụ thể.

### 17.1. Có thể dùng `Map.copyOf` sau `toMap`?

Có:

```java
Map<String, Offer> tmp = source.stream()
        .collect(Collectors.toMap(
                keyMapper, valueMapper,
                mergeFunction));

Map<String, Offer> readOnly = Map.copyOf(tmp);
```

Đây là schematic snippet, cần các biến tương ứng. `Map.copyOf` từ Java 10? **Không** — `Map.copyOf` cũng được đưa vào Java 10, và ở đây là lựa chọn hữu ích khi bạn cần một bước build/tranform mutable Map rồi freeze. Nếu không có yêu cầu intermediate Map riêng, `toUnmodifiableMap` gọn hơn.

**Quan trọng:** `Map.copyOf` không deep copy values; cũng không bảo đảm iteration order. Và nếu tmp có null key/value (khi được phép bởi implementation), copyOf sẽ từ chối.

### 17.2. Có thể sửa Map sau khi collect không?

Không với `toUnmodifiableMap`. Nếu ứng dụng cần incremental updates, chọn một cấu trúc mutable có đồng bộ thích hợp, hoặc build một snapshot mới rồi publish. Đừng cố cast Map kết quả về `HashMap` để gọi mutators: type implementation không có hợp đồng và vẫn unmodifiable.

## 18. Lookup hiệu quả và an toàn trong ứng dụng

Sau khi xây index:

```java
Offer selected = index.get("A-1");
```

Lệnh này là snippet bên trong scope có `index` và `Offer`.

### 18.1. Tra cứu phải dùng cùng canonicalization

Nếu index được xây bằng upper-case/strip, query cũng phải dùng cùng logic:

```java
String queryKey = rawSku.strip()
        .toUpperCase(Locale.ROOT);
Offer selected = index.get(queryKey);
```

Nếu build sử dụng canonical "A-1" nhưng truy vấn " a-1 ", `Map.get` không tự chuẩn hóa nên trả null. Tốt hơn là tạo **một utility/service method duy nhất** để canonicalize cả insert và lookup, không copy-paste hai hàm có thể lệch về sau.

### 18.2. Missing key không phải duplicate

Khóa không tồn tại lúc `get` khác với khóa trùng lúc `collect`. Có thể dùng:

```java
Offer selected = index.getOrDefault(
        key, defaultOffer);
```

hoặc:

```java
Optional<Offer> selected =
        Optional.ofNullable(index.get(key));
```

Đây là snippets; xác định rõ default/Optional semantics. Không dùng `getOrDefault` để “giải quyết duplicate” vì duplicate đã được xử lý **khi build Map**.

### 18.3. Keys không nên chứa state mutable

Nếu key là `record CompositeKey(String tenant, String sku)` với fields immutable, việc tra cứu theo `equals/hashCode` có cơ sở ổn định. Nếu dùng một POJO có mutable ID field làm key rồi thay ID, một Map có thể không tìm thấy entry nữa, dù Map bản thân là unmodifiable.

### 18.4. Index có thật sự “constant time” không?

`Map.get` thường rất nhanh với implementation hash-based, nhưng **API không bảo đảm** mọi lookup có thời gian O(1) tuyệt đối trong mọi điều kiện/cấu trúc; performance phụ thuộc implementation, kích thước key, hashing/collisions, CPU/cache và mục tiêu workload. Chạy benchmark trên dữ liệu thật khi tra cứu là hot path.

## 19. Xử lý lỗi đầu vào và trách nhiệm báo cáo duplicate

Một import pipeline đáng tin có thể gồm:

```text
  Source records (CSV/API/DB)
          |
          v
  Validate required fields & domain invariants
          |
          v
  Canonicalize key consistently
          |
          v
  Group/audit duplicates (nếu cần chi tiết)
          |
          v
  Apply explicit business duplicate policy
          |
          v
  Collect toUnmodifiableMap
          |
          v
  Validate size/expected keys and publish snapshot
```

**Các câu hỏi trước production:**

- Nếu có 5 duplicates cùng key, bạn muốn 1 lỗi, 5 cảnh báo, hay giữ cả 5?
- Nếu duplicate có cùng version nhưng giá khác, chọn/deny theo quy tắc nào?
- Nếu key là string phân biệt case, có chắc upper-case an toàn?
- Nếu source có blank SKU, bạn drop, reject hay dùng fallback key được phê duyệt?
- Nếu policy là last-wins, encounter order có được hệ thống nguồn bảo đảm?
- Nếu stream parallel, merge function có deterministic và thread-safe không?
- Nếu một value mutable, ai có quyền thay sau khi index được publish?
- Nếu cần cập nhật lookup, có snapshot versioning và atomic publication không?

### 19.1. Không nuốt lỗi để “chương trình không bị crash”

Với dữ liệu bắt buộc unique, catch `IllegalStateException` rồi dùng Map rỗng cho production có thể làm hệ thống trả kết quả sai âm thầm. Hãy chuyển lỗi thành **validation failure** có thông tin nguồn, metric và hành động kiểm soát. Nếu có fallback, đó phải là một chính sách đã được phê duyệt (ví dụ giữ snapshot cũ đang hợp lệ).

### 19.2. Đếm duplicates đúng mà không phụ thuộc merge side effects

Có thể dùng `groupingBy` rồi lọc `group.size()>1`, như `GroupAndAuditDemo`. Chú ý khi data volume rất lớn, grouping giữ tất cả values có thể tốn RAM; nếu chỉ cần đếm, dùng một `counting` collector hoặc pass có kiểm soát. Không chọn cấu trúc giữ mọi value nếu service chỉ cần biết số lượng duplicate.

### 19.3. Validate trước khi publish snapshot

`Map` kết quả được build trong local variable, kiểm các điều kiện đầu ra như `size` và keys bắt buộc rồi mới publish sang các threads khác. Nếu collect/validate fail, giữ snapshot cũ; đừng publish một Map nửa thành công rồi đổi dần các entries, bởi API unmodifiable không được thiết kế cho việc đó.

## 20. Kiểm thử: happy path, duplicate, null, mutability, order và parallel

Với `LookupPolicyDemo` có thể kiểm các ca sau:

| Test case | Input | Expectation |
| --- | --- | --- |
| Unique keys | `A-1`, `B-2` | Map size 2, lookup từng key đúng |
| Duplicate strict | `A-1`, `A-1` | `IllegalStateException` ở collect |
| Normalize collision | `" a-1 "`, `"A-1"` | Cùng canonical key và bị xử lý theo policy |
| First wins | `a:1` rồi `a:2` | `a -> 1` trên ordered sequential source |
| Last wins | `a:1` rồi `a:2` | `a -> 2` trên ordered sequential source |
| Higher version | Version 1 rồi 2 | Version 2 được chọn |
| Same version conflicting payload | Hai values không tương đương | Lỗi hoặc tie policy được phê duyệt |
| Sum | Hai giá trị 1 | `a -> 2` |
| Mapper returns null key | `kMapper -> null` | `NullPointerException` |
| Mapper returns null value | `vMapper -> null` | `NullPointerException` |
| Merge function returns null | Hai lần cùng key | Mapping bị remove theo Map.merge |
| Unmodifiable | `put/remove/clear` | `UnsupportedOperationException` |
| Source list changed | Add phần tử sau collect | Snapshot không tự có entry mới |
| Mutable value | Đổi nội dung nested List từ alias | Outer map không cản deep mutation |
| Iteration order | Nhiều keys | Không assert thứ tự nếu dùng toUnmodifiableMap |
| Parallel | Có duplicates | Chọn policy associative/deterministic, so result |
| Empty input | `Stream.empty()` | Unmodifiable Map rỗng |
| Source has null element | `null Offer` | Domain validation hoặc mapper exception rõ |
| Invalid SKU | Blank/key thiếu | Reject hoặc policy input riêng |
| Huge data / collisions | Nhiều key dài/dup | Đo memory/throughput, bảo vệ nguồn dữ liệu |

### 20.1. Ví dụ unit tests với JUnit 5 (minh họa, không phải file standalone)

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

class LookupTest {
    @Test
    void duplicateWithoutMergeThrows() {
        var input = List.of("x", "x");
        assertThrows(IllegalStateException.class,
            () -> input.stream().collect(
                Collectors.toUnmodifiableMap(
                    Function.identity(), s -> 1)));
    }

    @Test
    void mergeAndImmutability() {
        Map<String, Integer> map =
                List.of("x", "x").stream().collect(
                        Collectors.toUnmodifiableMap(
                                Function.identity(), s -> 1,
                                Integer::sum));
        assertEquals(2, map.get("x"));
        assertThrows(UnsupportedOperationException.class,
                () -> map.put("y", 3));
    }
}
```

**Đây là class test cho dự án đã có JUnit Jupiter dependency**, không thể tự compile chỉ bằng JDK nếu chưa có JUnit 5 trên classpath/module path. Các chương trình `LookupPolicyDemo` và `GroupAndAuditDemo` ở trên mới là những file Java 17+ độc lập không cần dependencies.

### 20.2. Không assert exact exception message

Thay vì so text đầy đủ của `IllegalStateException`, nên test **loại exception**, key input gây lỗi hoặc diagnostic do bạn tự tạo. Thông điệp của JDK có thể thay đổi giữa releases mà semantic duplicate failure vẫn giống.

### 20.3. Không assert `Map.toString()` order

Dùng:

```java
assertEquals(Map.of("A-1", 1, "B-2", 2), result);
```

nếu result có kiểu `Map<String,Integer>` và mục tiêu là equality. `Map.equals` so mappings độc lập iteration order. Không viết snapshot test string `"{A-1=1, B-2=2}"` trừ khi đã cố ý sort trước khi format.

### 20.4. Test bản ghi có same-version tie

Nếu policy dùng `maxBy` chỉ theo version, hai values cùng version có thể được comparator xem là bằng nhau dù payload khác. Hãy tạo test với hai records cùng version khác label/price và xác nhận hệ thống **reject** hoặc tie-break có chủ đích. Không gọi một kết quả tùy thứ tự là “chắc chắn mới nhất”.

## 21. Hiệu năng và vận hành

### 21.1. Chi phí dữ liệu

Một Map tra cứu có footprint cho keys, values, cấu trúc map và metadata; pipeline có intermediate accumulator. Không giả định `toUnmodifiableMap` chỉ tạo đúng một object rồi không cấp phát gì khác. Implementation có thể thay đổi giữa JDKs.

Với hàng triệu bản ghi, cân nhắc:

- Dung lượng RAM và tần suất build.
- Dữ liệu đầu vào streaming hay luôn nạp toàn bộ vào List.
- Độ dài key và chi phí canonicalization.
- Phần trăm duplicate, kích thước value objects.
- Có cần giữ toàn bộ histories hay chỉ latest?
- Có concurrency ở cập nhật/publish không?
- Có giới hạn bộ nhớ container/heap khi snapshot cũ và mới cùng tồn tại?
- Có cần database/index ngoài process cho dữ liệu thay đổi nhanh?

### 21.2. Map snapshot không cập nhật đồng thời

Unmodifiable Map là lựa chọn tốt cho **read-mostly configuration/reference data**. Nếu nguồn thay mỗi giây, việc rebuild toàn bộ Map có thể tốn chi phí; tùy trường hợp dùng mutable/concurrent state có contract rõ hoặc publish snapshots theo batches.

Không tự lấy `ConcurrentHashMap` đổi tên thành “immutable” chỉ vì application hiện không gọi `put`. Một concurrent map là một kiểu cấu trúc khác có semantics khác.

### 21.3. Khi dùng parallel stream

Đừng thêm `parallel()` chỉ vì input lớn. Gộp maps và gọi merge có thể gây overhead; thứ tự source có thể ảnh hưởng first/last và side effects. Dùng benchmark với workload và JDK thực tế, cùng cấu hình CPU/memory, và verify output equality trên nhiều lần chạy.

### 21.4. Khi khóa đến từ nguồn ngoài không đáng tin

Xác định giới hạn độ dài và charset cho SKU; validate canonical form; không tin bất kỳ string có thể trở thành authorization key. Collision sau normalization có thể làm một tenant/user ghi đè record của tenant khác nếu key không bao gồm tenant identity. Khi cần isolation, sử dụng khóa ghép immutable `record Key(String tenantId, String sku)` đã chuẩn hóa từng thành phần theo policy.

Chính sách merge phải **không vô tình cấp quyền cho dữ liệu nguồn ưu tiên thấp hơn**. Nếu data từ hai systems có độ tin cậy khác nhau, thứ tự list/arrival không phải cơ chế kiểm soát quyền.

## 22. Những hiểu nhầm phổ biến

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`toUnmodifiableMap` tự bỏ duplicate.” | Overload hai tham số ném `IllegalStateException` |
| “Overload ba tham số tự chọn version mới nhất.” | Nó chỉ gọi merge function **bạn cung cấp** |
| “Trùng là `keyA == keyB`.” | Trùng theo `equals`/`hashCode` của Map key |
| “Raw SKU khác nhau thì chắc keys không trùng.” | Normalization có thể tạo collision |
| “Mọi SKU nên upper-case.” | Phụ thuộc domain; case-sensitive IDs không được fold tùy ý |
| “`Locale.ROOT` xử lý mọi Unicode identity.” | Còn normalization/domain rules khác |
| “`oldValue` là phần tử có timestamp sớm nhất.” | Không có guarantee nếu input unordered |
| “`(left,right)->left` luôn là first theo nghiệp vụ.” | Chỉ theo phép merge và encounter semantics thích hợp |
| “`(left,right)->right` luôn chọn newest version.” | Không; chọn right value, không đọc version |
| “`maxBy` theo version tự giải quyết ties.” | Version bằng nhau cần tie/reject policy rõ |
| “`null` key/value sẽ được lưu trong Map.” | Bị `NullPointerException` |
| “Merge lambda trả `null` nghĩa là bỏ qua value mới.” | `Map.merge` có thể **xóa mapping** |
| “`Map` cuối là HashMap có iteration order cố định.” | Implementation/order không được cam kết |
| “Không sửa Map được nghĩa values immutable.” | Map unmodifiable không deep freeze objects |
| “`Function.identity()` deep copy each value.” | Giữ chính references |
| “`Map.copyOf` giữ LinkedHashMap insertion order.” | Không bảo đảm |
| “`Collections.unmodifiableMap` luôn snapshot.” | Nó là view; backing Map vẫn có thể đổi |
| “`toUnmodifiableMap` có overload mapSupplier.” | Không; dùng `toMap` 4 tham số rồi wrap/copy |
| “`groupingBy` tự trả nested immutable lists.” | Không; phải freeze nếu cần |
| “`Collectors.toMap` luôn trả mutable HashMap theo API.” | API không bảo đảm type/mutability cụ thể |
| “`Map.of` duplicate ném IllegalStateException.” | Factory `Map.of` duplicate ném IllegalArgumentException |
| “Stream parallel khiến merge có thứ tự xác định mọi nơi.” | Merge policy phải đáp ứng tính chất reduction và ordering |
| “Phép trừ là merge hợp lệ vì code chạy.” | Non-associative, có thể lệch khi kết hợp khác |
| “Thêm phần tử vào source list tự thêm vào lookup.” | Collector tạo Map result, không phải live view của List |
| “Unmodifiable Map là live thread-safe dynamic database.” | Là read-only snapshot; dynamic changes cần lifecycle khác |
| “Catch duplicate exception rồi Map rỗng là an toàn.” | Có thể che lỗi dữ liệu và làm lookup sai |
| “Mọi duplicate cần bỏ bớt để tiết kiệm RAM.” | Có thể phải giữ lịch sử bằng `groupingBy` |
| “Một microbenchmark đủ chứng minh parallel luôn nhanh.” | Cần data, overhead analysis và nhiều runs |

## 23. Bài tập có lời giải

### Bài 1 — Overload nghiêm ngặt

Stream có hai bản ghi tạo cùng key `"X"`; dùng `Collectors.toUnmodifiableMap(k,v)`. Kết quả?

**Đáp án:** terminal `collect` ném `IllegalStateException`; không có Map kết quả thành công.

### Bài 2 — Null key

`keyMapper` trả `null` cho một record. Collector có lưu `null -> value` không?

**Đáp án:** không; `toUnmodifiableMap` từ chối null key và ném `NullPointerException`.

### Bài 3 — Null value

`valueMapper` trả null. Có thể dùng làm “bản ghi bị xóa” không?

**Đáp án:** không trực tiếp; mapped null value bị từ chối. Nếu domain có tombstone, mô hình một value có trạng thái deleted hoặc pipeline riêng.

### Bài 4 — Merge function trả null

Stream `["a","a","a"]`, valueMapper trả 1, merge lambda luôn trả null. `get("a")` là gì trong sequential demo?

**Đáp án:** 1; lần hai xóa mapping, lần ba thêm lại. **Không** là chính sách “giữ giá trị cũ”.

### Bài 5 — First wins

Stream ordered `["a:1","a:2"]`, merge `(old,next)->old`, giá trị key a?

**Đáp án:** `"1"` trong sequential ordered reduction.

### Bài 6 — Last wins

Cũng stream đó, merge `(old,next)->next`, giá trị?

**Đáp án:** `"2"`. Nó không tự kiểm tra version/timestamp.

### Bài 7 — Latest version

Records `X,v=3` và `X,v=5`, merge chọn max version. Kết quả?

**Đáp án:** value version 5, nếu keyMapper cho cùng canonical key và không có tie/conflict khác.

### Bài 8 — Same version, payload khác

Hai values đều version 5 nhưng price khác; policy business yêu cầu mỗi version phải nhất quán. Nên làm gì?

**Đáp án:** báo conflict/validation failure thay vì im lặng chọn giá cao hay phần tử đến sau.

### Bài 9 — Canonicalization

`" a-1 "` và `"A-1"` thành một key sau `strip().toUpperCase(Locale.ROOT)`?

**Đáp án:** có, cả hai thành `"A-1"`. Cần xử lý duplicate sau mapper.

### Bài 10 — So sánh key

Hai `new String("X")` có cùng nội dung, `==` là false nhưng `equals` là true. Collector xem trùng không?

**Đáp án:** có, vì Map key equality theo `equals`.

### Bài 11 — Unmodifiable

`Map` result đã build, gọi `put("C-3",offer)`. Kết quả?

**Đáp án:** `UnsupportedOperationException`. Build snapshot mới nếu cần thay mappings.

### Bài 12 — Mutable value

Value object chứa `List<String>` mutable; `toUnmodifiableMap` có tự biến list thành immutable?

**Đáp án:** không. Tạo nested immutable snapshots như `List.copyOf` và dùng immutable value semantics.

### Bài 13 — Order

Stream có encounter order `A`, `B`, `C`. Có được assert `map.keySet().toString()` trả `[A,B,C]` khi dùng toUnmodifiableMap?

**Đáp án:** không. API không bảo đảm iteration order; sort khi hiển thị hoặc dùng `LinkedHashMap` theo hợp đồng riêng.

### Bài 14 — Ordered map

Muốn giữ thứ tự chèn và khóa trùng first-wins. Cách nào hợp lý?

**Đáp án:** `Collectors.toMap(k,v,merge,LinkedHashMap::new)` trên ordered stream rồi bọc private copy bằng `Collections.unmodifiableMap` nếu cần read-only.

### Bài 15 — Parallel

Merge `(a,b)->a-b` có phù hợp parallel reduction không?

**Đáp án:** không, phép trừ không associative nên các cách nhóm phần tử có thể cho kết quả khác nhau.

### Bài 16 — Aggregate

Hai dòng cùng SKU có số lượng 2 và 3; merge sum. Value cuối?

**Đáp án:** 5, miễn data trong miền số và không bị overflow nếu dùng `Math.addExact`.

### Bài 17 — Audit tất cả duplicate

Muốn biết toàn bộ duplicate keys và từng bản ghi. Nên dùng first-wins rồi bỏ các bản còn lại?

**Đáp án:** không. Dùng `groupingBy` để giữ List values theo key, hoặc bước audit/validation riêng trước khi tạo lookup.

### Bài 18 — Mutable view

`Collections.unmodifiableMap(backing)` đã tạo; code khác còn giữ backing mutable và `put` vào đó. View có thể đổi?

**Đáp án:** có, view đọc xuyên qua backing Map. Sao chép private backing trước khi bọc nếu cần snapshot.

### Bài 19 — Map factory

Bạn muốn điều khiển map type trong collector `toUnmodifiableMap`. Có overload bốn tham số nhận supplier?

**Đáp án:** không. Dùng `toMap` overload có `mapFactory` rồi freeze/cover theo contract mong muốn.

### Bài 20 — Thread safety

Unmodifiable Map được publish cho nhiều threads nhưng value có mutable nested list. Có chắc mọi read đều thấy một snapshot bất biến?

**Đáp án:** không. Phải freeze nested state và safe publish snapshot; outer Map không bảo vệ mutations bên trong values.

### Bài 21 — Empty stream

`Stream.<String>empty().collect(Collectors.toUnmodifiableMap(Function.identity(),Function.identity()))` trả gì?

**Đáp án:** một Map rỗng không cho sửa. Không có duplicate, không có null mapping.

### Bài 22 — Exceptions khác nhau

`Map.of("x",1,"x",2)` và `Stream.of("x","x").collect(toUnmodifiableMap(...))` đều duplicate. Chúng ném cùng exception class không?

**Đáp án:** không. Factory `Map.of` ném `IllegalArgumentException`; collector overload hai tham số ném `IllegalStateException`.

### Bài 23 — Query normalization

Index tạo key `"A-1"` nhưng user tra bằng `" a-1 "`. Vì sao `get` có thể trả null?

**Đáp án:** `Map.get` không tự gọi mapper; phải dùng cùng canonicalization logic ở cả build và lookup.

### Bài 24 — Chính sách an toàn

Một dataset gồm cùng SKU ở hai tenant khác nhau. Dùng SKU làm key và last-wins có thể gây lỗi gì?

**Đáp án:** làm tenant này ghi đè dữ liệu tenant kia. Phải đưa tenant identity vào composite key và validate ownership/policy.

## 24. Checklist trước khi đưa bảng tra cứu vào production

1. **Đã xác định key là gì và unique ở phạm vi nào?**
2. Có canonicalization cùng logic giữa import và lookup?
3. Có quy định case-sensitive hay case-insensitive rõ ràng?
4. Có xử lý whitespace, blank và null source fields?
5. Có biết normalization có thể tạo duplicate mới?
6. Có kiểm equals/hashCode của custom key types?
7. Có tránh keys mutable hoặc các field tham gia hashCode bị thay?
8. Có dùng `toUnmodifiableMap(k,v)` khi duplicate thật sự là lỗi?
9. Có định nghĩa mergeFunction rõ ràng khi duplicate được phép?
10. Có phân biệt first/last với newest version/timestamp?
11. Có tie-break hoặc conflict detection khi version bằng nhau?
12. Có tránh merge callback có side effects và shared mutable state?
13. Có tránh trả null từ mergeFn khi chỉ muốn skip một value?
14. Có hiểu keyMapper/valueMapper null sẽ bị NPE?
15. Có validate source null elements trước khi collect?
16. Có ghi nhận duplicate key counts/issues nếu cần audit?
17. Có phân biệt failed collect với một Map rỗng hợp lệ?
18. Có tránh assert Map iteration order của toUnmodifiableMap?
19. Có sort keys hoặc dùng LinkedHashMap khi order quan trọng?
20. Có biết `Collections.unmodifiableMap` là view, không mặc định copy?
21. Có freeze nested values/list nếu cần immutable graph?
22. Có dùng records/immutable key/value objects phù hợp?
23. Có safe publish snapshot cho các threads đọc?
24. Có chính sách atomically replace khi reload lookup?
25. Có bảo đảm business identity không bị collision giữa tenants?
26. Có kiểm memory footprint và build latency trên data thật?
27. Có benchmark sequential vs parallel thay vì suy parallel nhanh hơn?
28. Có merge operator associative, deterministic theo domain?
29. Có tránh reliance on HashMap implementation/class identity?
30. Có kiểm happy path, strict dup, valid merge, conflict, null, order, immutability, parallel?
31. Có test với JDK 17+ và API đã được giới thiệu từ Java 10?
32. Có tài liệu hóa policy duplicate để người đọc không hiểu ngầm “last wins”?
33. Có tách lookup missing-key policy khỏi build duplicate policy?
34. Có lưu nguồn, revision và checksum nếu index là config/reference data quan trọng?

## 25. Tổng kết

**`Collectors.toUnmodifiableMap` (Java 10+)** là cách trực tiếp biến một `Stream<T>` thành bảng tra cứu `Map<K,V>` không cho sửa. Với overload **hai tham số**, key trùng theo `equals` gây **`IllegalStateException`** — phù hợp khi unique key là một bất biến cần bảo vệ. Với overload **ba tham số**, `mergeFunction` xác định cách xử lý trùng: first/last, max version, sum hoặc một quyết định có kiểm soát.

Ba cảnh báo quan trọng: **(1)** chuẩn hóa key có thể tạo collisions; **(2)** mapped null keys/values bị từ chối, còn merge callback trả null có thể xóa mapping theo `Map.merge`; **(3)** unmodifiable Map không tự giữ iteration order, không deep-freeze mutable values và không là một live mutable index.

Để xây bảng tra cứu đáng tin trong ứng dụng thật: định nghĩa key canonical, xác định duplicate policy theo nghiệp vụ, dùng comparator có tie/conflict handling, giữ merge functions pure/associative, audit khi cần giữ toàn bộ bản ghi, kiểm tra kết quả theo keys độc lập Map order và publish một snapshot immutable phù hợp. Khi yêu cầu là giữ **mọi** duplicates, dùng `groupingBy` + đóng băng lists/map; khi yêu cầu là **thứ tự chèn**, dùng `LinkedHashMap` theo contract riêng.

### Tài liệu tham khảo chính thức, còn áp dụng

- [Java SE 21 — Collectors.toUnmodifiableMap, cả hai overload](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collectors.html)
- [Java SE 21 — Map và Map.merge](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html)
- [Java SE 21 — Oracle guide: Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/21/core/creating-immutable-lists-sets-and-maps.html)
- [Java SE 21 — Collections.unmodifiableMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html)
- [Java SE 21 — Map.copyOf](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map))
- [Java SE 21 — Collector contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collector.html)
- [Java SE 21 — BinaryOperator.maxBy](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/function/BinaryOperator.html)
- [Java SE 21 — LinkedHashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html)
- [Java SE 17 — Objects.requireNonNull](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html)
- [Java SE 17 — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))