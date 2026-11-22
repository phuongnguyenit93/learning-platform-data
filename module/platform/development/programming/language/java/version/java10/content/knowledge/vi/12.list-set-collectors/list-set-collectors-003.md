# Phần tử trùng trong Collectors.toUnmodifiableList()

## 1. Mục tiêu và quy tắc cốt lõi

`Collectors.toUnmodifiableList()` nằm trong `java.util.stream.Collectors`, được bổ sung từ **Java 10** và vẫn được hỗ trợ trên các JDK hiện đại. Đây là một **Collector** dùng ở thao tác kết thúc `Stream.collect(...)`, nhằm thu thập các phần tử stream thành một `List` **không sửa được** (*unmodifiable list*).

**Điểm quan trọng của bài:** `toUnmodifiableList()` **giữ nguyên những lần xuất hiện trùng nhau**, không tự khử trùng (*deduplicate*). Nếu stream có **encounter order** (thứ tự gặp phần tử), collector cũng thu các phần tử theo thứ tự đó.

~~~java
// Đoạn minh họa bên trong phương thức; cần import java.util.List và java.util.stream.Collectors.
var events = List.of("LOGIN", "LOGIN", "VIEW", "LOGIN");
var result = events.stream()
        .collect(Collectors.toUnmodifiableList());

System.out.println(result);       // [LOGIN, LOGIN, VIEW, LOGIN]
System.out.println(result.size()); // 4
~~~

Giá trị `"LOGIN"` có mặt **3 lần** ở index `0`, `1` và `3`. `result.size()` trả `4`, **không phải** `2`. Hai tên sự kiện bằng nhau vẫn tương ứng hai lần xuất hiện riêng biệt trong danh sách.

Ba ý cần phân biệt:

1. **Unmodifiable:** người nhận không thể gọi `add`, `remove`, `set` hoặc thao tác mutator để thay đổi list kết quả.
2. **Duplicate được giữ:** kết quả là một `List`; List cho phép những phần tử có `equals` bằng nhau ở nhiều vị trí.
3. **Giữ encounter order nếu có:** một stream có thứ tự, như `List.stream()`, có trật tự gặp phần tử. Collector tạo list theo thứ tự này; nó không sắp xếp hoặc tự chọn giá trị đại diện.

**Không nhầm với** `Collectors.toUnmodifiableSet()`: Set giữ các phần tử duy nhất theo hợp đồng bình đẳng, vì vậy số lần xuất hiện trùng sẽ bị mất.

## 2. Vì sao List cho phép trùng nhưng Set không?

Trong Java Collections Framework, một **List** lưu dãy có thứ tự và có index; nhiều vị trí có thể chứa giá trị giống nhau. Một **Set** mô tả tập thành viên và không được chứa hai phần tử trùng theo hợp đồng `equals`.

~~~java
// Minh họa Java 17+ trong phương thức, có import java.util.* và Collectors.
var values = List.of("A", "B", "A", "A");

var asList = values.stream()
        .collect(Collectors.toUnmodifiableList());

var asSet = values.stream()
        .collect(Collectors.toUnmodifiableSet());

System.out.println(asList);           // [A, B, A, A]
System.out.println(asList.size());    // 4
System.out.println(asSet.size());     // 2
System.out.println(asSet.contains("A")); // true
~~~

Bảng đối chiếu:

| Đặc điểm | `Collectors.toUnmodifiableList()` | `Collectors.toUnmodifiableSet()` |
| --- | --- | --- |
| Kiểu kết quả | `List<T>` | `Set<T>` |
| Cho phép nhiều lần xuất hiện bằng nhau | **Có**, giữ mọi lần xuất hiện | **Không**, chỉ một đại diện cho nhóm trùng |
| Thứ tự phần tử | Theo encounter order nếu stream có thứ tự | Không cam kết iteration order |
| Cho phép thay đổi kết quả qua mutator | Không | Không |
| Cho phép phần tử `null` | Không, ném `NullPointerException` | Không, ném `NullPointerException` |
| Dùng index `get(i)` | Có | Không |
| Mục đích điển hình | Lịch sử sự kiện, danh sách dòng, thứ tự xử lý, giữ tần suất | Tập mã duy nhất, danh sách quyền không trùng, membership |

**Lưu ý về Set:** nếu đầu vào có hai object riêng biệt nhưng `equals` bằng nhau, `toUnmodifiableSet()` có thể giữ **một đại diện bất kỳ**; không được mặc định nó giữ object được gặp đầu tiên. Đây là hành vi riêng của set collector. `toUnmodifiableList()` không đặt ra thao tác chọn một đại diện: các vị trí được giữ.

Bản thân hai collector đều có `Since: 10` trong [Javadoc `Collectors`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html).

## 3. Đếm số lần xuất hiện mà không làm mất dữ liệu

Khi các bản ghi trùng có ý nghĩa nghiệp vụ, ví dụ các lần truy cập endpoint, giao dịch lặp lại hoặc nhiều đơn vị sản phẩm cùng mã, list là cấu trúc thích hợp.

~~~java
// Minh họa trong phương thức.
var logs = List.of("LOGIN", "LOGIN", "SEARCH", "LOGIN");
var immutableLog = logs.stream()
        .collect(Collectors.toUnmodifiableList());

System.out.println(immutableLog.size()); // 4
System.out.println(
        java.util.Collections.frequency(immutableLog, "LOGIN")
); // 3
~~~

`size()` đếm **tất cả phần tử**, còn `Collections.frequency(...)` đếm số lần một phần tử bằng giá trị tìm kiếm xuất hiện. `Collectors.toUnmodifiableList()` giữ nguyên cả hai thông tin ở thời điểm thu thập.

### Kiểm tra từng vị trí

~~~java
// Minh họa trong phương thức.
var data = List.of("A", "B", "A", "A");
var result = data.stream().collect(Collectors.toUnmodifiableList());

System.out.println(result.get(0));      // A
System.out.println(result.get(2));      // A
System.out.println(result.indexOf("A"));     // 0
System.out.println(result.lastIndexOf("A")); // 3
~~~

`indexOf` tìm index đầu tiên, `lastIndexOf` tìm index cuối cùng. Không có một bước “gộp phần tử trùng” trong collector, nên các index vẫn mang ý nghĩa theo encounter order.

### Duplicate theo giá trị và duplicate theo tham chiếu

Hai object khác nhau có thể được xem là bằng nhau theo `equals`. Với Java 17, một `record` đơn giản có `equals` theo các thành phần:

~~~java
// Khai báo record minh họa ở cấp class hoặc file, không đặt ở đầu phương thức.
record Event(String action) {}

// Trong thân phương thức:
var a = new Event("LOGIN");
var b = new Event("LOGIN");

var result = java.util.stream.Stream.of(a, b)
        .collect(java.util.stream.Collectors.toUnmodifiableList());

System.out.println(a.equals(b)); // true
System.out.println(a == b);      // false
System.out.println(result.size()); // 2
~~~

Dù `a.equals(b)` là `true`, list vẫn có **2 vị trí**. Bộ thu thập không tự tạo một bảng băm để loại object bằng nhau.

Ngược lại, nếu stream phát ra **chính một object hai lần**, list cũng có hai vị trí tham chiếu tới cùng object. `toUnmodifiableList` không deep-copy object phần tử và không buộc object thành bất biến.

## 4. Cơ chế stream: lọc, biến đổi, rồi thu thập

Mô hình cơ bản:

~~~java
// Minh họa trong phương thức.
List<String> result = source.stream()
        .filter(s -> !s.isBlank())
        .map(String::toUpperCase)
        .collect(Collectors.toUnmodifiableList());
~~~

Trong đoạn này, `source` là collection các chuỗi đã có từ trước (chưa khai báo ở đây). Pipeline có hai nhóm thao tác:

- **Trung gian:** `filter` giữ hoặc bỏ từng phần tử theo predicate; `map` biến đổi từng phần tử. Các bước này có thể làm một số giá trị trùng nhau (ví dụ `"a"` và `"A"` sau `toUpperCase`), nhưng không tự loại trùng chỉ vì giá trị sau biến đổi bằng nhau.
- **Kết thúc:** `collect(Collectors.toUnmodifiableList())` tiêu thụ stream và đưa các phần tử còn lại vào một list không sửa được.

Ví dụ độc lập:

~~~java
// Minh họa có import List, Collectors.
var input = List.of(" a ", "A", "b", " a ");
var output = input.stream()
        .map(String::trim)
        .map(String::toUpperCase)
        .collect(Collectors.toUnmodifiableList());

System.out.println(output); // [A, A, B, A]
~~~

Các bước `trim` và `toUpperCase` khiến nhiều giá trị thành `"A"`, nhưng danh sách đầu ra vẫn có 3 lần `"A"` theo thứ tự gặp.

**Không suy ngược rằng `toUnmodifiableList` tự khử trùng khi gặp biến đổi có trùng.** Chỉ các thao tác thay đổi số lượng phần tử trong pipeline (ví dụ `filter`, `distinct`, `limit`, `flatMap` trong trường hợp tương ứng) mới làm tập phần tử được thu thập khác với những phần tử đã được đưa vào.

### `distinct()` là phép loại trùng tường minh

~~~java
var input = List.of("A", "B", "A", "A");

var keepAll = input.stream()
        .collect(Collectors.toUnmodifiableList());

var unique = input.stream()
        .distinct()
        .collect(Collectors.toUnmodifiableList());

System.out.println(keepAll); // [A, B, A, A]
System.out.println(unique);  // [A, B]
~~~

`distinct()` dựa trên `equals` để lọc các lần xuất hiện trùng. Với **ordered stream** như stream của List, `distinct` giữ phần tử xuất hiện đầu tiên trong mỗi nhóm. `toUnmodifiableList` chỉ thu thập những gì pipeline đưa tới; nó không phải tác nhân loại trùng.

Nếu thứ tự ưu tiên cần được giữ, `distinct()` cộng với list collector phù hợp hơn so với chuyển sang Set vốn không hứa iteration order.

## 5. Encounter order: cần có ngay từ nguồn stream

Câu “`toUnmodifiableList` giữ thứ tự” phải hiểu chính xác là **giữ encounter order khi nguồn có encounter order**. Không phải stream nào cũng có thứ tự được bảo đảm.

### Stream từ List

~~~java
var source = List.of("C", "A", "C", "B");
var output = source.stream()
        .collect(Collectors.toUnmodifiableList());

System.out.println(output); // [C, A, C, B]
~~~

List có thứ tự duyệt theo index nên pipeline mang thứ tự gặp phần tử rõ ràng. Các phần tử `C` trùng vẫn ở index `0` và `2`.

### Stream từ HashSet

~~~java
// Không nên dự đoán thứ tự cụ thể từ HashSet.
var source = new java.util.HashSet<>(List.of("C", "A", "B"));
var output = source.stream()
        .collect(Collectors.toUnmodifiableList());
~~~

`HashSet` không bảo đảm iteration order. Danh sách thu được có thứ tự của stream ở lần chạy đó, nhưng **không có thứ tự nguồn ổn định để bảo toàn**. Thay đổi JVM hoặc implementation có thể khiến thứ tự khác. Đây không phải lỗi của collector.

### Stream được chủ động bỏ ràng buộc thứ tự

~~~java
var source = List.of("C", "A", "B");
var unordered = source.stream().unordered()
        .collect(Collectors.toUnmodifiableList());
~~~

`unordered()` cho phép stream không còn ràng buộc encounter order. Đừng viết test cố định `[C, A, B]` cho kết quả trên khi hợp đồng đã bỏ ràng buộc thứ tự.

### Sắp xếp trước khi thu thập

~~~java
var source = List.of("B", "A", "B", "C");
var sorted = source.stream()
        .sorted()
        .collect(Collectors.toUnmodifiableList());

System.out.println(sorted); // [A, B, B, C]
~~~

`sorted()` xác định order dựa trên thứ tự tự nhiên hoặc comparator. Nó **không xóa duplicate**: hai `B` vẫn còn. Kết quả có thứ tự ổn định bởi **bước sort**, không phải do collector tự sắp xếp.

## 6. Parallel stream có giữ duplicate không?

Có. Khi dùng `parallel()` với một **ordered stream** và `Collectors.toUnmodifiableList()`, collector tạo list theo encounter order của stream theo hợp đồng, dù việc xử lý các phần tử có thể diễn ra trên nhiều luồng.

~~~java
var source = List.of("A", "B", "A", "C", "A");

var serial = source.stream()
        .collect(Collectors.toUnmodifiableList());

var parallel = source.parallelStream()
        .collect(Collectors.toUnmodifiableList());

System.out.println(serial);   // [A, B, A, C, A]
System.out.println(parallel); // [A, B, A, C, A]
~~~

**Không nhầm thứ tự xử lý với thứ tự kết quả.** Trong parallel pipeline, thứ tự các lời gọi xử lý trung gian có thể khác thứ tự encounter. Nhưng kết quả của collector giữ encounter order nếu ngữ cảnh stream có ràng buộc order.

Vì vậy, không dùng `System.out.println` hay thao tác side effect trong `map`/`peek` để đoán thứ tự list cuối; side effect trên parallel stream có thể xuất hiện theo thứ tự thực thi khác. Tránh làm thay đổi shared mutable state trong `map`/`filter` nếu không có thiết kế đồng bộ phù hợp.

### Khi `unordered()` làm mất ràng buộc

~~~java
var values = List.of("A", "B", "A");
var unorderedResult = values.parallelStream()
        .unordered()
        .collect(Collectors.toUnmodifiableList());
~~~

Collector vẫn thu các phần tử được phát ra, bao gồm duplicate, nhưng không có cam kết giữ `A, B, A` theo trật tự gốc sau khi bạn chủ động loại bỏ yêu cầu order.

### Có cần song song chỉ để thu list không?

Không. `parallel()` không mặc nhiên tăng hiệu năng: chi phí tách/cộng dồn và đặc tính nguồn, kích thước dữ liệu, phép biến đổi quyết định hiệu quả. Chỉ dùng khi workload và đo lường cho thấy có lợi, không phải để thay đổi quy tắc duplicate.

## 7. Kết quả không sửa được nhưng không phải deep copy

`toUnmodifiableList` trả về list từ chối các thao tác sửa cấu trúc:

~~~java
var result = List.of("A", "A").stream()
        .collect(Collectors.toUnmodifiableList());

// Nếu chạy, lệnh sau ném UnsupportedOperationException:
// result.add("B");
~~~

Điều này không ảnh hưởng tới các phần tử đã có, bao gồm các lần xuất hiện trùng, và **không tự làm object bên trong bất biến**.

~~~java
// Đoạn minh họa: class Box là object mutable.
static final class Box {
    String label;
    Box(String label) { this.label = label; }
}

// Trong một phương thức cùng class:
var box = new Box("old");
var result = java.util.stream.Stream.of(box, box)
        .collect(java.util.stream.Collectors.toUnmodifiableList());

box.label = "new";

System.out.println(result.size());          // 2
System.out.println(result.get(0).label);    // new
System.out.println(result.get(1).label);    // new
System.out.println(result.get(0) == result.get(1)); // true
~~~

List có **2 vị trí tham chiếu cùng object**. Sửa object làm giá trị mà hai vị trí quan sát được thay đổi. Tuy nhiên, bạn vẫn không thể thêm/xóa/thay phần tử qua list kết quả.

Nếu ứng dụng cần dữ liệu hoàn toàn ổn định cho báo cáo hoặc cache, hãy ưu tiên phần tử immutable như `String`, `record` chỉ chứa thành phần immutable, hoặc sao chép dữ liệu object một cách phù hợp trước khi thu thập. `record` cũng không tự deep-copy các trường tham chiếu mutable.

### Thay đổi nguồn sau khi kết thúc collect

~~~java
var source = new java.util.ArrayList<>(List.of("A", "A"));
var result = source.stream()
        .collect(Collectors.toUnmodifiableList());

source.add("B");
source.remove(0);

System.out.println(source); // [A, B]
System.out.println(result); // [A, A]
~~~

Kết quả là một danh sách các phần tử được thu thập tại lúc stream chạy. Những thay đổi **cấu trúc nguồn sau thao tác terminal** không làm kết quả tự động thêm/xóa theo. Điều này khác với một live view như `Collections.unmodifiableList(source)`, vốn có thể phản ánh các thay đổi nguồn.

**Cẩn trọng concurrency:** Không coi `collect(...)` là ảnh chụp giao dịch nguyên tử của một nguồn mutable bị các thread khác sửa đồng thời. Nếu cần trạng thái chụp nhất quán, phải bảo đảm đồng bộ thích hợp với bên ghi.

## 8. Giá trị null bị từ chối — không nhầm với duplicate

`Collectors.toUnmodifiableList()` **không chấp nhận null**. Nếu stream đưa một phần tử null đến collector, thao tác kết thúc ném `NullPointerException`:

~~~java
// Đoạn minh họa lỗi runtime.
java.util.stream.Stream.of("A", null, "A")
        .collect(Collectors.toUnmodifiableList()); // NullPointerException
~~~

Duplicate `"A"` hoàn toàn hợp lệ; vấn đề là **phần tử `null`**, không phải số lần lặp lại.

Nếu dữ liệu đầu vào có thể null, hãy quyết định chính sách trước khi collect:

~~~java
// Loại các phần tử null khi nghiệp vụ cho phép:
var input = java.util.Arrays.asList("A", null, "A");

var result = input.stream()
        .filter(java.util.Objects::nonNull)
        .collect(Collectors.toUnmodifiableList());

System.out.println(result); // [A, A]
~~~

Giữ cả hai `"A"`, chỉ loại null. Không tự động bỏ null khi null mang ý nghĩa nghiệp vụ cần bảo toàn; khi đó hãy chọn cấu trúc/cơ chế có hợp đồng hỗ trợ null phù hợp.

### Khác biệt với `Stream.toList()` trên Java 17+

Từ Java 16, `Stream.toList()` cũng trả list không sửa được và giữ encounter order nếu có. Nhưng **đó là API khác**:

- `stream.collect(Collectors.toUnmodifiableList())`: có từ **Java 10**, collector từ chối null.
- `stream.toList()`: có từ **Java 16**, cho phép phần tử null theo hợp đồng của thao tác và không có giới hạn cấm null như collector trên.
- Cả hai đều giữ các lần xuất hiện trùng, và không được suy từ tên “unmodifiable” rằng chúng loại trùng.
- `Collectors.toList()`: có từ Java 8, nhưng **không cam kết mutability của kết quả**; không dùng nó khi API phải bảo đảm list không sửa được.

Ví dụ Java 17+:

~~~java
var data = java.util.Arrays.asList("A", null, "A");

// Hợp lệ với Stream.toList() trên Java 17:
var allowNull = data.stream().toList();
System.out.println(allowNull); // [A, null, A]

// Cùng dữ liệu đưa cho Collectors.toUnmodifiableList()
// sẽ gây NullPointerException.
~~~

Hãy quyết định dựa trên yêu cầu thực tế về null, phiên bản Java mục tiêu và API cần sử dụng; không đổi collector này sang API khác chỉ vì tên gần giống nhau.

## 9. Chương trình Java 17+ hoàn chỉnh, có stdout chính xác

File chạy dưới đây minh họa giữ duplicate, giữ encounter order, pipeline biến đổi, độc lập nguồn, parallel stream, so sánh Set và cách từ chối null/đột biến. Tất cả kết quả được in đều có thứ tự được bảo đảm hoặc là phép kiểm tra membership.

Lưu file đúng tên **`UnmodifiableListDuplicatesDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class UnmodifiableListDuplicatesDemo {

    static final class Box {
        private String label;

        Box(String label) {
            this.label = label;
        }

        void rename(String label) {
            this.label = label;
        }

        String label() {
            return label;
        }
    }

    public static void main(String[] args) {
        var source = new ArrayList<>(
                List.of("LOGIN", "LOGIN", "VIEW", "LOGIN")
        );

        var result = source.stream()
                .map(String::toLowerCase)
                .collect(Collectors.toUnmodifiableList());

        System.out.println("list=" + result);
        System.out.println("size=" + result.size());
        System.out.println("loginCount="
                + Collections.frequency(result, "login"));
        System.out.println("firstLogin=" + result.indexOf("login"));
        System.out.println("lastLogin=" + result.lastIndexOf("login"));

        source.add("LOGOUT");
        System.out.println("afterSourceEdit=" + result);

        Set<String> uniqueSet = result.stream()
                .collect(Collectors.toUnmodifiableSet());
        System.out.println("setSize=" + uniqueSet.size());
        System.out.println("setContainsLogin="
                + uniqueSet.contains("login"));

        var uniqueList = result.stream()
                .distinct()
                .collect(Collectors.toUnmodifiableList());
        System.out.println("distinct=" + uniqueList);

        var parallelResult = source.parallelStream()
                .map(String::toLowerCase)
                .collect(Collectors.toUnmodifiableList());
        System.out.println("parallel=" + parallelResult);

        var box = new Box("old");
        var boxes = Stream.of(box, box)
                .collect(Collectors.toUnmodifiableList());

        box.rename("new");
        System.out.println("boxCount=" + boxes.size());
        System.out.println("boxValues="
                + boxes.get(0).label() + "," + boxes.get(1).label());
        System.out.println("sameBox="
                + (boxes.get(0) == boxes.get(1)));

        try {
            result.add("new");
        } catch (UnsupportedOperationException expected) {
            System.out.println("mutationRejected=true");
        }

        try {
            Stream.of("A", null, "A")
                    .collect(Collectors.toUnmodifiableList());
        } catch (NullPointerException expected) {
            System.out.println("nullRejected=true");
        }

        var withNull = Arrays.asList("A", null, "A").stream().toList();
        System.out.println("streamToList=" + withNull);
    }
}
~~~

Lệnh biên dịch và chạy bằng JDK 17 trở lên có hỗ trợ `--release 17`:

~~~bash
javac --release 17 UnmodifiableListDuplicatesDemo.java
java UnmodifiableListDuplicatesDemo
~~~

**Stdout chính xác:**

~~~text
list=[login, login, view, login]
size=4
loginCount=3
firstLogin=0
lastLogin=3
afterSourceEdit=[login, login, view, login]
setSize=2
setContainsLogin=true
distinct=[login, view]
parallel=[login, login, view, login, logout]
boxCount=2
boxValues=new,new
sameBox=true
mutationRejected=true
nullRejected=true
streamToList=[A, null, A]
~~~

### Kiểm tra từng kết quả

1. `map(String::toLowerCase)` chuyển nội dung sang chữ thường nhưng không đổi số lượng phần tử: vẫn `[login, login, view, login]`, bốn vị trí và ba lần `login`.
2. `Collections.frequency(result,"login")` bằng `3`; `indexOf` trả `0` và `lastIndexOf` trả `3`.
3. `source.add("LOGOUT")` thực hiện **sau** khi đã collect, nên `result` không tự thêm phần tử; nó vẫn có bốn giá trị ban đầu.
4. `toUnmodifiableSet` từ `result` chỉ có hai giá trị phân biệt là `login` và `view`. Chương trình in `size` và `contains` thay vì in set, tránh phụ thuộc iteration order không được cam kết.
5. `distinct()` trên ordered stream của list loại các bản sao `login` còn lặp, giữ `[login, view]` theo lần xuất hiện đầu tiên.
6. `source.parallelStream()` vẫn là ordered stream từ `ArrayList`, nên collector trả năm phần tử theo encounter order, bao gồm `logout` được thêm vào source trước lúc stream thứ hai chạy.
7. Hai vị trí trong `boxes` tham chiếu **cùng đối tượng `Box`**; đổi nhãn thành `new` ảnh hưởng cả hai, nhưng không làm thay đổi số phần tử hay khả năng sửa list.
8. Mutator `result.add` ném `UnsupportedOperationException`; collector gặp null ném `NullPointerException`.
9. `Stream.toList()` của Java 17+ giữ một phần tử null trong ví dụ này, cho thấy nó **không có chính sách null giống `toUnmodifiableList`**.

Chương trình không sử dụng một thứ tự duyệt không được bảo đảm để tạo stdout. Các đoạn lỗi minh họa ở phần lý thuyết không được đặt trực tiếp vào file main, trừ những lời gọi đã được bọc bằng `try/catch`.

## 10. So sánh các cách thu thập danh sách

| Cách viết | Có từ Java | Duplicate | Thứ tự | Mutability kết quả | Null |
| --- | --- | --- | --- | --- | --- |
| `collect(Collectors.toUnmodifiableList())` | **10** | Giữ | Giữ encounter order nếu có | Không sửa được | Từ chối |
| `collect(Collectors.toList())` | 8 | Giữ | Giữ encounter order nếu có | **Không có cam kết** | Không dựa vào chính sách null nếu không rõ nguồn/collector |
| `stream.toList()` | **16** | Giữ | Giữ encounter order nếu có | Không sửa được | Cho phép |
| `collect(Collectors.toCollection(ArrayList::new))` | 8 | Giữ | Giữ encounter order nếu có | `ArrayList` có thể sửa | Có thể chứa null |
| `collect(Collectors.toUnmodifiableSet())` | **10** | **Loại trùng** | Collector UNORDERED, không cam kết thứ tự duyệt | Không sửa được | Từ chối |
| `stream.distinct().collect(Collectors.toUnmodifiableList())` | 10 | **Chủ động loại trùng** | Giữ lần xuất hiện đầu tiên nếu ordered stream | Không sửa được | Sau `distinct` vẫn từ chối null |

**Không nhầm với `List.copyOf(source)`:** đó là factory static trên `List` nhận một `Collection` có sẵn (từ Java 10), tạo list không sửa được giữ các phần tử theo iteration order. `Collectors.toUnmodifiableList()` là **collector** cho pipeline stream. Cả hai đều giữ duplicate, đều không nhận null, nhưng áp dụng ở vị trí xử lý khác nhau.

Ví dụ tương đương về **giá trị** khi đầu vào là một list không chứa null:

~~~java
var source = List.of("A", "A", "B");

var viaCollection = List.copyOf(source);
var viaStream = source.stream()
        .collect(Collectors.toUnmodifiableList());

System.out.println(viaCollection.equals(viaStream)); // true
~~~

Phép `equals` của list so sánh từng phần tử theo thứ tự. Đừng dựa vào `viaCollection == viaStream` hoặc implementation class cụ thể; tính bằng nhau về nội dung là điều cần kiểm chứng.

## 11. Lỗi thường gặp và cách sửa

| Nhận định/sai sót | Lý do | Cách làm đúng |
| --- | --- | --- |
| “`toUnmodifiableList` tự loại trùng vì không sửa được” | Unmodifiable chỉ giới hạn mutator của list, không giới hạn duplicate | Giữ list nếu cần số lần xuất hiện; chỉ loại trùng có chủ đích |
| “Hai sự kiện `LOGIN` giống nhau được tính là một” | `List` giữ mọi vị trí; `size` và `frequency` phản ánh số lần xuất hiện | Xử lý theo yêu cầu nghiệp vụ về sự kiện/tần suất |
| Dùng `toUnmodifiableSet` thay vì `toUnmodifiableList` để “chỉ đọc” | Set loại trùng và không cam kết order, làm mất thông tin | Dùng list collector khi thứ tự và duplicate có ý nghĩa |
| Thấy `map` tạo giá trị bằng nhau nên nghĩ collector gộp | `map` có thể tạo duplicate mới nhưng không lọc | Thêm `distinct()` nếu thực sự cần |
| Dùng `distinct` rồi ngạc nhiên vì thiếu lần xuất hiện | Chính `distinct` chủ động loại trùng | Bỏ `distinct` nếu dữ liệu phải giữ mọi occurrence |
| Giả định order luôn cố định dù stream từ HashSet | Nguồn không có encounter order đáng tin cậy | Sắp xếp tường minh hoặc lấy stream từ collection có order |
| Giả định song song làm hỏng kết quả của ordered list collector | `toUnmodifiableList` phải bảo toàn encounter order khi có | Phân biệt order kết quả với thời gian xử lý các phần tử |
| Nghĩ `toUnmodifiableList` cho phép null giống mọi list khác | Collector này chủ động từ chối null | Lọc/chuyển null trước collect, hoặc chọn API theo yêu cầu |
| Nghĩ `Collectors.toList()` luôn trả `ArrayList` mutable | Javadoc không bảo đảm implementation/mutability | Muốn chắc mutable, dùng `toCollection(ArrayList::new)` |
| Nghĩ unmodifiable là immutable sâu | Element mutable vẫn có thể thay trạng thái | Immutable value object hoặc defensive copy phần tử |
| Nghĩ kết quả là live view của collection ban đầu | List đã thu thập không tiếp tục phản ánh thay đổi cấu trúc nguồn | Thu thập lại nếu cần snapshot mới; live view là hợp đồng khác |
| Dựa vào identity hay lớp triển khai cụ thể | API không cam kết một implementation cụ thể | Lập trình theo `List<T>` và nội dung dữ liệu |

### Khi nào kết quả không giữ trùng?

Chỉ khi **các phần tử không được đưa tới collector** hoặc **pipeline chủ động loại trùng**. Ví dụ `filter` có thể bỏ một vài lần xuất hiện; `distinct` loại các phần tử bằng nhau; `limit` chỉ lấy một số phần tử đầu; `sorted` chỉ đổi thứ tự, không tự loại trùng. Bộ thu thập `toUnmodifiableList` không có lựa chọn “unique” bí mật.

Nếu nghiệp vụ cần **số lần xuất hiện nhưng muốn tránh lưu một list rất lớn**, có thể thay mô hình bằng map tần suất. Ví dụ:

~~~java
var values = List.of("A", "B", "A");
var counts = values.stream()
        .collect(Collectors.groupingBy(
                java.util.function.Function.identity(),
                Collectors.counting()
        ));

System.out.println(counts.get("A")); // 2
~~~

Đây là phép tổng hợp theo khóa và đếm có chủ đích, không tương đương với list giữ nguyên thứ tự. Đừng thay đổi mô hình nếu thứ tự hoặc vị trí từng occurrence vẫn cần được giữ.

## 12. Checklist áp dụng cho dự án

1. **Xác định yêu cầu dữ liệu:** mọi lần xuất hiện có ý nghĩa hay chỉ cần membership? Nếu cần tần suất và thứ tự, List là lựa chọn tự nhiên.
2. **Kiểm tra nguồn stream:** có encounter order không? Với `List.stream()` hoặc `Stream.of(...)`, có; với collection không có order hoặc pipeline đã dùng `unordered()`, đừng giả định output order cố định.
3. **Kiểm tra intermediate operations:** `map` có thể tạo thêm các giá trị bằng nhau; `filter`/`distinct`/`limit` có thể thay đổi số lượng phần tử. Bản thân collector chỉ thu thập kết quả đi tới nó.
4. **Chọn collector theo yêu cầu:** `toUnmodifiableList` cho danh sách không sửa được và giữ duplicate; `toUnmodifiableSet` cho membership duy nhất, không cần thứ tự.
5. **Xử lý null trước khi thu thập:** quyết định lọc, thay thế, báo lỗi hay chọn API cho phép null; `toUnmodifiableList` từ chối null.
6. **Phân biệt mutable với unmodifiable:** nếu bước tiếp theo cần thêm/sửa danh sách, `toUnmodifiableList` không phù hợp; cân nhắc `toCollection(ArrayList::new)`.
7. **Đánh giá dữ liệu phần tử:** list unmodifiable vẫn có thể chứa mutable object hoặc trỏ cùng một instance nhiều lần. Cần hợp đồng immutable sâu thì xử lý riêng.
8. **Đánh giá concurrency:** nếu nguồn mutable có thể bị thay đổi đồng thời, cần thiết kế thread-safety và snapshot nhất quán, không trông chờ collector giải quyết.
9. **Chạy kiểm thử đúng target:** trên Java 10–15 dùng `collect(Collectors.toUnmodifiableList())`; nếu target Java 16+ có thể cân nhắc thêm `Stream.toList()` với khác biệt null đã nêu.
10. **Viết test đúng:** kiểm `List.equals`, `size`, `get`, `indexOf` hoặc `Collections.frequency`. Không chỉ kiểm `contains` nếu duplicate là yêu cầu quan trọng.

### Tự đánh giá

**Câu 1.** `Stream.of("A","A","B").collect(Collectors.toUnmodifiableList())` có `size()` bằng bao nhiêu?

**Đáp án:** `3`, dữ liệu `[A, A, B]`; duplicate không bị xóa.

**Câu 2.** Cùng stream nhưng dùng `toUnmodifiableSet()` thì `size()` bằng bao nhiêu?

**Đáp án:** `2`. Set giữ hai giá trị phân biệt; iteration order không được bảo đảm.

**Câu 3.** `Stream.of("a","A").map(String::toUpperCase).collect(Collectors.toUnmodifiableList())` trả gì?

**Đáp án:** `[A, A]`; `map` tạo hai phần tử bằng nhau nhưng collector vẫn giữ cả hai.

**Câu 4.** `Stream.of("A",null,"A").collect(Collectors.toUnmodifiableList())` trả list có null không?

**Đáp án:** Không. Thao tác kết thúc ném `NullPointerException` do collector từ chối null.

**Câu 5.** Có phải kết quả của `toUnmodifiableList` luôn theo thứ tự phần tử được tạo ra trong quá trình chạy parallel?

**Đáp án:** Không nên suy từ thứ tự thời điểm xử lý. Kết quả theo **encounter order nếu stream có order**, còn việc xử lý trung gian trong parallel có thể diễn ra đồng thời và không theo thứ tự ấy.

**Câu 6.** Muốn list không sửa được nhưng chỉ giữ một `"A"` trong `[A,B,A]`, cần viết gì?

**Đáp án:** Dùng `source.stream().distinct().collect(Collectors.toUnmodifiableList())` với nguồn ordered; kết quả `[A,B]`. Chính `distinct` loại trùng.

**Câu 7.** Khi nguồn mutable được sửa sau khi `collect` hoàn thành, list kết quả tự cập nhật không?

**Đáp án:** Không đối với thay đổi cấu trúc nguồn. Tuy nhiên object phần tử mutable được tham chiếu có thể tiếp tục thay đổi trạng thái.

**Câu 8.** `var result = source.stream().collect(Collectors.toUnmodifiableList());` có thể được gọi là immutable sâu không?

**Đáp án:** Không. `var` chỉ là suy luận kiểu biến cục bộ, collector tạo unmodifiable List, nhưng không tự deep-copy các object phần tử.

## 13. Tài liệu chuẩn vẫn áp dụng hiện nay

- [Oracle Java SE 25 — Collectors API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html): `toUnmodifiableList()` thu các phần tử theo encounter order, trả List unmodifiable, từ chối null, có `Since: 10`; `toUnmodifiableSet()` loại duplicate và là UNORDERED collector.
- [Oracle Java SE 26 — Collectors API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html): xác nhận những hợp đồng collector trên tiếp tục áp dụng ở JDK mới.
- [Oracle JDK 25 — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html): cách dùng collectors `toUnmodifiableList`/`toUnmodifiableSet`, giới hạn phần tử mutable và iteration order của Set.
- [Oracle Java SE 25 — List API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html): List là ordered collection và cho phép duplicate; các kết quả unmodifiable không tự biến object phần tử thành immutable.
- [Oracle Java SE 25 — Stream API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): `Stream.toList()` có từ Java 16, tạo list không sửa được theo encounter order nếu có; tham khảo sự khác nhau với collector.
- [Oracle Java SE 25 — Collections.frequency](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#frequency(java.util.Collection,java.lang.Object)): đếm số lần một phần tử xuất hiện trong collection, hữu ích khi kiểm thử duplicate.

**Điều cần nhớ:** `Collectors.toUnmodifiableList()` **giữ tất cả các lần xuất hiện trùng**, bảo toàn encounter order của stream nếu có và trả list không sửa được. Muốn loại trùng, bạn phải làm **có chủ đích** bằng `distinct()` hoặc chuyển sang Set (đồng thời chấp nhận thay đổi hợp đồng thứ tự và số lượng). Không nhầm tính unmodifiable với tính duy nhất của phần tử.