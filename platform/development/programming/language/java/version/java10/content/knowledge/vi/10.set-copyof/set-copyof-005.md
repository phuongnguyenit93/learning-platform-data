# `Set.copyOf`: `NullPointerException` khi nguồn hoặc phần tử tập hợp là `null`

## 1. Quy tắc cần nhớ

`Set.copyOf(Collection<? extends E> source)` được bổ sung từ **Java 10** và vẫn là API tiêu chuẩn trong Java hiện đại. Nó nhận một `Collection`, trả về một **`Set` không sửa được** (*unmodifiable set*) chứa các phần tử khác nhau của nguồn tại thời điểm gọi.

**Hai trường hợp bắt buộc ném `NullPointerException`:**

1. **Chính đối tượng nguồn là `null`**: ví dụ `Set.copyOf(source)` khi `source == null`.
2. **Nguồn có ít nhất một phần tử `null`**: ví dụ `Set.copyOf(Arrays.asList("A", null, "B"))`.

Không có ngoại lệ cho `HashSet`, `ArrayList`, `LinkedHashSet` hay một `Collection` khác được phép lưu `null`. **Khả năng chấp nhận `null` của nguồn không được kế thừa sang `Set.copyOf`**.

Mặt khác, **phần tử trùng nhau nhưng khác `null` không gây lỗi**: `Set.copyOf(List.of("A", "A", "B"))` hợp lệ và chỉ giữ một giá trị tương đương `"A"`. Phân biệt nguyên nhân để không chẩn đoán nhầm `NullPointerException` với lỗi về trùng lặp.

> **Phạm vi:** Bài này tập trung vào `Set.copyOf` và quy tắc `null`. Các ví dụ chỉ dùng kiến thức/API Java vẫn còn áp dụng; chương trình chạy đầy đủ tương thích Java 10 trở lên và có thể chạy bằng JDK 17+.

## 2. Chữ ký, đầu vào và đầu ra

Chữ ký phương thức trong `java.util.Set`:

~~~java
static <E> Set<E> copyOf(Collection<? extends E> coll)
~~~

Đây là **chữ ký API rút gọn**, không phải khai báo cần tự viết vào chương trình. `coll` phải là một `Collection` **khác `null`** và mọi phần tử trong nó cũng phải **khác `null`**.

~~~java
import java.util.Collection;
import java.util.List;
import java.util.Set;

// Các dòng sau đặt bên trong một phương thức:
Collection<String> source = List.of("A", "B");
Set<String> result = Set.copyOf(source);

// Hoặc dùng suy luận kiểu biến cục bộ:
var result2 = Set.copyOf(source); // Set<String>
~~~

`Set.copyOf` nhận `Collection` chứ không chỉ `Set`. Ví dụ, một `List<String>` hợp lệ có thể được chuyển thành `Set<String>` không sửa được. `Iterable<String>` thuần túy **chưa đủ** để truyền trực tiếp nếu nó không đồng thời là `Collection`.

Đầu ra có những tính chất cần biết:

- **Không sửa được:** các thao tác thay đổi tập hợp như `add` hay `remove` bị từ chối bằng `UnsupportedOperationException`.
- **Không chứa `null`:** mọi phần tử được chấp nhận lúc tạo đều khác `null`.
- **Không có phần tử trùng theo `equals`:** nếu nguồn chứa các phần tử bằng nhau, chỉ một phần tử đại diện được giữ lại.
- **Không cam kết thứ tự duyệt:** không dựa vào `toString()` hoặc iterator để suy đoán thứ tự.
- **Không phản ánh thay đổi cấu trúc nguồn về sau:** với nguồn có thể sửa, một phép `add`/`remove` trên nguồn sau khi tạo bản sao không cập nhật tập kết quả.

## 3. Trường hợp 1 — cả nguồn là `null`

~~~java
import java.util.Collection;
import java.util.Set;

// Ví dụ trong phương thức:
Collection<String> source = null;

// Set<String> snapshot = Set.copyOf(source);
// Nếu thực thi: ném NullPointerException
~~~

Biến `source` có **kiểu khai báo hợp lệ `Collection<String>`**, nhưng giá trị tham chiếu là `null`. `Set.copyOf` cần một đối tượng `Collection` để lấy các phần tử, vì thế phép gọi bị từ chối.

Dù một `Set` rỗng có thể được tạo bằng `Set.of()`, `Set.copyOf(null)` **không tự xem nguồn thiếu là rỗng**. `null` và collection rỗng là hai trạng thái khác nhau:

~~~java
Collection<String> empty = java.util.List.of();
var safe = Set.copyOf(empty); // Hợp lệ: Set rỗng

Collection<String> missing = null;
// var unsafe = Set.copyOf(missing); // Ném NullPointerException
~~~

**Một tình huống phổ biến:** phương thức tìm dữ liệu trả về `null` để biểu thị “chưa có dữ liệu”, sau đó kết quả được truyền ngay vào `Set.copyOf`:

~~~java
Collection<String> loadTags() {
    return null; // Ví dụ về nguồn thiếu; không phải thiết kế khuyến nghị.
}

// Trong phương thức gọi:
// var tags = Set.copyOf(loadTags()); // Ném NullPointerException
~~~

*`loadTags` là phương thức minh họa đặt trong lớp. Không nên dùng cách trả về `null` này nếu API thực sự có thể trả về một collection rỗng thay thế.* Khi có quyền thiết kế API, ưu tiên trả về collection rỗng thay vì `null` nếu ý nghĩa nghiệp vụ là “không có phần tử”.

## 4. Trường hợp 2 — nguồn tồn tại nhưng có phần tử `null`

Một collection khác có thể **cho phép** `null`. Chẳng hạn, `ArrayList` và `HashSet` có thể chứa `null`. Tuy nhiên, `Set.copyOf` kiểm tra quy tắc riêng của nó.

### `ArrayList` hoặc danh sách có `null`

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

var source = new ArrayList<String>();
source.add("A");
source.add(null); // ArrayList cho phép
source.add("B");

// var copied = Set.copyOf(source);
// Nếu thực thi: NullPointerException
~~~

Điểm quan trọng: **lỗi xuất hiện lúc gọi `Set.copyOf`**, không phải ở dòng `source.add(null)` trong ví dụ này.

Tương tự, `Arrays.asList` có thể tạo một danh sách chứa `null`:

~~~java
var source = java.util.Arrays.asList("A", null, "B");
// var copied = java.util.Set.copyOf(source); // NullPointerException
~~~

Kiểu generic `List<String>` **không đảm bảo các phần tử khác `null`**. Tham số kiểu `String` mô tả loại đối tượng, nhưng hệ thống kiểu Java không tự loại bỏ `null` khỏi mọi `List<String>`.

### `HashSet` có `null`

~~~java
var source = new java.util.HashSet<String>();
source.add("A");
source.add(null); // HashSet cho phép một phần tử null

// var copied = java.util.Set.copyOf(source);
// Ném NullPointerException dù đầu vào đã là Set.
~~~

Đây là ví dụ điển hình vì tên `Set.copyOf` có thể làm người đọc tưởng chỉ cần nguồn là một `Set` thì luôn an toàn. **Không đúng:** loại collection không quyết định việc `null` được phép đi vào tập không sửa được.

`Set.copyOf` không tự lọc bỏ `null`, không thay `null` bằng chuỗi rỗng và không diễn giải `null` như giá trị thiếu hợp lệ.

## 5. Phân biệt nơi phát sinh lỗi khi dùng `Set.of` hoặc `List.of`

Ba thao tác dưới đây không giống nhau:

| Biểu thức | Kết quả | Vì sao |
| --- | --- | --- |
| `List.of("A", null)` | `NullPointerException` **ngay tại `List.of`** | Factory `List.of` không chấp nhận `null` |
| `Set.of("A", null)` | `NullPointerException` **ngay tại `Set.of`** | Factory `Set.of` không chấp nhận `null` |
| `Set.copyOf(Arrays.asList("A", null))` | `NullPointerException` **tại `Set.copyOf`** | `Arrays.asList` cho phép danh sách chứa `null`, nhưng `copyOf` không cho |

Nếu mã là:

~~~java
// Set.copyOf(List.of("A", null));
~~~

thì biểu thức `List.of("A", null)` sẽ thất bại **trước khi** phương thức `Set.copyOf` thực sự được gọi, do Java cần đánh giá đối số trước. Do đó khi đọc stack trace, cần xác định chính xác thao tác nào ném ngoại lệ.

Còn với **phần tử trùng nhau nhưng không null**:

~~~java
var source = java.util.List.of("A", "A", "B");
var copied = java.util.Set.copyOf(source);

System.out.println(copied.size());      // 2
System.out.println(copied.contains("A")); // true
~~~

`Set.copyOf` xử lý các phần tử trùng nhau bằng cách giữ một đại diện bất kỳ của nhóm phần tử tương đương. Nó **không ném `IllegalArgumentException` chỉ vì đầu vào `Collection` có duplicate**.

Ngược lại, `Set.of("A", "A")` ném **`IllegalArgumentException`** do đối số trùng. Đừng dùng quy tắc kiểm tra duplicate của `Set.of` để suy luận sai cho `Set.copyOf`.

## 6. Nên xử lý `null` như thế nào?

Tùy hợp đồng nghiệp vụ, có **ba chiến lược khác nhau**. Không nên tự chọn “lọc bỏ” nếu `null` mang ý nghĩa cần bảo toàn.

### A. Từ chối dữ liệu thiếu (fail fast)

Khi nguồn buộc phải có và mọi phần tử buộc phải có, hãy xác thực rõ:

~~~java
import java.util.Collection;
import java.util.Objects;
import java.util.Set;

// Đoạn minh họa trong phương thức:
Collection<String> input = loadFromService();

Objects.requireNonNull(input, "tags collection must not be null");

for (var tag : input) {
    Objects.requireNonNull(tag, "tags element must not be null");
}

Set<String> tags = Set.copyOf(input);
~~~

`loadFromService()` là tên phương thức giả định trong đoạn minh họa, không phải API có sẵn. Các lệnh `Objects.requireNonNull` **chủ động kiểm tra** và có thể cung cấp thông báo dễ chẩn đoán hơn thông báo mặc định của `Set.copyOf`.

Nếu collection có thể bị thay đổi từ luồng khác trong khi xác thực/sao chép, việc kiểm tra trước **không bảo đảm** nguồn sẽ không đổi trước `copyOf`. Cần quản lý truy cập đồng thời phù hợp, không xem việc gọi `Objects.requireNonNull` là giải pháp đồng bộ.

Nếu muốn thông báo có chỉ số lỗi trong `List`, có thể duyệt bằng chỉ số và ném một ngoại lệ có ngữ cảnh. Tuy nhiên `Collection` nói chung không có chỉ số, nên với nguồn bất kỳ, có thể dùng bộ đếm khi duyệt.

### B. Loại phần tử `null`, nhưng **chỉ nếu quy tắc dữ liệu cho phép**

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

var source = new ArrayList<String>();
source.add("A");
source.add(null);
source.add("B");

var filtered = source.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.toList());

var tags = Set.copyOf(filtered); // Set<String> chứa A và B
~~~

Đây là cách làm tương thích **Java 10+**. `filter(Objects::nonNull)` chủ động bỏ qua phần tử null; `Set.copyOf` chỉ nhận đầu vào đã được chuẩn hóa.

Nếu dùng JDK 16+ và thích cú pháp ngắn, có thể thay `collect(Collectors.toList())` bằng `toList()`. Tính năng `Stream.toList()` xuất hiện muộn hơn Java 10, nên **đừng dùng nó khi dự án thật sự phải biên dịch trên Java 10**.

**Cảnh báo nghiệp vụ:** việc lọc null âm thầm làm mất dữ liệu. Nó chỉ đúng khi yêu cầu xác định rằng `null` biểu thị một phần tử rỗng cần bỏ, không phải lỗi cần báo hoặc giá trị có nghĩa.

### C. Nếu cần giữ `null` như một phần tử, **không dùng `Set.copyOf`**

Một số mô hình dữ liệu cũ hoặc tích hợp bên ngoài coi `null` là một phần tử hợp lệ. Trong trường hợp đó, dùng collection cho phép `null`, sau đó tạo bản sao cấu trúc và bọc để ngăn sửa trực tiếp:

~~~java
var source = new java.util.ArrayList<String>();
source.add("A");
source.add(null);

var snapshotWithNull = java.util.Collections.unmodifiableSet(
        new java.util.HashSet<>(source));

System.out.println(snapshotWithNull.contains(null)); // true
~~~

- `HashSet` hỗ trợ phần tử `null`.
- `new HashSet<>(source)` tạo tập hợp mới từ nguồn, loại phần tử trùng nhau và giữ tối đa một `null`.
- `Collections.unmodifiableSet(...)` trả về một **view không sửa được trên tập hợp mới tạo**. Vì tập hợp mới không được chia sẻ riêng ra bên ngoài trong ví dụ, thay đổi cấu trúc của danh sách `source` sau đó không cập nhật tập hợp kết quả.
- `snapshotWithNull` **không** phải kết quả `Set.copyOf`. Hai API có hợp đồng khác nhau về `null`.

Nếu có thể, thiết kế dữ liệu bằng giá trị đại diện rõ ràng hoặc dùng một kiểu dữ liệu biểu thị “thiếu” thay cho việc để `null` làm phần tử tập hợp. Nhưng khi cần giữ đúng hợp đồng cho phép null, cách nêu trên vẫn là API hợp lệ hiện hành, không phải mẹo dựa vào hành vi không xác định.

## 7. Ví dụ đầy đủ: từng nguyên nhân NPE và cách xử lý

Lưu chương trình vào tệp **`SetCopyOfNullDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Collections;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

public class SetCopyOfNullDemo {
    public static void main(String[] args) {
        // 1. Nguồn chính là null.
        Collection<String> absent = null;
        try {
            Set.copyOf(absent);
        } catch (NullPointerException ex) {
            System.out.println("nullSource=blocked");
        }

        // 2. Nguồn ArrayList có phần tử null.
        var source = new ArrayList<String>();
        source.add("A");
        source.add(null);
        source.add("B");

        try {
            Set.copyOf(source);
        } catch (NullPointerException ex) {
            System.out.println("nullListElement=blocked");
        }

        // 3. Ngay cả HashSet chứa null cũng không được.
        var withNull = new HashSet<String>();
        withNull.add("C");
        withNull.add(null);

        try {
            Set.copyOf(withNull);
        } catch (NullPointerException ex) {
            System.out.println("nullSetElement=blocked");
        }

        // 4. Chỉ lọc null nếu nghiệp vụ cho phép bỏ giá trị thiếu.
        var cleaned = source.stream()
                .filter(Objects::nonNull)
                .collect(Collectors.toList());

        var safe = Set.copyOf(cleaned);

        System.out.println("safeSize=" + safe.size());
        System.out.println("safeHasA=" + safe.contains("A"));
        System.out.println("safeHasB=" + safe.contains("B"));

        // 5. Phần tử trùng không làm Set.copyOf ném lỗi.
        var duplicates = Set.copyOf(Arrays.asList("A", "A", "B"));
        System.out.println("duplicateSize=" + duplicates.size());

        // 6. Set trả về không hỗ trợ sửa cấu trúc.
        try {
            safe.add("D");
        } catch (UnsupportedOperationException ex) {
            System.out.println("modifyCopy=blocked");
        }

        // 7. Cách khác khi hợp đồng thật sự cần giữ null.
        var nullableSnapshot = Collections.unmodifiableSet(
                new HashSet<>(source));
        source.remove(null);

        System.out.println(
                "nullableSnapshotHasNull=" + nullableSnapshot.contains(null));
        System.out.println("sourceHasNull=" + source.contains(null));
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**; cú pháp và các API trong chương trình đều tương thích **Java 10 trở lên**:

~~~bash
javac SetCopyOfNullDemo.java
java SetCopyOfNullDemo
~~~

Kết quả `stdout` xác định, không phụ thuộc thứ tự duyệt của `Set`:

~~~text
nullSource=blocked
nullListElement=blocked
nullSetElement=blocked
safeSize=2
safeHasA=true
safeHasB=true
duplicateSize=2
modifyCopy=blocked
nullableSnapshotHasNull=true
sourceHasNull=false
~~~

**Giải thích kết quả:**

1. `absent` là một tham chiếu `null` nên `Set.copyOf(absent)` ném `NullPointerException`.
2. `source` tồn tại, nhưng một phần tử của nó là `null` nên bản sao không được tạo.
3. `withNull` là `HashSet` có phần tử `null`, vẫn không được `Set.copyOf` chấp nhận.
4. Sau khi lọc null, tập hợp `safe` có đúng hai giá trị phân biệt `"A"` và `"B"`.
5. `Set.copyOf` gộp phần tử `"A"` trùng nhau, vì vậy `duplicateSize` bằng `2` chứ không ném `IllegalArgumentException`.
6. Lệnh `safe.add("D")` bị từ chối bằng `UnsupportedOperationException`.
7. `nullableSnapshot` không phải `Set.copyOf`; nó là tập bọc quanh một `HashSet` mới và **có thể chứa null**. Việc xóa null khỏi `source` không xóa null khỏi tập sao chép đó.

Mã cố ý **không in trực tiếp `safe` hay `duplicates`** vì `Set.copyOf` không cam kết thứ tự duyệt. Kiểm tra kích thước và tư cách thành viên cho kết quả ổn định.

## 8. Cách xác định lỗi trong ứng dụng thực tế

Khi nhận stack trace dạng `NullPointerException` quanh thao tác tạo tập hợp, hãy lần lượt kiểm tra:

1. **Đối số truyền vào có là `null` không?** Nguồn có thể đến từ API, cơ sở dữ liệu, cache hoặc một phương thức có nhánh trả về null.
2. **Nếu có đối tượng nguồn, nó có phần tử `null` không?** Đừng chỉ kiểm tra `source != null` rồi kết luận an toàn.
3. **Lỗi xảy ra ở `Set.copyOf` hay khi tạo nguồn trước đó?** Với `List.of("A", null)` hoặc `Set.of("A", null)`, ngoại lệ phát sinh ngay ở factory tạo nguồn.
4. **Dữ liệu có bị thay đổi đồng thời không?** Nếu có thể, cần cơ chế đồng bộ hoặc snapshot đầu vào ổn định, thay vì chỉ kiểm tra trước rồi sao chép khi luồng khác vẫn sửa dữ liệu.
5. **`null` mang nghĩa gì trong nghiệp vụ?** Cần từ chối, lọc bỏ, thay bằng giá trị có nghĩa, hay giữ nguyên trong cấu trúc cho phép null?

Có thể kiểm tra có null bằng một phép duyệt khi dữ liệu ổn định:

~~~java
Collection<String> source = java.util.Arrays.asList("A", null, "B");

boolean hasNull = source.stream().anyMatch(java.util.Objects::isNull);
System.out.println(hasNull); // true
~~~

*Đây là ví dụ trong phương thức.* `hasNull` chỉ cho biết trạng thái dữ liệu đã quan sát tại lần duyệt; nó không tự khóa collection khỏi chỉnh sửa đồng thời.

**Không dựa vào thông điệp ngoại lệ cụ thể.** `NullPointerException` là loại ngoại lệ được API cam kết, nhưng thông điệp, vị trí trong stack trace và chi tiết triển khai có thể khác giữa phiên bản JDK. Trong kiểm thử, hãy xác nhận **loại ngoại lệ và ngữ nghĩa dữ liệu**, không so sánh văn bản thông điệp của NPE.

**Không bắt NPE rồi mặc định trả về tập rỗng** nếu hệ thống chưa định nghĩa rõ việc thiếu nguồn hoặc chứa null tương đương “không có dữ liệu”. Cách đó có thể che giấu sai sót từ phía nguồn và khiến dữ liệu biến mất âm thầm.

## 9. Thay đổi nguồn sau khi copy thành công

Khi `Set.copyOf(source)` đã **tạo thành công**, bản sao không phản ánh thay đổi cấu trúc nguồn về sau:

~~~java
var source = new java.util.HashSet<String>();
source.add("A");
source.add("B");

var copied = java.util.Set.copyOf(source);

source.add(null); // HashSet cho phép, sau khi bản sao đã được tạo
source.remove("A");

System.out.println(copied.size());       // 2
System.out.println(copied.contains("A")); // true

// java.util.Set.copyOf(source); // Lần sao chép MỚI sẽ ném NPE vì có null
~~~

Điều kiện **không chứa null** được xét **tại lần gọi `copyOf`**. `source.add(null)` sau đó **không thể chèn null vào bản sao cũ**. Tuy vậy, nếu gọi `copyOf` một lần nữa với nguồn lúc này có null, lần mới bị từ chối.

Snapshot ở đây là **sao chép nông**, không sao chép sâu trạng thái đối tượng phần tử. Nếu phần tử là đối tượng mutable, việc sửa trạng thái của đối tượng có thể ảnh hưởng đến cách nhìn thấy phần tử qua tập đã sao chép, và đặc biệt nguy hiểm nếu sửa các trường tham gia `equals`/`hashCode`. Quy tắc không nhận null của `Set.copyOf` không khiến các đối tượng phần tử trở nên bất biến.

## 10. So sánh nhanh các tình huống

| Nguồn / lời gọi | `Set.copyOf` hoạt động? | Lý do |
| --- | --- | --- |
| `List.of()` | Có | Nguồn hợp lệ, rỗng |
| `List.of("A", "B")` | Có | Không có phần tử null |
| `Arrays.asList("A", null)` | **Không** | Nguồn có phần tử null → NPE |
| `HashSet` chứa null | **Không** | `Set.copyOf` không chấp nhận null dù nguồn có |
| Biến `Collection<String> coll = null` | **Không** | Bản thân nguồn null → NPE |
| `List.of("A", "A")` | Có | Trùng lặp được gộp trong `Set.copyOf` |
| `Set.of("A", "A")` | Không tạo được nguồn | `Set.of` ném `IllegalArgumentException` vì trùng |
| `List.of("A", null)` | Không tạo được nguồn | `List.of` tự ném NPE trước |
| `Collections.emptyList()` | Có | Nguồn rỗng hợp lệ |
| `Collections.unmodifiableSet(new HashSet<>(...))` có null | **Không** | Chỉ đọc không đồng nghĩa không có null |

**Không dùng bảng để suy ra rằng `Set.copyOf` chỉ ném NPE.** Phương thức được định nghĩa cụ thể ném `NullPointerException` cho nguồn hoặc phần tử null; ứng dụng vẫn có thể gặp ngoại lệ khác từ mã nguồn dữ liệu, các phương thức `equals/hashCode` lỗi, hoặc do vi phạm quy tắc về truy cập đồng thời. Nhưng với câu hỏi “nguồn hoặc phần tử là null”, NPE là kết quả đúng theo hợp đồng.

## 11. Bài tập tự kiểm tra

**Bài 1.** Với mã sau, dòng nào gây ngoại lệ?

~~~java
var names = new java.util.ArrayList<String>();
names.add("An");
names.add(null);

// var set = java.util.Set.copyOf(names);
~~~

**Đáp án:** Nếu bỏ chú thích, `Set.copyOf(names)` ném `NullPointerException`; `ArrayList.add(null)` trước đó hợp lệ. Không phải lỗi do tên `"An"` hoặc do kiểu generic.

**Bài 2.** Phân biệt hai câu lệnh:

~~~java
// A: Set.copyOf(java.util.List.of("A", null))
// B: Set.copyOf(java.util.Arrays.asList("A", null))
~~~

**Đáp án:** A ném NPE từ `List.of` khi tạo đối số; B tạo được danh sách chứa null, sau đó NPE từ `Set.copyOf`. Cả hai thất bại, nhưng **vị trí lỗi khác nhau**.

**Bài 3.** Kết quả có bao nhiêu phần tử?

~~~java
var result = java.util.Set.copyOf(
        java.util.Arrays.asList("A", "A", "B"));
System.out.println(result.size());
~~~

**Đáp án:** In `2`. Các phần tử trùng không gây NPE, và `Set.copyOf` chỉ giữ các giá trị phân biệt.

**Bài 4.** Nếu nghiệp vụ **bắt buộc giữ null** như một giá trị phần tử, có nên viết `Set.copyOf(collection)`?

**Đáp án:** Không. Cần một cấu trúc cho phép null và cơ chế bảo vệ khỏi chỉnh sửa phù hợp, ví dụ `Collections.unmodifiableSet(new HashSet<>(collection))` khi chỉ cần một bản sao cấu trúc không sửa được. Nếu nghiệp vụ xem null là dữ liệu không hợp lệ, hãy chủ động từ chối và nêu lý do, thay vì âm thầm bỏ nó.

## 12. Ghi nhớ

- **`Set.copyOf(null)` → `NullPointerException`.**
- **`Set.copyOf(collection)` khi bất kỳ phần tử nào là `null` → `NullPointerException`.**
- Một nguồn là `List`, `HashSet` hay `Collection` có thể chứa null; **không có nghĩa bản sao cho phép null**.
- **`Set.copyOf` không tự bỏ phần tử null**; nếu muốn lọc, phải làm rõ quy tắc dữ liệu và lọc trước.
- **Duplicate không phải nguyên nhân NPE:** `Set.copyOf` gộp phần tử trùng, còn `Set.of` với đối số trùng ném `IllegalArgumentException`.
- **Nguồn đã sửa sau khi sao chép thành công** không làm tập kết quả bị thêm null hoặc đổi thành phần.
- **`Set.copyOf` trả về tập không sửa được**, nhưng không tự làm phần tử mutable trở thành bất biến sâu.

### Tham khảo chính thức

- [Java SE 26 API — `Set.copyOf(Collection)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)): quy tắc đầu vào không được null hoặc chứa null, hành vi duplicate, kết quả không sửa được.
- [dev.java — Creating and Processing Data with Collections Factory Methods](https://dev.java/learn/api/collections-and-streams/collections-framework/factory-methods/): hướng dẫn `copyOf` và cách xử lý dữ liệu từ Java 10.
