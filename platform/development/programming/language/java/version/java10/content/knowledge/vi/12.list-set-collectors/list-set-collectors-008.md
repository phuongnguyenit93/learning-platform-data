# Java 10 — So sánh Collectors.toUnmodifiableList/toUnmodifiableSet với Collectors.toList/toSet

## 1. Mục tiêu học tập

Khi thu thập dữ liệu từ Stream, lựa chọn collector ảnh hưởng trực tiếp đến **khả năng sửa collection**, **thứ tự phần tử**, **phần tử trùng lặp** và **xử lý null**. Java 10 bổ sung hai collector `Collectors.toUnmodifiableList()` và `Collectors.toUnmodifiableSet()` nhằm thể hiện rõ trong API rằng kết quả không cho sửa đổi. Hai collector có tên gần giống `Collectors.toList()` và `Collectors.toSet()` vốn đã có từ Java 8, nhưng **hợp đồng không giống nhau**.

Sau bài này, bạn có thể:

1. So sánh bốn collector dựa trên **cam kết trong Javadoc**, thay vì dựa vào implementation của JDK đang chạy.
2. Biết khi nào chọn danh sách giữ thứ tự và phần tử trùng, khi nào chọn tập phần tử duy nhất.
3. Phân biệt “**không cam kết khả năng sửa**” với “**bảo đảm không cho sửa**”.
4. Xử lý đúng các trường hợp `null`, nguồn có thứ tự, nguồn không có thứ tự và phần tử bằng nhau theo `equals`.
5. Dùng `Collectors.toCollection(...)` khi thực sự cần một collection mutable hoặc một loại collection cụ thể.
6. Phân biệt hai collector Java 10 với `Stream.toList()` (Java 16) và với các collection factory `List.of`/`Set.of` (Java 9).
7. Viết test ổn định khi chạy trên JDK khác hoặc thay đổi cách triển khai.

Bài sử dụng **chỉ những API và nguyên tắc vẫn có hiệu lực trong Java hiện đại**. Mã minh họa chạy độc lập được thiết kế cho Java 17+; những API riêng xuất hiện sau Java 10 được ghi rõ phiên bản.

## 2. Bản đồ phiên bản: không nhầm nguồn gốc

| API | Phiên bản xuất hiện | Ý nghĩa |
|---|---|---|
| `Collectors.toList()` | **Java 8** | Thu thành `List`; không cam kết loại cụ thể, mutability, serializability, thread-safety |
| `Collectors.toSet()` | **Java 8** | Thu thành `Set`; là unordered collector, không cam kết loại cụ thể hoặc mutability |
| `Collectors.toCollection(Supplier)` | **Java 8** | Người gọi chỉ định factory của collection đích |
| `List.of(...)` / `Set.of(...)` | **Java 9** | Tạo collection không cho sửa trực tiếp từ các phần tử |
| `Collectors.toUnmodifiableList()` | **Java 10** | Thu thành `List` không cho sửa, theo encounter order nếu có; từ chối null |
| `Collectors.toUnmodifiableSet()` | **Java 10** | Thu thành `Set` không cho sửa, unordered, từ chối null |
| `List.copyOf(...)` / `Set.copyOf(...)` | **Java 10** | Tạo collection không cho sửa từ collection đã có |
| `Stream.toList()` | **Java 16** | Terminal operation tạo `List` không cho sửa, theo encounter order nếu có |

**Mốc Java 10 cần nhớ:** hai collector có tiền tố `toUnmodifiable...` không phải tên thay thế cho hai collector `toList/toSet`. Chúng bổ sung **cam kết không cho sửa** và quy tắc **từ chối null** vào hợp đồng thu thập.

## 3. Bảng so sánh bốn collector quan trọng

| Tiêu chí | `toList()` | `toUnmodifiableList()` | `toSet()` | `toUnmodifiableSet()` |
|---|---|---|---|---|
| Kết quả | `List<T>` | `List<T>` | `Set<T>` | `Set<T>` |
| Java tối thiểu | 8 | 10 | 8 | 10 |
| Khả năng sửa kết quả | **Không được cam kết** | **Bảo đảm không cho sửa** | **Không được cam kết** | **Bảo đảm không cho sửa** |
| Thứ tự | Theo encounter order nếu stream có thứ tự | Theo encounter order nếu stream có thứ tự | **Unordered collector** | **Unordered collector** |
| Phần tử trùng | Giữ lại | Giữ lại | Loại theo hợp đồng `Set` | Loại theo hợp đồng `Set` |
| `null` | Không dựa vào một cam kết xử lý null cụ thể của collector | **Từ chối null bằng `NullPointerException`** | Không dựa vào một cam kết xử lý null cụ thể của collector | **Từ chối null bằng `NullPointerException`** |
| Loại implementation | Không bảo đảm | Không nên phụ thuộc implementation | Không bảo đảm | Không nên phụ thuộc implementation |
| Khi dùng | Cần `List`, chưa đặt yêu cầu đảm bảo mutable/unmodifiable | Cần `List` không cho sửa | Cần tập phần tử duy nhất, chưa đặt yêu cầu mutable/unmodifiable | Cần tập phần tử duy nhất, không cho sửa |

Các phương thức đều là **terminal collection strategies** dùng qua `stream.collect(...)`, ví dụ:

```java
var result = source.stream()
        .collect(Collectors.toUnmodifiableList());
```

Đây là **mảnh code**; cần `import java.util.stream.Collectors;` và biến `source` là một collection phù hợp.

### 3.1. Không cam kết mutable KHÁC với bảo đảm mutable

Một nhầm lẫn phổ biến là:

> “`Collectors.toList()` luôn trả về `ArrayList` mutable; `Collectors.toSet()` luôn trả về `HashSet` mutable.”

**Không nên coi đây là hợp đồng của Java.** Javadoc của `Collectors.toList()` và `Collectors.toSet()` nói rõ không bảo đảm kiểu implementation, mutability, serializability hoặc thread safety. Một lần chạy có thể cho thấy kết quả cho phép `add`, nhưng code phụ thuộc vào việc đó không được API bảo đảm trên mọi implementation hợp lệ.

Điều đúng:

- Nếu code **chỉ cần đọc kết quả List/Set** và không cần các ràng buộc bổ sung, `toList`/`toSet` là lựa chọn hợp lệ.
- Nếu code **bắt buộc phải có thể thay đổi kết quả**, dùng `Collectors.toCollection(ArrayList::new)` hoặc `Collectors.toCollection(HashSet::new)` hay factory của collection mong muốn.
- Nếu code **bắt buộc không được sửa kết quả**, dùng `toUnmodifiableList`/`toUnmodifiableSet`, hoặc một API khác có hợp đồng không cho sửa phù hợp.

**Điểm ra quyết định là hợp đồng phải bảo đảm**, không phải implementation hiện tại.

### 3.2. Unmodifiable KHÔNG có nghĩa bất biến sâu

`toUnmodifiableList` và `toUnmodifiableSet` chặn việc thêm, xóa hoặc thay thế phần tử **thông qua collection kết quả**. Nếu phần tử là object mutable, code vẫn có thể thay đổi thuộc tính của object đó qua tham chiếu khác (hoặc qua object lấy từ kết quả). Các collector này không sao chép sâu object.

Với `Set`, nên giữ ổn định những trường có ảnh hưởng đến `equals/hashCode`; thay đổi chúng khi phần tử nằm trong set có thể làm các thao tác membership hoạt động không đúng mong đợi.

## 4. Để nhận diện đúng “List” và “Set”, cần xét thứ tự và trùng lặp

### 4.1. Các List collector

`Collectors.toList()` và `Collectors.toUnmodifiableList()` đều thu phần tử theo **encounter order của Stream**, nếu nguồn có encounter order. Nếu nguồn là `List.of("c", "a", "b", "a")` thì kết quả danh sách có thứ tự `[c, a, b, a]` và **vẫn giữ hai phần tử "a"**.

Không có bước sort hoặc loại trùng tự động. Muốn sort, thêm `sorted(...)` trước bước collect; muốn loại trùng, thêm `distinct()` nếu phù hợp ý nghĩa nghiệp vụ.

### 4.2. Các Set collector

`Collectors.toSet()` và `Collectors.toUnmodifiableSet()` đều là **unordered collectors**. Kết quả chứa các phần tử duy nhất theo hợp đồng `Set`, không bảo đảm thứ tự duyệt, ngay cả khi stream nguồn có thứ tự.

Ví dụ, từ nguồn `["c", "a", "b", "a"]`, kết quả set chứa đúng `"a"`, `"b"`, `"c"`. Nhưng không nên khẳng định `set.iterator().next()` là `"c"` hoặc output của `set.toString()` là một chuỗi nhất định.

Với `toUnmodifiableSet`, nếu stream chứa **nhiều object bằng nhau theo `equals` nhưng khác identity**, collector được quyền giữ **một đại diện bất kỳ**. Nếu đại diện nào được giữ có ý nghĩa nghiệp vụ, hãy xác định quy tắc gộp rõ ràng trước khi thu thành Set, thay vì dựa vào thứ tự ngẫu nhiên.

### 4.3. Dùng `parallelStream()` có ảnh hưởng gì?

Với một stream có encounter order như stream của `List`, cả hai collector List vẫn có mục tiêu kết quả **theo encounter order**, kể cả khi pipeline được xử lý song song. Kết quả set thì vẫn là unordered.

Không được suy từ việc `parallelStream().collect(Collectors.toList())` chạy được mà kết luận **List trả về là thread-safe**. Stream framework quản lý quá trình giảm/gom kết quả; **collection kết quả sau khi trả về** không được collector cam kết an toàn khi nhiều thread tự ý sửa cùng lúc.

## 5. Ví dụ chạy được trên Java 17+: so sánh thực tế

Lưu tệp **`CollectorComparisonDemo.java`**:

```java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

public class CollectorComparisonDemo {

    static String mutate(Runnable operation) {
        try {
            operation.run();
            return "allowed";
        } catch (UnsupportedOperationException ex) {
            return "blocked";
        }
    }

    public static void main(String[] args) {
        var source = List.of("c", "a", "b", "a");

        var ordinaryList = source.stream()
                .collect(Collectors.toList());

        var frozenList = source.stream()
                .collect(Collectors.toUnmodifiableList());

        var ordinarySet = source.stream()
                .collect(Collectors.toSet());

        var frozenSet = source.stream()
                .collect(Collectors.toUnmodifiableSet());

        System.out.println("ordinaryList=" + ordinaryList);
        System.out.println("frozenList=" + frozenList);

        // Không in Set trực tiếp vì thứ tự duyệt không được bảo đảm.
        System.out.println("ordinarySetMembers="
                + ordinarySet.equals(Set.of("a", "b", "c")));
        System.out.println("frozenSetMembers="
                + frozenSet.equals(Set.of("a", "b", "c")));

        System.out.println("frozenListMutation="
                + mutate(() -> frozenList.add("z")));
        System.out.println("frozenSetMutation="
                + mutate(() -> frozenSet.remove("a")));

        // Khi thật sự cần mutable List, chọn factory rõ ràng.
        var mutableList = source.stream()
                .collect(Collectors.toCollection(ArrayList::new));
        mutableList.add("z");

        // Khi cần tập duy nhất với thứ tự duyệt theo lần xuất hiện đầu.
        var insertionSet = source.stream()
                .collect(Collectors.toCollection(LinkedHashSet::new));

        System.out.println("mutableList=" + mutableList);
        System.out.println("insertionSetOrder="
                + new ArrayList<>(insertionSet));

        var parallelList = source.parallelStream()
                .collect(Collectors.toUnmodifiableList());
        System.out.println("parallelKeepsOrder="
                + parallelList.equals(source));
    }
}
```

Chạy:

```bash
javac --release 17 CollectorComparisonDemo.java
java CollectorComparisonDemo
```

**Stdout chính xác** (không phụ thuộc thứ tự duyệt Set):

```text
ordinaryList=[c, a, b, a]
frozenList=[c, a, b, a]
ordinarySetMembers=true
frozenSetMembers=true
frozenListMutation=blocked
frozenSetMutation=blocked
mutableList=[c, a, b, a, z]
insertionSetOrder=[c, a, b]
parallelKeepsOrder=true
```

Phân tích:

1. `ordinaryList` và `frozenList` đều giữ encounter order và phần tử trùng từ nguồn List.
2. `ordinarySet` và `frozenSet` chứa các phần tử duy nhất, nên bài kiểm tra dùng `Set.equals`, không giả định iteration order.
3. Hai phép thử mutator trên collection **unmodifiable** bị chặn bằng `UnsupportedOperationException`. Hàm `mutate` chỉ là cách biểu diễn kết quả cho mục đích học, **không phải** cách xử lý lỗi nên dùng để lặng lẽ bỏ qua cập nhật trong business logic.
4. `mutableList` được tạo bởi `toCollection(ArrayList::new)`, nên có thể `add` theo hợp đồng `ArrayList`.
5. `insertionSet` là `LinkedHashSet`; nó duyệt theo thứ tự chèn lần đầu, nên `new ArrayList<>(insertionSet)` cho `[c, a, b]` ổn định.
6. `parallelList` dùng `toUnmodifiableList` trên nguồn List có encounter order, nên thứ tự vẫn như nguồn.

**Vì sao không thử `ordinaryList.add("z")` để kết luận toList mutable?** Vì việc đó chỉ kiểm tra hành vi của một implementation cụ thể trong lần chạy. Bài này nhấn mạnh **hợp đồng công khai**; nếu cần mutable, phải chọn `toCollection(...)`.

## 6. Null: khác biệt có thể khiến pipeline đang chạy bị lỗi

### 6.1. Hai collector Java 10 từ chối null

`Collectors.toUnmodifiableList()` và `Collectors.toUnmodifiableSet()` **không chấp nhận phần tử null**, và sẽ ném `NullPointerException` nếu collector nhận phần tử null. Điều này cần đặc biệt chú ý khi stream là kết quả của:

- Phép ánh xạ có thể trả `null`;
- Dữ liệu đọc từ API cũ cho phép `null`;
- `List` hoặc collection nguồn có phần tử `null`;
- Việc dùng `map` biến một bản ghi chưa đầy đủ thành `null`.

Đừng tạo dữ liệu null bằng `List.of("a", null)` để kiểm tra: `List.of` tự từ chối null **trước khi stream được tạo**. Có thể dùng `Arrays.asList` để xây dữ liệu minh họa chứa null, hoặc một nguồn khác cho phép.

### 6.2. Ví dụ kiểm tra null và `Stream.toList()`

Lưu tệp **`CollectorEdgeCasesDemo.java`**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.function.Supplier;
import java.util.stream.Collectors;

public class CollectorEdgeCasesDemo {

    static String nullStatus(Supplier<?> action) {
        try {
            action.get();
            return "accepted";
        } catch (NullPointerException ex) {
            return "rejected";
        }
    }

    static String mutate(Runnable action) {
        try {
            action.run();
            return "allowed";
        } catch (UnsupportedOperationException ex) {
            return "blocked";
        }
    }

    static class Item {
        String status;

        Item(String status) {
            this.status = status;
        }
    }

    public static void main(String[] args) {
        var nullable = Arrays.asList("x", null, "y");

        System.out.println("unmodifiableListNull="
                + nullStatus(() -> nullable.stream()
                        .collect(Collectors.toUnmodifiableList())));

        System.out.println("unmodifiableSetNull="
                + nullStatus(() -> nullable.stream()
                        .collect(Collectors.toUnmodifiableSet())));

        var source = List.of("x", "y", "x");

        // Stream.toList() được thêm từ Java 16.
        var newList = source.stream().toList();
        System.out.println("streamToListKeepsDuplicates="
                + newList.equals(source));
        System.out.println("streamToListMutation="
                + mutate(() -> newList.add("z")));

        // Unmodifiable collection KHÔNG deep-copy object phần tử.
        var item = new Item("draft");
        var result = List.of(item).stream()
                .collect(Collectors.toUnmodifiableList());
        item.status = "approved";
        System.out.println("elementStatus=" + result.get(0).status);
    }
}
```

```bash
javac --release 17 CollectorEdgeCasesDemo.java
java CollectorEdgeCasesDemo
```

```text
unmodifiableListNull=rejected
unmodifiableSetNull=rejected
streamToListKeepsDuplicates=true
streamToListMutation=blocked
elementStatus=approved
```

Giải thích:

- Hai collector `toUnmodifiable...` ném `NullPointerException` khi có `null`.
- `Stream.toList()` là terminal operation **Java 16**, có hợp đồng danh sách kết quả **unmodifiable**, giữ thứ tự và phần tử trùng của nguồn List.
- `elementStatus=approved` chứng tỏ collector không sao chép sâu object `Item`. Kết quả List vẫn có một phần tử như trước, nhưng thuộc tính của object có thể thay đổi.
- Ví dụ **không** dùng một vài kết quả thực nghiệm về cách `Collectors.toList/toSet` xử lý null để suy thành hợp đồng API. Nếu dữ liệu có thể null, hãy thiết lập quy tắc xử lý rõ ràng trước khi gom.

### 6.3. Cách xử lý null đúng theo nghiệp vụ

Nếu hệ thống muốn **loại bỏ** phần tử null và điều đó là hợp lệ về nghiệp vụ:

```java
var safe = nullable.stream()
        .filter(java.util.Objects::nonNull)
        .collect(Collectors.toUnmodifiableList());
```

Đây là mảnh mã trong phương thức, `nullable` là collection có thể có null và `Collectors` cần import.

Nhưng nếu `null` biểu thị một lỗi dữ liệu cần khắc phục, **không âm thầm filter**. Hãy kiểm tra, thông báo hoặc chuẩn hóa ở ranh giới dữ liệu theo quy tắc nghiệp vụ. Không có “mẹo collector” nào thay thế cho thiết kế dữ liệu null-safe.

## 7. Sự khác nhau giữa `Collectors.toList()` và `Stream.toList()`

Đây là nguồn nhầm lẫn lớn trên Java hiện đại vì **hai cách đều có chữ `toList`**:

```java
var a = stream.collect(Collectors.toList()); // Collector: Java 8
var b = stream.toList();                      // Stream method: Java 16
```

Hai dòng chỉ là **mảnh minh họa**, giả định biến `stream` là một stream phù hợp và mỗi dòng dùng một stream khác nhau; một stream không thể thực hiện terminal operation hai lần. `Collectors` cần import.

| Thuộc tính | `stream.collect(Collectors.toList())` | `stream.toList()` |
|---|---|---|
| Bắt đầu có | Java 8 | Java 16 |
| Có bảo đảm unmodifiable không? | **Không cam kết** | **Có** |
| Thứ tự kết quả | Theo encounter order nếu có | Theo encounter order nếu có |
| Có giữ phần tử trùng? | Có | Có |
| Có thể gọi `add` vào kết quả không? | **Không nên dựa vào** | **Không**, ném `UnsupportedOperationException` |
| Có cần `Collectors` import không? | Có | Không |
| Kiểu implementation | Không cam kết | Không cam kết |

Nếu muốn kết quả unmodifiable khi đang dùng `collect` và target Java 10+, hãy chọn `Collectors.toUnmodifiableList()`. Với target Java 16+, `stream.toList()` thường ngắn gọn khi cần danh sách không cho sửa và hợp đồng phù hợp.

**Không khẳng định chúng giống hệt về null và implementation.** `Collectors.toUnmodifiableList` có hợp đồng **từ chối null**; `Stream.toList` có đặc tả riêng, không nên suy các điều kiện của collector vào phương thức Stream chỉ vì kết quả đều là danh sách không cho sửa. Khi xử lý null, phải xác định yêu cầu và kiểm tra API thực sự đang dùng.

## 8. Khi thực sự cần mutable List hoặc mutable Set

### 8.1. Dùng `toCollection(ArrayList::new)`

```java
var editableNames = names.stream()
        .map(String::strip)
        .collect(Collectors.toCollection(ArrayList::new));

editableNames.add("New");
editableNames.remove("Old");
```

Đây là mảnh code, cần import `ArrayList` và `Collectors`, giả định `names` là collection chuỗi. `toCollection(ArrayList::new)` cho biết rõ **kiểu đích và khả năng sửa**, không cần đặt cược vào implementation của `Collectors.toList()`.

### 8.2. Dùng `toCollection(HashSet::new)`

```java
var editableLabels = labels.stream()
        .collect(Collectors.toCollection(HashSet::new));

editableLabels.add("urgent");
```

Mảnh code cần `HashSet`/`Collectors` và biến `labels` phù hợp. Nó chủ đích tạo một `HashSet` mutable để lưu phần tử duy nhất; không bảo đảm thứ tự duyệt.

### 8.3. Cần thứ tự chèn trong Set: `LinkedHashSet`

```java
var insertionOrder = values.stream()
        .collect(Collectors.toCollection(LinkedHashSet::new));
```

Mảnh code cần `LinkedHashSet`, `Collectors` và `values` là nguồn có encounter order. `LinkedHashSet` duyệt theo thứ tự chèn, giúp giữ lần xuất hiện đầu tiên của phần tử.

**Không** dùng `Collectors.toSet()` hoặc `toUnmodifiableSet()` với mong muốn tự động có thứ tự chèn. Cả hai đều là unordered collectors.

Nếu muốn **một tập read-only được duyệt theo thứ tự chèn**, có thể tạo `LinkedHashSet` private rồi bọc bằng `Collections.unmodifiableSet(...)`, miễn là backing collection đó không bị sửa hay làm lộ tham chiếu cho nơi khác. Đây là **unmodifiable view**, khác với kết quả `Set.copyOf` vốn không bảo đảm iteration order.

### 8.4. Cần thứ tự sắp xếp: tạo nguồn có comparator

```java
var sorted = values.stream()
        .collect(Collectors.toCollection(TreeSet::new));
```

Mảnh code cần `TreeSet` và `Collectors`, và yêu cầu các phần tử so sánh tự nhiên được với nhau. Nếu cần comparator riêng, dùng factory `() -> new TreeSet<>(comparator)` với `comparator` đã được khai báo. Hãy nhớ `TreeSet` còn có quy tắc nhận diện phần tử tương đương theo comparator, vì vậy có thể loại những object mà comparator coi bằng nhau.

## 9. Đặt ra hợp đồng đúng khi xuất dữ liệu cho phương thức khác

Giả sử một service trả về `Set<String> permissions()`. Nếu caller **không được phép sửa danh sách quyền nội bộ**, nên bảo đảm hợp đồng đầu ra bằng unmodifiable set hoặc một bản immutable đúng phạm vi.

Ví dụ mảnh method trong class:

```java
static Set<String> effectivePermissions(List<String> rawPermissions) {
    return rawPermissions.stream()
            .map(String::strip)
            .filter(name -> !name.isEmpty())
            .collect(Collectors.toUnmodifiableSet());
}
```

Mảnh code cần import `java.util.Set`, `java.util.List`, `Collectors`. `String.strip()` xuất hiện từ Java 11; phương thức trên phù hợp với **Java 17+**. Nếu cần dùng Java 10 làm target, phải dùng API xử lý chuỗi tương thích với target và ngữ nghĩa mong muốn.

Ưu điểm:
- Nêu rõ người nhận không thể tự ý `add/remove`.
- Quy tắc lọc/chuẩn hóa dữ liệu được xác định ngay nơi xuất API.
- Tập kết quả không phản ánh các thay đổi cấu trúc nguồn sau collect.
- Không phụ thuộc vào implementation cụ thể.

Tuy nhiên, unmodifiable set **không** phải cơ chế bảo mật cho phép phân quyền. Kiểm tra quyền thực tế ở điểm thực thi vẫn phải dùng dữ liệu và quy trình được hệ thống tin cậy; collector chỉ làm rõ **hợp đồng dữ liệu tại API**.

Với dữ liệu có thứ tự quan trọng (ví dụ danh sách bước nghiệp vụ), hãy trả `List` và chọn `toUnmodifiableList` hoặc `Stream.toList` phù hợp, thay vì sử dụng `Set`.

## 10. Stream, song song, hiệu năng và thread safety

### 10.1. Parallel stream không khiến Set có thứ tự

Hai dòng đều trả set không cho sửa chứa phần tử duy nhất, nhưng **không bảo đảm thứ tự duyệt**:

```java
var first = names.stream()
        .collect(Collectors.toUnmodifiableSet());

var second = names.parallelStream()
        .collect(Collectors.toUnmodifiableSet());
```

Mảnh code cần `names` và `Collectors`. Không so sánh `first.toString()` với `second.toString()` để kết luận nội dung khác nhau. Dùng `first.equals(second)` khi muốn so sánh thành viên.

### 10.2. Collector result không có bảo đảm thread-safe

Javadoc `Collectors.toList` và `toSet` không hứa hẹn thread safety của collection trả về. `toUnmodifiableList`/`toUnmodifiableSet` ngăn mutator thông qua tập kết quả, nhưng **không** biến object phần tử mutable thành an toàn khi truy cập đồng thời.

Stream framework có thể xử lý song song một reduction mà không yêu cầu bạn tự thêm lock quanh collector mặc định. Điều đó **không** là lời hứa rằng một List/Set thu được sau đó sẽ phù hợp cho mọi tình huống đồng thời hoặc mọi hành vi object lồng bên trong.

### 10.3. Không chọn collector chỉ vì giả định tối ưu nội bộ

Không nên áp dụng quy tắc “`toUnmodifiableList` lúc nào cũng nhanh hơn `toList`” hoặc ngược lại. Hiệu năng thực tế phụ thuộc kích thước dữ liệu, đường xử lý, implementation và workload. Khi hiệu năng quan trọng:
- Đo trên JDK và dữ liệu thực tế;
- Xét nhu cầu mutable/unmodifiable là **hợp đồng đúng đắn trước tiên**;
- Tránh sao chép thêm không cần thiết nếu API hiện tại đã trả dữ liệu phù hợp;
- Không hy sinh thông tin về thứ tự, null hoặc mutability chỉ để giảm vài ký tự.

## 11. Viết unit test ổn định

### 11.1. Test List: kiểm tra cả thứ tự và trùng lặp

```java
var result = List.of("c", "a", "b", "a")
        .stream()
        .collect(Collectors.toUnmodifiableList());

if (!result.equals(List.of("c", "a", "b", "a"))) {
    throw new AssertionError("Wrong list order or duplicates");
}
```

Đây là mảnh code trong method, cần `List` và `Collectors`. `List.equals` so sánh thứ tự và phần tử tương ứng, phù hợp với List từ nguồn có encounter order.

### 11.2. Test Set: không phụ thuộc thứ tự

```java
var result = List.of("c", "a", "b", "a")
        .stream()
        .collect(Collectors.toUnmodifiableSet());

if (!result.equals(Set.of("a", "b", "c"))) {
    throw new AssertionError("Wrong set members");
}
```

Mảnh code cần `List`, `Set`, `Collectors`. **Không** kiểm tra phần tử đầu qua `iterator.next()` hoặc kỳ vọng một chuỗi `toString()` theo thứ tự cố định.

### 11.3. Test unmodifiable: thao tác sửa phải bị chặn

```java
var result = List.of("a", "b")
        .stream()
        .collect(Collectors.toUnmodifiableList());

boolean blocked = false;
try {
    result.add("c");
} catch (UnsupportedOperationException expected) {
    blocked = true;
}

if (!blocked) {
    throw new AssertionError("Unmodifiable list allowed mutation");
}
```

Đây là mảnh code trong method. Với JUnit có thể thay bằng `assertThrows(...)` nếu dự án đã có dependency phù hợp.

**Không viết test `Collectors.toList()` bắt buộc cho phép `add`**: khả năng sửa không nằm trong cam kết. Nếu mã thực sự cần sửa, hãy chuyển sang `toCollection(ArrayList::new)` và test hành vi đó.

### 11.4. Test null: nêu rõ hợp đồng

```java
var source = java.util.Arrays.asList("a", null, "b");

boolean rejected = false;
try {
    source.stream().collect(Collectors.toUnmodifiableSet());
} catch (NullPointerException expected) {
    rejected = true;
}

if (!rejected) {
    throw new AssertionError("Null should be rejected");
}
```

Mảnh code này hợp lệ trong method với import `Collectors`. Không dùng `List.of("a", null, "b")` làm nguồn vì factory `List.of` sẽ ném ngoại lệ trước collector.

## 12. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “`Collectors.toList` luôn trả `ArrayList` mutable.” | Javadoc không cam kết loại implementation hoặc mutability. |
| “`Collectors.toSet` luôn trả `HashSet` mutable.” | Không cam kết implementation/mutability; đây là unordered collector. |
| “`toUnmodifiableList` chỉ là tên khác của `toList`.” | Không: có hợp đồng không cho sửa và từ chối `null`. |
| “`toUnmodifiableSet` giữ thứ tự đầu vào.” | Không: đây là unordered collector. |
| “Set collector giữ cả phần tử trùng.” | Không: kết quả `Set` có một phần tử tương đương theo `equals`. |
| “`toUnmodifiableSet` giữ đúng object trùng xuất hiện đầu tiên.” | Không có cam kết chọn đại diện nào nếu hai object bằng nhau theo `equals`. |
| “Set unmodifiable thì mọi object bên trong đều immutable.” | Không: object mutable có thể còn thay đổi trạng thái. |
| “Stream.toList() có từ Java 10.” | Sai: `Stream.toList()` có từ Java 16. |
| “Stream.toList() và Collectors.toList() đều bảo đảm mutable.” | Sai: `Stream.toList()` bảo đảm **unmodifiable**; `Collectors.toList()` không cam kết. |
| “toCollection(ArrayList::new) thừa vì toList luôn mutable.” | Nếu cần đảm bảo mutable `ArrayList`, `toCollection(ArrayList::new)` mới thể hiện rõ hợp đồng đó. |
| “Với parallel stream, kết quả list chắc chắn thread-safe.” | Thread safety của collection kết quả không được bảo đảm từ collector thường. |
| “Có thể dùng `Set.copyOf` để có thứ tự chèn ổn định.” | Set tạo bởi `copyOf` không bảo đảm iteration order; dùng cấu trúc/cách xuất kết quả có hợp đồng thứ tự phù hợp. |

## 13. Quy tắc lựa chọn cho code review

Đặt câu hỏi theo thứ tự:

1. **Cần giữ phần tử trùng và thứ tự?** Dùng List; nếu chỉ cần membership và uniqueness, cân nhắc Set.
2. **Có cần kết quả không cho sửa?** Nếu có, chọn `toUnmodifiableList`/`toUnmodifiableSet` hoặc API tương đương đã có cam kết rõ.
3. **Có cần tiếp tục add/remove vào kết quả?** Nếu có, chọn `toCollection` với factory mutable.
4. **Dữ liệu có thể chứa null?** Chuẩn hóa/kiểm tra theo nghiệp vụ. Hai collector `toUnmodifiable...` từ chối null.
5. **Set có cần thứ tự chèn hoặc sorted order?** Chọn `LinkedHashSet`, `TreeSet` hoặc danh sách được sắp xếp, **không** dựa vào `toSet`/`toUnmodifiableSet`.
6. **Có object mutable không?** Đánh giá bất biến dữ liệu và những field tham gia `equals/hashCode`.
7. **Mức Java mục tiêu là gì?** Java 10 hỗ trợ `Collectors.toUnmodifiable...`; `Stream.toList` chỉ có từ Java 16; `String.strip` từ Java 11.

Mẫu review hợp lý:

> “Hàm này trả collection cho caller và yêu cầu không sửa kết quả. `Collectors.toList()` không bảo đảm tính unmodifiable; hãy dùng `Collectors.toUnmodifiableList()` (Java 10+) hoặc `Stream.toList()` (Java 16+) theo yêu cầu null của dữ liệu.”

Một nhận xét chưa đủ căn cứ:

> “Dùng `Collectors.toList()` là sai và phải thay tất cả bằng `toUnmodifiableList()`.”

`toList` vẫn là API chuẩn và hợp lệ khi bạn không cần một hợp đồng mutability cụ thể. Quyết định phải căn cứ vào yêu cầu của code, không chỉ theo phong cách.

## 14. Bài tập tự kiểm tra

**Câu 1.** `Collectors.toList()` có bảo đảm trả một `ArrayList` sửa được không?

**Đáp án:** Không. Không được cam kết loại implementation hoặc mutability.

**Câu 2.** `Collectors.toUnmodifiableList()` có từ Java nào và khác gì với `toList()`?

**Đáp án:** Java 10. Nó bảo đảm không cho sửa và từ chối null; giữ encounter order của stream nếu có.

**Câu 3.** `List.of("c","a","c").stream().collect(Collectors.toUnmodifiableSet())` có bao nhiêu phần tử?

**Đáp án:** Hai phần tử `"a"` và `"c"`. Thứ tự duyệt không được bảo đảm.

**Câu 4.** Có thể dùng `toSet()` nếu muốn chắc chắn giữ thứ tự chèn không?

**Đáp án:** Không. `toSet` là unordered collector. Có thể dùng `toCollection(LinkedHashSet::new)` với stream có encounter order.

**Câu 5.** `Stream.toList()` khác `Collectors.toList()` về mutability như thế nào?

**Đáp án:** `Stream.toList()` (Java 16) luôn trả list không cho sửa; `Collectors.toList()` (Java 8) không có cam kết mutability.

**Câu 6.** Có hai object bằng nhau theo `equals` nhưng có field phụ khác nhau. `toUnmodifiableSet` có bảo đảm giữ object đầu tiên không?

**Đáp án:** Không. Nó có thể giữ một đại diện bất kỳ của nhóm phần tử bằng nhau.

**Câu 7.** Muốn một `ArrayList` để gọi `add` sau khi collect, nên dùng gì?

**Đáp án:** `Collectors.toCollection(ArrayList::new)`, không dựa vào implementation hiện tại của `Collectors.toList()`.

**Câu 8.** Vì sao `Arrays.asList("a", null).stream().collect(Collectors.toUnmodifiableList())` ném `NullPointerException`?

**Đáp án:** Collector Java 10 này không nhận giá trị null. `Arrays.asList` cho phép null, nên null đi đến collector.

**Câu 9.** Kết quả `toUnmodifiableList` có chứa object mutable. Object đó đổi thuộc tính, có phải collector đã bị sửa trái phép không?

**Đáp án:** Không. Hợp đồng cấm sửa **collection**, không deep-copy hoặc đóng băng object phần tử.

**Câu 10.** Kết quả từ `parallelStream().collect(Collectors.toList())` có được cam kết thread-safe không?

**Đáp án:** Không. Cơ chế collect song song và tính thread-safe của collection kết quả là hai vấn đề khác nhau.

## 15. Nguồn chính thức

- [Oracle JDK 10 — `Collectors` API](https://docs.oracle.com/javase/10/docs/api/java/util/stream/Collectors.html): xem `toList`, `toSet`, `toUnmodifiableList`, `toUnmodifiableSet` cùng các mục `Since: 10`.
- [Oracle Java SE 21 — `Collectors` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collectors.html): hợp đồng các collector còn áp dụng trong Java hiện đại.
- [Oracle Java SE 21 — `Stream.toList()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html#toList()): terminal operation Java 16, list unmodifiable và encounter order.
- [Oracle Java SE 21 — `Collectors.toCollection(Supplier)`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collectors.html#toCollection(java.util.function.Supplier)): tạo collection theo factory chỉ định.
- [Oracle Java SE 21 — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/21/core/creating-immutable-lists-sets-and-maps.html): hướng dẫn dùng các collection không cho sửa trong ứng dụng hiện đại.
- [Oracle Java SE 21 — `Collection`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collection.html): khác biệt giữa unmodifiable collections, mutable collections và views.

**Ghi nhớ:** `Collectors.toList()` và `toSet()` **không cam kết kết quả mutable hay unmodifiable**; `toUnmodifiableList()` và `toUnmodifiableSet()` (Java 10) **bảo đảm không cho sửa và từ chối null**. Hai collector List giữ encounter order nếu có, hai collector Set là unordered và loại trùng. Muốn collection mutable cụ thể, dùng `toCollection(...)`; đừng nhầm `Collectors.toList()` với `Stream.toList()` của Java 16.