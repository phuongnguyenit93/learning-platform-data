# Viết tài liệu khi thứ tự tự nhiên cố ý không nhất quán với `equals()` trong Java

Một lớp Java triển khai `Comparable<T>` có thể quy định **thứ tự tự nhiên** thông qua `compareTo()`. Thông thường nên thiết kế sao cho hai đối tượng so sánh bằng `0` cũng là hai đối tượng bằng nhau theo `equals()`. Tuy nhiên, Java **khuyến nghị mạnh mẽ nhưng không bắt buộc** hai quan hệ phải nhất quán. Có trường hợp nghiệp vụ chủ ý dùng một tiêu chí cho **định danh hoặc giá trị đầy đủ** và một tiêu chí khác cho **thứ tự tự nhiên**.

Khi cố ý chọn thiết kế như vậy, **tài liệu API phải nói rõ sự khác biệt**, định nghĩa chính xác ý nghĩa của `compareTo() == 0`, nêu hệ quả lên `TreeSet`/`TreeMap`, và hướng dẫn cách giữ tính duy nhất theo `equals()` nếu người dùng API cần điều đó. Chỉ ghi “implements Comparable” hoặc “sorts by priority” là chưa đủ.

## 1. Hiểu chính xác hai quan hệ

Giả sử `a` và `b` cùng thuộc lớp `T`:

- **Bằng nhau theo `equals()`**: `a.equals(b)` có nghĩa hai đối tượng cùng một giá trị logic theo hợp đồng của lớp. Nếu ghi đè `equals()`, `hashCode()` phải nhất quán: hai đối tượng bằng nhau có cùng hash.
- **Tương đương theo thứ tự tự nhiên**: `a.compareTo(b) == 0` nghĩa chúng thuộc cùng một **nhóm tương đương của phép so sánh**; trong một collection có thứ tự dùng quan hệ này, chúng được xem là trùng về mặt sắp xếp/khóa.
- **Nhất quán với `equals()`** nghĩa với **mọi** cặp `a`, `b`, hai biểu thức `(a.compareTo(b) == 0)` và `a.equals(b)` luôn cùng giá trị boolean.
- **Không nhất quán** chỉ cần tồn tại một cặp mà hai biểu thức trả kết quả khác nhau. Ví dụ `compareTo() == 0` nhưng `equals()` là `false`; chiều ngược lại cũng là một dạng bất nhất có thể gây hại.

Không nhất quán với `equals()` **không đồng nghĩa** phương thức `compareTo()` được phép tùy tiện. `Comparable` vẫn yêu cầu quan hệ thứ tự ổn định và hợp lệ: dấu của phép so sánh đảo chiều phải đối nhau, quan hệ lớn hơn phải có tính bắc cầu, và những phần tử so bằng `0` phải có cùng dấu khi so sánh với mọi phần tử thứ ba. Kết quả âm/không/dương mới quan trọng, không phải chính xác `-1`, `0`, `1`.

Một ví dụ nghiệp vụ: `RankedItem(id, priority)` có danh tính giá trị gồm cả mã `id` và `priority` (như một record), nhưng thứ tự tự nhiên **chỉ so `priority`**. Hai mục mã khác nhau cùng mức ưu tiên không bằng nhau theo `equals()`, song `compareTo()` trả `0`. Thiết kế có thể dùng được, nhưng cần công bố rõ rằng tập có thứ tự sẽ giữ **tối đa một mục trên mỗi mức ưu tiên**.

## 2. Vì sao phải ghi tài liệu rõ ràng?

`Comparable<T>` quy định thứ tự tự nhiên được dùng mặc định bởi một số API:

- `Collections.sort(list)`, `List.sort(null)` và `Arrays.sort(array)` với phần tử so sánh được bằng thứ tự tự nhiên.
- `TreeSet<E>` và `TreeMap<K,V>` khi được tạo **không truyền `Comparator`**.
- `PriorityQueue<E>` khi được tạo không truyền comparator: thứ tự ưu tiên dựa trên `compareTo()`.

Đáng chú ý, API **sắp xếp danh sách** vẫn giữ các phần tử dù `compareTo() == 0`. Nhưng `TreeSet` và `TreeMap` dùng **kết quả so sánh bằng `0` để quyết định phần tử/khóa trùng**. Đây là nguồn ngạc nhiên lớn nhất cho người sử dụng API.

| Hành vi | Khi `a.compareTo(b) == 0` nhưng `!a.equals(b)` |
| --- | --- |
| `HashSet.add(a); add(b)` | Thường giữ **cả hai**, vì đánh giá trùng theo `equals()` và hash tương ứng |
| `TreeSet` dùng thứ tự tự nhiên | Chỉ giữ **một**, lần thêm thứ hai trả `false` |
| `HashMap` dùng `a`, `b` làm hai khóa | Giữ **hai khóa** khác nhau theo `equals()` |
| `TreeMap` dùng thứ tự tự nhiên | `put(b, value2)` có thể **thay giá trị** của khóa tương đương `a` |
| `List.sort(null)` / `Collections.sort(list)` | Sắp xếp, **không loại bản ghi** cùng thứ hạng |
| `PriorityQueue` | Dùng thứ tự lấy phần tử, **không loại trùng** chỉ vì `compareTo() == 0` |

Những collection được xây dựng theo thứ tự tự nhiên vẫn vận hành nhất quán với **quy tắc so sánh** của chúng, nhưng `TreeSet`/`TreeMap` có thể không tuân trực giác và hợp đồng `Set`/`Map` được định nghĩa theo `equals()` của phần tử/khóa. Việc ghi chú giúp người gọi quyết định kiểu collection, comparator và mô hình khóa đúng.

**Hệ quả khó nhận thấy:** `treeSet.contains(x)` có thể trả `true` ngay cả khi tập không chứa phần tử nào `equals(x)`, miễn là một phần tử hiện có so sánh bằng `0` với `x`. Tương tự, `treeMap.get(x)` có thể trả giá trị của một khóa khác theo `equals()` nhưng bằng `0` theo `compareTo()`.

## 3. Điều tối thiểu phải ghi trong Javadoc

Tài liệu của `Comparable` trong Java SE 17 khuyến nghị một câu cảnh báo chuẩn cho trường hợp bất nhất có chủ ý:

> Note: this class has a natural ordering that is inconsistent with equals.

Cần ghi **cảnh báo này ở tài liệu của kiểu** (hoặc tài liệu public API dễ tìm), bên cạnh mô tả định nghĩa thứ tự. Có thể nhắc lại tại Javadoc của `compareTo()` và hướng dẫn dùng collection. Câu cảnh báo là điểm bắt đầu; tài liệu tốt phải trả lời được những điều sau:

1. **`equals()` dùng những trường nào?** Nói rõ hai đối tượng được xem là cùng giá trị khi nào.
2. **`compareTo()` dùng những trường nào và chiều thứ tự ra sao?** Ví dụ theo `priority` tăng dần; không dùng `id` để phá hòa.
3. **Khi nào `compareTo()` trả `0` dù `equals()` là `false`?** Nêu cặp minh họa cụ thể.
4. **Vì sao chủ ý thiết kế khác nhau?** Chẳng hạn nghiệp vụ muốn tạo nhóm mức ưu tiên, thay vì gộp định danh.
5. **Ảnh hưởng lên tập/map có thứ tự là gì?** Mô tả trùng phần tử, thay thế giá trị và kết quả `contains/get`.
6. **Làm thế nào nếu muốn giữ từng đối tượng khác nhau?** Chọn `HashSet`/`HashMap` khi muốn `equals()` quyết định tính duy nhất, hoặc truyền comparator nhất quán với equality vào `TreeSet`/`TreeMap` nếu thật sự cần cả thứ tự.
7. **Các giới hạn khác**: `null` có hỗ trợ không, tiêu chí có bất biến khi đối tượng nằm trong collection không, và phương thức có ổn định với mọi phiên bản không.

Không nhất thiết cần một Javadoc quá dài, nhưng người đọc phải dự đoán được hành vi collection **trước khi dùng lớp làm khóa hoặc phần tử tập hợp**.

## 4. Ví dụ tài liệu đầy đủ ngay trên lớp (Java 17+)

Trong ví dụ sau, một `record` có `id` và `priority`:

- `equals()`/`hashCode()` do record sinh tự động xét **cả hai component**.
- `compareTo()` cố tình chỉ xét `priority` để thiết lập thứ tự tự nhiên theo mức ưu tiên.
- Hai mục cùng ưu tiên nhưng khác mã ID **khác nhau theo `equals()`** và **tương đương theo thứ tự**.
- `id` được kiểm tra không null; bản thân `String` và `int` bất biến, làm quan hệ so sánh ổn định.

Lưu toàn bộ chương trình vào **`DocumentedOrderDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

/**
 * Một mục xếp theo priority tăng dần.
 *
 * <p>Hai mục bằng nhau theo equals khi cả id và priority
 * bằng nhau. Thứ tự tự nhiên chỉ xét priority; các mục
 * khác id nhưng cùng priority so sánh bằng 0.
 *
 * <p>Note: this class has a natural ordering that is
 * inconsistent with equals.
 *
 * <p>TreeSet/TreeMap không truyền Comparator coi các mục
 * cùng priority là một phần tử hoặc khóa tương đương.
 * Nếu cần giữ các id khác nhau, dùng HashSet/HashMap hoặc
 * comparator xét thêm id.
 */
record RankedItem(String id, int priority)
        implements Comparable<RankedItem> {

    RankedItem {
        Objects.requireNonNull(id, "id");
    }

    /**
     * So sánh thứ tự tự nhiên theo priority tăng dần,
     * cố ý không xét id. Trả về 0 với các id khác nhau
     * nhưng cùng priority.
     */
    @Override
    public int compareTo(RankedItem other) {
        Objects.requireNonNull(other, "other");
        return Integer.compare(priority, other.priority);
    }
}

public class DocumentedOrderDemo {
    public static void main(String[] args) {
        RankedItem a = new RankedItem("A", 10);
        RankedItem b = new RankedItem("B", 10);
        RankedItem unseen = new RankedItem("C", 10);

        System.out.println("equals: " + a.equals(b));
        System.out.println("compareTo zero: "
                + (a.compareTo(b) == 0));

        Set<RankedItem> hashed =
                new HashSet<>(List.of(a, b));
        Set<RankedItem> ordered =
                new TreeSet<>(List.of(a, b));

        System.out.println("HashSet size: " + hashed.size());
        System.out.println("TreeSet size: " + ordered.size());
        System.out.println("TreeSet contains unseen: "
                + ordered.contains(unseen));

        List<RankedItem> list =
                new ArrayList<>(List.of(a, b));
        list.sort(null);
        System.out.println("sorted list size: " + list.size());

        Map<RankedItem, String> hashMap = new HashMap<>();
        hashMap.put(a, "first");
        hashMap.put(b, "second");

        Map<RankedItem, String> treeMap = new TreeMap<>();
        treeMap.put(a, "first");
        treeMap.put(b, "second");

        System.out.println("HashMap size: " + hashMap.size());
        System.out.println("TreeMap size: " + treeMap.size());
        System.out.println("TreeMap lookup unseen: "
                + treeMap.get(unseen));
        System.out.println("TreeMap first key: "
                + treeMap.keySet().iterator().next().id());

        Comparator<RankedItem> completeOrder =
                Comparator.comparingInt(RankedItem::priority)
                          .thenComparing(RankedItem::id);
        Set<RankedItem> distinctSorted =
                new TreeSet<>(completeOrder);
        distinctSorted.add(a);
        distinctSorted.add(b);
        System.out.println("TreeSet with tiebreaker: "
                + distinctSorted.size());
    }
}
```

Biên dịch và chạy:

```bash
javac DocumentedOrderDemo.java
java DocumentedOrderDemo
```

Đầu ra:

```text
equals: false
compareTo zero: true
HashSet size: 2
TreeSet size: 1
TreeSet contains unseen: true
sorted list size: 2
HashMap size: 2
TreeMap size: 1
TreeMap lookup unseen: second
TreeMap first key: A
TreeSet with tiebreaker: 2
```

**Giải thích các kết quả ít trực quan:**

- `HashSet` và `HashMap` phân biệt `"A"` với `"B"` theo equality của record.
- `TreeSet` chỉ giữ `a` vì `b.compareTo(a) == 0`. `contains(unseen)` cũng trả `true` do `"C"` cùng `priority = 10`, dù chưa hề được thêm vào và không `equals()` với `"A"`.
- `TreeMap` coi `a`, `b`, `unseen` là các khóa tương đương theo `priority`. Lần `put(b, "second")` thay giá trị của mapping trước, nên map có kích thước `1`. Đối tượng khóa lưu lại vẫn là `a`, nên `"TreeMap first key"` là `"A"`; tra cứu bằng `unseen` nhận `"second"`.
- `List.sort(null)` chỉ sắp xếp theo thứ tự tự nhiên; danh sách **không mất phần tử**. Với hai phần tử bằng thứ tự, thuật toán sort ổn định của List cũng giữ thứ tự tương đối.
- `completeOrder` xét `priority` rồi `id`, vì vậy cùng ưu tiên nhưng khác ID được phân biệt. Với record trong ví dụ này, so sánh hai trường phù hợp định nghĩa equality dựa trên cả hai component.

**Quan trọng:** comparator `completeOrder` có thể phù hợp `equals()` **cho kiểu dữ liệu cụ thể này**, vì record equality xét đúng `id` và `priority`. Nếu equality của một kiểu khác chỉ dựa vào `id` nhưng comparator còn xét trạng thái phụ mutable, chỉ thêm `thenComparing(id)` chưa chắc đã tạo thứ tự nhất quán với equality. Cần kiểm chứng cặp quan hệ trên **mọi trường hợp**, không chỉ hai ví dụ minh họa.

## 5. Ví dụ thư viện chuẩn: `BigDecimal`

`BigDecimal` là trường hợp chuẩn, được JDK nhắc tới trong tài liệu `Comparable`:

- `new BigDecimal("2.0")` có scale `1`, `new BigDecimal("2.00")` có scale `2`.
- Chúng cùng giá trị số học, nên `compareTo()` trả `0`.
- `equals()` của `BigDecimal` xem xét cả **giá trị không chia thang và scale** nên hai đại diện có scale khác nhau có thể không bằng nhau.

Tạo file **`BigDecimalOrderDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.HashSet;
import java.util.List;
import java.util.TreeSet;

public class BigDecimalOrderDemo {
    public static void main(String[] args) {
        BigDecimal x = new BigDecimal("2.0");
        BigDecimal y = new BigDecimal("2.00");

        System.out.println("x scale: " + x.scale());
        System.out.println("y scale: " + y.scale());
        System.out.println("equals: " + x.equals(y));
        System.out.println("compareTo zero: "
                + (x.compareTo(y) == 0));
        System.out.println("HashSet size: "
                + new HashSet<>(List.of(x, y)).size());
        System.out.println("TreeSet size: "
                + new TreeSet<>(List.of(x, y)).size());
    }
}
```

Lệnh:

```bash
javac BigDecimalOrderDemo.java
java BigDecimalOrderDemo
```

Stdout:

```text
x scale: 1
y scale: 2
equals: false
compareTo zero: true
HashSet size: 2
TreeSet size: 1
```

Đó là **hành vi có chủ ý của API**, không phải lỗi Java. Với bài toán tài chính, giá trị số học và biểu diễn thập phân đôi khi mang ý nghĩa khác nhau; lập trình viên cần biết đang yêu cầu quan hệ nào. Không nên tự động gọi `stripTrailingZeros()` để “sửa” mọi trường hợp: phép chuẩn hóa có thể thay đổi scale và cách biểu diễn (kể cả dạng số mũ), tác động đến nghiệp vụ cần giữ scale ban đầu.

Văn bản chính thức: [Java SE 17 – Comparable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html) và [Java SE 17 – BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html).

## 6. Javadoc nên đặt ở đâu và viết sâu đến mức nào?

### 6.1. Tài liệu cấp lớp/record là nơi chính

Người dùng thường thấy thông tin khi tra cứu lớp trước lúc dùng nó làm khóa. Cấp lớp nên nêu:

- Quan hệ equality (những thành phần quyết định bằng nhau).
- Quan hệ thứ tự tự nhiên (những thành phần, chiều tăng/giảm).
- Câu cảnh báo chuẩn về việc không nhất quán.
- Hệ quả lên sorted collection và lựa chọn thay thế.

Nếu API công khai nhiều overload hoặc có comparator phụ trợ, tài liệu lớp cũng nên trỏ đến phương án phù hợp. Ví dụ: `Comparator.comparing(RankedItem::id)` chỉ nhất quán với equality khi ID **tự nó đủ** làm danh tính. Với record gồm `id` và `priority`, comparator chỉ dựa vào ID sẽ gộp những bản ghi cùng ID nhưng khác priority, vẫn bất nhất với equality; cần kiểm tra đủ trường nếu mục tiêu là nhất quán hoàn toàn.

### 6.2. Tài liệu `compareTo()` nói rõ quan hệ trả `0`

Ở phương thức nên mô tả giá trị âm/0/dương và đặc biệt giải thích khi trả 0, ví dụ:

> So sánh theo mức ưu tiên tăng dần. Hai mục khác ID nhưng cùng mức ưu tiên được xem là tương đương theo thứ tự và `compareTo()` trả 0.

Nếu muốn phù hợp chuẩn Javadoc, thêm các phần diễn giải `@param other`, `@return`, `@throws NullPointerException` và `@see` khi hữu ích. Không nên chỉ ghi “so sánh hai đối tượng” hoặc đưa duy nhất một ví dụ không chỉ ra điều kiện trả `0`.

Về `null`: đối với `Comparable.compareTo(null)`, cách thông thường và theo hợp đồng là ném `NullPointerException`, dù `equals(null)` luôn `false`. Nếu cần xếp các phần tử nullable của **collection**, thường dùng `Comparator.nullsFirst()` hoặc `Comparator.nullsLast()` ở nơi gọi, thay vì làm lớp chấp nhận đối tượng null trong thứ tự tự nhiên.

### 6.3. README, hướng dẫn sử dụng và ví dụ phải cùng nói một quy tắc

Javadoc chỉ có ích nếu ví dụ và tài liệu tích hợp không gây hiểu nhầm. Một mục hướng dẫn có thể viết:

- **Muốn khử trùng theo toàn bộ giá trị (`equals`)**: dùng `HashSet`/`HashMap` với `hashCode()` nhất quán.
- **Muốn phân nhóm/tối đa một giá trị theo thứ hạng**: `TreeSet`/`TreeMap` với natural ordering đó có thể phù hợp, nhưng lựa chọn phần tử giữ lại và cập nhật map phải rõ ràng.
- **Muốn vừa sắp xếp vừa giữ các phần tử phân biệt**: dùng `List.sort()` nếu được phép trùng, hoặc truyền một comparator có kết quả `0` khớp quan hệ equality cho `TreeSet`/`TreeMap`.
- **Muốn thứ tự theo thứ hạng nhưng tính duy nhất theo ID**: thường tốt hơn nên lưu trong map theo ID rồi sắp xếp các value khi cần, hoặc chọn cấu trúc phù hợp; không dùng `TreeSet` với phép so sánh chỉ xét thứ hạng và kỳ vọng nó giữ đủ ID.

Phải phân biệt **tính duy nhất** với **thứ tự hiển thị**. Một comparator nhóm theo thứ hạng có thể tốt cho phân nhóm, nhưng không tự động là định nghĩa identity tốt cho khóa.

## 7. Khi nào thực sự nên chủ ý không nhất quán?

Tình huống có thể cân nhắc:

1. **Mô hình giá trị có nhiều biểu diễn hợp lệ của cùng độ lớn**, như `BigDecimal` và scale: equality giữ thông tin biểu diễn, thứ tự tự nhiên chỉ xét độ lớn.
2. **Miền nghiệp vụ định nghĩa thứ hạng cơ bản theo một tiêu chí**, trong khi đối tượng lưu thêm thông tin phân biệt: dùng `compareTo()` để biểu diễn lớp tương đương theo thứ hạng nếu đây thực sự là khái niệm tự nhiên duy nhất.
3. **Tương thích API đã công bố**: đổi ngữ nghĩa `equals()` hay `compareTo()` của một kiểu công khai có thể là breaking change; cần tài liệu minh bạch về quan hệ đang tồn tại.

Không nên mặc nhiên chọn thiết kế bất nhất chỉ để tiết kiệm một phép so sánh phụ. Nếu lớp có nhiều cách sắp xếp hợp lý (theo ID, điểm, tên, thời gian...), hãy cân nhắc **không triển khai `Comparable`** và yêu cầu người gọi cung cấp `Comparator`. Cách này giảm nguy cơ người dùng mặc định chọn natural ordering với nghĩa không mong muốn.

Một phương án khác là cho thứ tự tự nhiên phù hợp `equals()` (ví dụ `priority` rồi `id` khi record equality đúng hai trường), và cung cấp comparator riêng `BY_PRIORITY` để phục vụ nhóm theo mức ưu tiên. Khi đó phần tài liệu vẫn cần cảnh báo rằng **Comparator này không nhất quán với equality** nếu dùng trong `TreeSet`, dù thứ tự tự nhiên của lớp nhất quán.

## 8. Hợp đồng `compareTo()` vẫn bắt buộc tuân thủ

Sự bất nhất được cho phép chỉ là khác biệt giữa **định nghĩa nhóm tương đương của thứ tự** và **định nghĩa equality**. Nó không cho phép:

- So sánh không bắc cầu, ví dụ `a < b`, `b < c` nhưng `a > c`.
- Hai đối tượng so bằng `0` nhưng khi so với đối tượng thứ ba lại trả dấu khác nhau.
- Kết quả thay đổi tùy đồng hồ, số ngẫu nhiên hoặc trạng thái mutable mà collection không kiểm soát.
- Dùng phép trừ `return a.priority - b.priority;` làm tiêu chí `int` khi có nguy cơ tràn số. Dùng `Integer.compare(a.priority, b.priority)` như ví dụ.
- Gọi `compareTo()` dựa trên một tiêu chí khác hoàn toàn từ lần này sang lần khác hoặc thay đổi tiêu chí trong khi đối tượng nằm trong `TreeSet`/`TreeMap`.

Cũng đừng sửa `hashCode()` để cố ép bằng nhau theo `compareTo()`: `hashCode()` cần phù hợp **`equals()`**, không nhất thiết phù hợp các nhóm do thứ tự tự nhiên định nghĩa. Đối với hai đối tượng `compareTo() == 0` nhưng `equals() == false`, hash **được phép bằng hoặc khác nhau**.

Nếu đối tượng có trường tham gia thứ tự tự nhiên có thể thay đổi khi đã nằm trong một sorted collection, phép tìm kiếm/thứ tự của cây có thể trở nên không còn phù hợp. Giữ khóa/tiêu chí so sánh ổn định trong suốt thời gian lưu; record và lớp bất biến thường dễ đảm bảo hơn.

## 9. Kiểm thử hợp đồng và xác minh tài liệu

Bộ test nên không chỉ xác minh một danh sách đã sắp đúng. Cần kiểm tra **những ca thể hiện sự bất nhất có chủ ý** và những quy tắc thứ tự bắt buộc:

| Trường hợp | Kỳ vọng khi tự nhiên chỉ xét `priority` |
| --- | --- |
| Cùng `id`, cùng `priority` | `equals() == true`, `compareTo() == 0`, hash bằng nhau |
| Khác `id`, cùng `priority` | `equals() == false`, `compareTo() == 0` |
| Khác `priority` | `compareTo()` âm/dương đúng chiều |
| So với chính nó | `compareTo() == 0`, `equals() == true` |
| Dãy ba mức ưu tiên 1, 2, 3 | Thứ tự bắc cầu và ổn định |
| `compareTo(null)` | `NullPointerException` theo hợp đồng |
| Hai phần tử khác ID cùng priority trong `TreeSet` | `size()` là 1 |
| Hai khóa khác ID cùng priority trong `TreeMap` | Khóa tương đương được dùng cho cùng một mapping |
| Cùng hai phần tử trong `HashSet` | `size()` là 2 |
| Cùng hai phần tử trong `List.sort(null)` | Vẫn có 2 phần tử sau sắp xếp |

Với kiểu dữ liệu phức tạp, nên bổ sung property-based tests cho đối xứng dấu, bắc cầu và tính nhất quán khi so với đối tượng thứ ba. Nếu class là API công khai, một ca regression test có thể dùng chính cặp ví dụ trong Javadoc để bảo đảm tài liệu và hành vi không bị lệch khi refactor.

Nếu nhà phát triển về sau “sửa” `compareTo()` bằng cách thêm `id` làm tiêu chí phá hòa, hai đối tượng từng so bằng `0` có thể trở thành khác nhóm. Đây **không chỉ là thay đổi hiển thị**, mà có thể làm `TreeSet` giữ thêm phần tử hoặc `TreeMap` có thêm khóa. Thay đổi như vậy cần đánh giá tương thích, cập nhật tài liệu và test chứ không tự ý xem là tối ưu nội bộ.

## 10. Mẫu checklist trước khi phát hành

- [ ] Javadoc của class công bố rõ **natural ordering intentionally inconsistent with equals** bằng câu cảnh báo chuẩn hoặc câu tương đương dễ thấy.
- [ ] Mô tả chính xác tiêu chí và chiều thứ tự; đặc biệt nói rõ **khi nào `compareTo()` trả `0`**.
- [ ] Mô tả rõ thuộc tính nào quyết định `equals()` và `hashCode()`; không sửa hash dựa trên tiêu chí so sánh riêng.
- [ ] Có ví dụ hai đối tượng `equals()` khác nhau nhưng `compareTo() == 0`, hoặc chiều bất nhất thực sự mà lớp hỗ trợ.
- [ ] Nêu tác động tới `TreeSet` (`add`/`contains`) và `TreeMap` (`put`/`get`) khi không truyền comparator.
- [ ] Hướng dẫn lựa chọn `HashSet`/`HashMap`, `List.sort()` hoặc comparator nhất quán với equality tùy ý định.
- [ ] Kiểm thử thứ tự hợp lệ, bắc cầu, `null`, ổn định tiêu chí và bất biến của khóa trong collection.
- [ ] Nếu API có thay đổi quy tắc so sánh, cập nhật Javadoc, README, test và đánh giá tác động tương thích.

**Ghi nhớ:** một thứ tự tự nhiên có thể cố ý không nhất quán với `equals()` mà vẫn thỏa hợp đồng `Comparable`. Khi chọn thiết kế đó, tài liệu phải giải thích **định nghĩa hai quan hệ, lý do chúng khác nhau, và những hành vi collection bị ảnh hưởng**. Tránh để người dùng chỉ phát hiện sự khác biệt sau khi `TreeSet` làm mất một phần tử hoặc `TreeMap` thay một giá trị.
