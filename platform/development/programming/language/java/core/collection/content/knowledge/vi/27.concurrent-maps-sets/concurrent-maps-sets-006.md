# ConcurrentHashMap.newKeySet và view tập khóa

## 1. Từ một map đồng thời tới một set đồng thời

Một số bài toán chỉ cần biết một mã đã được đăng ký hay chưa: mã yêu cầu đang xử lý, tên đã xuất hiện, hoặc tài nguyên đã được nhận. Dùng `Map<K, Boolean>` có thể diễn đạt điều đó, nhưng người gọi thường không cần thao tác với giá trị Boolean; họ cần `add`, `contains` và `remove` của một `Set`.

`ConcurrentHashMap.newKeySet()` cung cấp một set đồng thời dựa trên map. Đồng thời, một `ConcurrentHashMap` có sẵn cũng có thể đưa ra **khung nhìn tập khóa (key-set view)** để người dùng thao tác với các khóa.

Hai cách này trông giống nhau khi khai báo bằng `Set<K>`, nhưng khác về quyền sở hữu và cách thêm phần tử:

- `newKeySet()` tạo một set mới với map nền mới.
- `map.keySet()` nhìn các khóa của map đang có; không hỗ trợ thêm qua set.
- `map.keySet(mappedValue)` cũng nhìn map đang có, nhưng cho phép thêm khóa bằng một giá trị chung đã chỉ định.

Khung nhìn không phải một bản sao. Xóa một khóa qua khung nhìn sẽ xóa cả ánh xạ khóa–giá trị trong map nền. Nếu bỏ qua điều này, một lời gọi tưởng chỉ sửa “danh sách khóa” có thể làm mất dữ liệu ở map mà thành phần khác đang dùng.

Mục tiêu của bài là đọc đúng mối quan hệ đó, chọn đúng API và sử dụng kết quả của thao tác set trong môi trường nhiều luồng. Ví dụ dùng Java 17 trở lên; cần biết `Map`, `Set`, khóa, giá trị và tham chiếu đối tượng.

## 2. Ba cách tạo có cùng kiểu nhìn nhưng khác ý nghĩa

### 2.1. Bảng đối chiếu API

| Cách lấy set | Map nền | Hỗ trợ `add/addAll`? | Giá trị dùng cho khóa được thêm |
| --- | --- | --- | --- |
| `ConcurrentHashMap.newKeySet()` | Map mới do phương thức tạo | Có | `Boolean.TRUE` |
| `ConcurrentHashMap.newKeySet(initialCapacity)` | Map mới, có gợi ý định cỡ ban đầu | Có | `Boolean.TRUE` |
| `map.keySet()` | Chính map đang có | Không | Không có giá trị mặc định để thêm |
| `map.keySet(mappedValue)` | Chính map đang có | Có | `mappedValue` khác null |

Các cách này trả về `ConcurrentHashMap.KeySetView`. Đối với factory `newKeySet`, kiểu giá trị nền là `Boolean`; với khung nhìn của `ConcurrentHashMap<K, V>`, kiểu giá trị nền là `V`. [ConcurrentHashMap — newKeySet và keySet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#newKeySet())

Các khung nhìn trong bảng đều hỗ trợ xóa. “Không hỗ trợ thêm” của `keySet()` vì thế **không có nghĩa là chỉ đọc**.

### 2.2. Tại sao `keySet()` không tự biết phải thêm giá trị gì?

Giả sử map chứa `String -> Order`. Khi người gọi viết `keys.add("order-7")`, chỉ có khóa `"order-7"` được cung cấp. Map còn cần một đối tượng `Order` để tạo ánh xạ.

`keySet()` không được tự đoán một `Order` hoặc thêm giá trị null. Bởi vậy, thao tác thêm không được hỗ trợ.

`keySet(mappedValue)` giải quyết bằng một lựa chọn tường minh: mọi khóa mới thêm qua khung nhìn này dùng cùng giá trị đã truyền. Nó phù hợp khi việc dùng chung giá trị đó là đúng với ý nghĩa dữ liệu.

`newKeySet()` giải quyết trường hợp thuần set bằng một giá trị đánh dấu `Boolean.TRUE`. Giá trị chỉ phục vụ biểu diễn trong map nền; thành viên của set được xác định bởi khóa.

### 2.3. Khung nhìn liên kết hai chiều

Có thể hình dung:

```text
map.keySet() --------\
                      > cung nhin cac khoa cua MOT map dang co
map.keySet("NEW") ---/

map.put / map.remove
         <----> thanh vien cua cac khung nhin

ConcurrentHashMap.newKeySet()
         ---> mot set moi ---> mot ConcurrentHashMap moi
```

Một số hệ quả:

- `map.put(k, v)` với khóa mới làm khung nhìn có thêm `k`.
- Thay giá trị của một khóa đang có không tạo thêm thành viên set.
- `keys.remove(k)` xóa cả khóa lẫn giá trị tương ứng trong map.
- `keys.clear()` xóa các ánh xạ của map nền, không chỉ “làm rỗng một bản danh sách khóa”.
- Hai khung nhìn lấy từ cùng map cùng thấy tập khóa đó, dù giá trị mặc định để thêm của chúng khác nhau.

Đây là quan hệ dữ liệu sống, không phải cơ chế thông báo sự kiện hay bản lưu lịch sử.

### 2.4. `KeySetView<K, V>` vẫn là `Set<K>`

Tham số `K` là kiểu phần tử set; `V` là kiểu giá trị của map nền. Nó không phải set chứa cặp `Map.Entry<K, V>`.

Có thể khai báo:

```java
Set<String> visited = ConcurrentHashMap.newKeySet();

ConcurrentHashMap.KeySetView<String, Boolean> detailed =
        ConcurrentHashMap.newKeySet();
```

Đây là các khai báo minh họa, cần import `Set` và `ConcurrentHashMap`. Dùng `Set` khi chỉ muốn bề mặt thao tác set. Dùng `KeySetView` khi thực sự cần các phương thức riêng như `getMap` và `getMappedValue`.

Lớp `KeySetView` không được tạo trực tiếp bằng constructor công khai. Các factory/phương thức của `ConcurrentHashMap` ở trên là điểm tạo được tài liệu chỉ ra. [KeySetView Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.KeySetView.html)

## 3. `keySet(mappedValue)`: giá trị chung cho khóa mới, không phải lệnh thay mọi giá trị

### 3.1. Thêm một khóa đã có không ghi đè

Đoạn minh họa không độc lập:

```java
ConcurrentHashMap<String, String> states = new ConcurrentHashMap<>();
states.put("task-1", "DONE");

Set<String> pending = states.keySet("PENDING");
boolean changed = pending.add("task-1");
```

Kết quả trong bối cảnh tuần tự này:

- `changed` là false vì khóa đã là thành viên.
- Giá trị của `"task-1"` vẫn là `"DONE"`.
- `"PENDING"` chỉ được dùng nếu việc thêm tạo một ánh xạ còn thiếu.

Nếu cần chuyển trạng thái của một khóa đang có, hãy dùng thao tác map phù hợp, chẳng hạn `replace` có điều kiện. Thêm khóa qua set không phải lệnh cập nhật trạng thái.

### 3.2. Một map có thể có nhiều khung nhìn với nhiều giá trị mặc định

Ví dụ:

```java
Set<String> pending = states.keySet("PENDING");
Set<String> queued = states.keySet("QUEUED");

pending.add("task-2");
queued.add("task-3");
```

Đây là đoạn minh họa với `states` từ ví dụ trước. Sau đó map có thể chứa cả `DONE`, `PENDING`, `QUEUED`. Giá trị mặc định gắn với **đường thêm qua một khung nhìn**, không phải quy tắc ép mọi giá trị của map phải giống nhau.

Nếu cả hai cùng thêm một khóa chưa có, việc bên nào tạo ánh xạ trước quyết định giá trị được dùng cho lần thêm đó. Bên sau thấy khóa đã tồn tại nên không dùng việc thêm để ghi đè.

**Điểm cần nhớ:** `keySet("PENDING")` không lọc các khóa có giá trị PENDING. Nó vẫn nhìn mọi khóa, kể cả các khóa đang mang DONE hay ACTIVE. Tham số chỉ quyết định giá trị dùng khi thêm một khóa còn thiếu.

### 3.3. `getMappedValue` và `getMap` trả về điều gì?

`getMappedValue()` trả giá trị mặc định dành cho thao tác thêm, hoặc null nếu khung nhìn không hỗ trợ thêm. `getMap()` trả map nền đang được liên kết. [KeySetView — các phương thức truy cập](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.KeySetView.html#getMappedValue())

Null từ `map.keySet().getMappedValue()` không có nghĩa map lưu giá trị null. Nó là tín hiệu về khả năng thêm của khung nhìn.

`getMappedValue()` cũng không phải lệnh đọc mọi giá trị hiện tại trong map. Các ánh xạ được tạo bằng đường khác có thể mang giá trị khác. `getMap()` không tạo bản sao và không trả một map chỉ đọc; giữ tham chiếu đó là có thêm một đường truy cập tới cùng dữ liệu.

## 4. Chương trình: nhìn thấy thay đổi hai chiều và phạm vi quyền sửa

Lưu thành **`KeySetViewDemo.java`**:

```java
import java.util.Iterator;
import java.util.List;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.concurrent.ConcurrentHashMap;

public class KeySetViewDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, String> states = new ConcurrentHashMap<>();
        states.put("kept", "DONE");
        states.put("remove-me", "ACTIVE");

        ConcurrentHashMap.KeySetView<String, String> keys = states.keySet();
        System.out.println("plain default = " + keys.getMappedValue());
        System.out.println("same backing map = " + (keys.getMap() == states));
        expectUnsupported("plain add", () -> keys.add("late"));
        expectUnsupported("plain addAll", () -> keys.addAll(List.of("late")));

        require(keys.remove("remove-me"), "remove through plain view");
        System.out.println("after view removal = " + new TreeMap<>(states));

        states.put("from-map", "ACTIVE");
        System.out.println("after map insertion = " + new TreeSet<>(keys));

        ConcurrentHashMap.KeySetView<String, String> pending =
                states.keySet("PENDING");
        boolean existingAdded = pending.add("kept");
        boolean newAdded = pending.add("new");
        require(!existingAdded && newAdded, "conditional addition");
        require("DONE".equals(states.get("kept")), "existing value overwritten");
        System.out.println("existing added = " + existingAdded);
        System.out.println("new added = " + newAdded);
        System.out.println("after mapped additions = " + new TreeMap<>(states));

        ConcurrentHashMap.KeySetView<String, String> other =
                states.keySet("OTHER");
        other.add("alternative");
        System.out.println("defaults = "
                + pending.getMappedValue() + ", " + other.getMappedValue());
        System.out.println("same keys in both views = " + pending.equals(other));

        Iterator<String> iterator = keys.iterator();
        while (iterator.hasNext()) {
            if ("new".equals(iterator.next())) {
                iterator.remove();
            }
        }
        require(!states.containsKey("new"), "iterator removal");
        System.out.println("removed via iterator = " + !states.containsKey("new"));
        System.out.println("final map = " + new TreeMap<>(states));

        pending.clear();
        System.out.println("clear view clears map = " + states.isEmpty());
    }

    private static void expectUnsupported(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("expected UnsupportedOperationException");
        } catch (UnsupportedOperationException ex) {
            System.out.println(label + " -> " + ex.getClass().getSimpleName());
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all KeySetViewDemo.java
java KeySetViewDemo
```

Stdout khi chạy thành công:

```text
plain default = null
same backing map = true
plain add -> UnsupportedOperationException
plain addAll -> UnsupportedOperationException
after view removal = {kept=DONE}
after map insertion = [from-map, kept]
existing added = false
new added = true
after mapped additions = {from-map=ACTIVE, kept=DONE, new=PENDING}
defaults = PENDING, OTHER
same keys in both views = true
removed via iterator = true
final map = {alternative=OTHER, from-map=ACTIVE, kept=DONE}
clear view clears map = true
```

Các quan sát chính:

1. Khung nhìn `keys` không có giá trị mặc định để thêm, nên hai lần thêm được thử đều ném `UnsupportedOperationException`.
2. Nó vẫn xóa được `"remove-me"`, và map mất ánh xạ đó.
3. Thêm bằng `states.put` xuất hiện trong cùng khung nhìn.
4. Khung nhìn `pending` thêm `"new" -> "PENDING"` nhưng không đổi `"kept" -> "DONE"`.
5. Khung nhìn `other` dùng mặc định khác, song vẫn có cùng tập khóa với `pending`.
6. Xóa bằng iterator của `keys` và `clear` bằng `pending` đều tác động vào map nền.

Các phép in dùng `TreeMap`/`TreeSet` để thứ tự stdout cố định. Đây là bước trình bày trong một chương trình tuần tự; không có cam kết rằng iterator của `ConcurrentHashMap` sắp xếp khóa.

Hai khung nhìn bằng nhau theo nội dung set vì chúng nhìn cùng các khóa ở lúc so sánh, không phải vì các giá trị mặc định bằng nhau. Trong bối cảnh có cập nhật đồng thời, không dùng một lần so sánh toàn bộ tập như một giao dịch khóa trạng thái lại.

## 5. `newKeySet`: set mới và thao tác thêm có điều kiện

### 5.1. Khi chỉ cần lưu sự hiện diện

Khai báo thông thường là:

```java
Set<String> registeredIds = ConcurrentHashMap.newKeySet();
```

Set này không dùng một map có sẵn của bạn. Factory tĩnh tạo map nền cho chính set mới. Viết lời gọi qua tên lớp `ConcurrentHashMap` giúp thể hiện đúng ý nghĩa; gọi factory qua một biến map không khiến kết quả trở thành khung nhìn của biến đó.

Một phần tử trong set tương ứng với một khóa trong map nền. Khi thêm qua API set, giá trị đánh dấu được dùng là `Boolean.TRUE`. Bạn thường không cần đọc giá trị đó; `Set` đã diễn đạt đúng nhu cầu kiểm tra thành viên.

Phần tử trùng theo hợp đồng set được xác định bằng quy tắc bằng nhau/băm của khóa, không đòi hỏi là cùng một đối tượng `==`. Vì vậy, khóa cần có `equals`/`hashCode` đúng và ổn định trong lúc đang nằm trong set. [Set Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)

### 5.2. Dùng kết quả `add`, không tự ghép `contains` rồi `add`

Đoạn minh họa cố ý không đủ cho việc chọn một bên thắng khi nhiều luồng cùng chạy:

```java
if (!registeredIds.contains("job-1")) {
    registeredIds.add("job-1");
    System.out.println("Bat dau xu ly job-1");
}
```

Hai luồng có thể đều thấy chưa có khóa rồi đều vào nhánh xử lý. Set vẫn không chứa hai khóa trùng, nhưng chương trình đã bỏ qua kết quả của hai lần thêm.

Một cách diễn đạt phù hợp hơn là:

```java
if (registeredIds.add("job-1")) {
    System.out.println("Lan dang ky nay da them job-1");
}
```

Đây là đoạn minh họa không độc lập. Với set từ `newKeySet`, lần thêm có điều kiện của map nền giữ việc tạo ánh xạ theo khóa. Khi khóa ban đầu vắng, không có bên xóa trong giai đoạn tranh chấp và nhiều bên cùng thêm, chỉ một lần thêm thay đổi set.

Kết quả true chỉ nói về lần đăng ký đó. Nếu ứng dụng xóa khóa rồi cho đăng ký lại, một lần thêm về sau có thể lại trả true.

### 5.3. Chương trình đầy đủ với hai tác vụ

Lưu thành **`ConcurrentKeySetDemo.java`**:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ConcurrentKeySetDemo {
    private static final int DISTINCT_PER_TASK = 1_000;

    public static void main(String[] args) throws Exception {
        ConcurrentHashMap.KeySetView<String, Boolean> ids =
                ConcurrentHashMap.newKeySet();
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Boolean> north = pool.submit(() -> addIds(ids, start, "north"));
            Future<Boolean> south = pool.submit(() -> addIds(ids, start, "south"));
            start.countDown();

            boolean a = north.get(10, TimeUnit.SECONDS);
            boolean b = south.get(10, TimeUnit.SECONDS);
            int successfulAdds = (a ? 1 : 0) + (b ? 1 : 0);
            require(successfulAdds == 1, "one shared-key addition must win");
            require(ids.size() == 2 * DISTINCT_PER_TASK + 1, "distinct count");
            boolean boundaryKeys = ids.contains("north-999")
                    && ids.contains("south-999");
            require(boundaryKeys, "missing boundary key");
            require(Boolean.TRUE.equals(ids.getMap().get("job-1")),
                    "set insertion must use the mapped value");

            System.out.println("successful shared-key adds = " + successfulAdds);
            System.out.println("total keys = " + ids.size());
            System.out.println("boundary keys present = " + boundaryKeys);
            System.out.println("default mapped value = " + ids.getMappedValue());

            ids.getMap().put("manual", Boolean.FALSE);
            boolean addedExisting = ids.add("manual");
            require(ids.contains("manual"), "presence is determined by the key");
            require(!addedExisting, "existing mapping must not be replaced");
            require(Boolean.FALSE.equals(ids.getMap().get("manual")),
                    "false value must be preserved");
            System.out.println("false-valued key is a member = "
                    + ids.contains("manual"));
            System.out.println("add existing manual key = " + addedExisting);
            System.out.println("manual mapping after add = "
                    + ids.getMap().get("manual"));
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }
        }
    }

    private static boolean addIds(
            ConcurrentHashMap.KeySetView<String, Boolean> ids,
            CountDownLatch start, String prefix) throws InterruptedException {
        if (!start.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("start timed out");
        }
        boolean won = ids.add("job-1");
        for (int i = 0; i < DISTINCT_PER_TASK; i++) {
            String id = prefix + "-" + i;
            require(ids.add(id), "new id must be inserted");
            require(!ids.add(id), "duplicate id must not be inserted");
        }
        return won;
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Lệnh chạy:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all ConcurrentKeySetDemo.java
java ConcurrentKeySetDemo
```

Stdout khi chạy thành công:

```text
successful shared-key adds = 1
total keys = 2001
boundary keys present = true
default mapped value = true
false-valued key is a member = true
add existing manual key = false
manual mapping after add = false
```

Hai tác vụ cùng thêm `"job-1"` rồi mỗi tác vụ thêm 1.000 khóa riêng. Mỗi khóa riêng được thử thêm hai lần: lần đầu phải thay đổi set, lần sau không thay đổi. Không có đường xóa trong giai đoạn đó.

Luồng chính chờ cả hai tác vụ hoàn tất rồi mới kiểm tra số lượng. Do đó, tổng 2.001 gồm 2.000 khóa riêng và một khóa chung. Nó không dựa vào việc đọc `size` lúc các tác vụ còn đang thêm.

Bên nào thắng khóa chung không được in thành một kết quả cố định vì điều đó phụ thuộc lịch chạy. Chương trình chỉ khẳng định đúng một lần thêm thành công. Các giới hạn chờ giúp báo lỗi thay vì treo; mọi lỗi kiểm tra trong tác vụ được chuyển về luồng chính qua `Future.get`.

### 5.4. Một giá trị `Boolean.FALSE` vẫn tạo thành viên nếu đưa vào map nền

Phần cuối chương trình cố ý lấy `getMap` rồi thêm `"manual" -> Boolean.FALSE`. Khóa vẫn là thành viên của set vì set nhìn **các khóa đang tồn tại**, không lọc theo giá trị có bằng true hay không.

Lần `ids.add("manual")` tiếp theo trả false và giữ giá trị false cũ. `getMappedValue()` vẫn là true vì đó là mặc định cho khóa mới, không phải kết quả kiểm tra mọi giá trị đang lưu.

Đây là minh họa về quyền truy cập map nền. Nếu thành phần chỉ cần một set thông thường, hạn chế phát tán tham chiếu map giúp tránh các đường thao tác không cần thiết. Không cần chủ động ghi false vào map để sử dụng `newKeySet`.

Nếu muốn biểu diễn trạng thái bật/tắt bằng giá trị Boolean, hãy thao tác trên map với hợp đồng trạng thái rõ ràng. Thành viên của khung nhìn tập khóa không đồng nghĩa với “giá trị Boolean đang bật”.

## 6. Giá trị mặc định là một tham chiếu chung

### 6.1. Không phải hàm tạo giá trị riêng cho từng khóa

`keySet(mappedValue)` nhận một giá trị, không nhận `Supplier<V>` hay hàm theo khóa. Khi các khóa mới được thêm qua khung nhìn, chúng dùng chung tham chiếu giá trị đã truyền.

Với `String`, enum hay một đối tượng đánh dấu bất biến, dùng chung thường đúng với mục đích. Với một danh sách có thể sửa, nó có thể là một nhầm lẫn lớn: sửa danh sách của khóa A cũng sửa chính đối tượng mà khóa B đang trỏ tới.

Điều đó khác với một thuật toán tạo một giá trị mới cho mỗi khóa. Nếu cần giá trị riêng, dùng thao tác map có hàm tạo phù hợp, rồi vẫn phải quản lý tính an toàn đa luồng của các giá trị được tạo.

### 6.2. Chương trình: tham chiếu chung, null và định cỡ ban đầu

Lưu thành **`MappedValueContractDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;

public class MappedValueContractDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, List<String>> groups = new ConcurrentHashMap<>();
        List<String> shared = new ArrayList<>();
        ConcurrentHashMap.KeySetView<String, List<String>> keys =
                groups.keySet(shared);
        keys.add("a");
        keys.add("b");
        require(groups.get("a") == groups.get("b"), "expected shared value");
        shared.add("tag");
        System.out.println("same value reference = "
                + (groups.get("a") == groups.get("b")));
        System.out.println("values after edit = " + new TreeMap<>(groups));

        ConcurrentHashMap.KeySetView<String, Boolean> ids =
                ConcurrentHashMap.newKeySet(1);
        ids.add("one");
        ids.add("two");
        ids.add("three");
        System.out.println("size with initialCapacity 1 = " + ids.size());

        expectFailure("add null", NullPointerException.class,
                () -> ids.add(null));
        expectFailure("contains null", NullPointerException.class,
                () -> ids.contains(null));
        expectFailure("remove null", NullPointerException.class,
                () -> ids.remove(null));
        expectFailure("null mapped value", NullPointerException.class,
                () -> groups.keySet(null));
        expectFailure("negative initialCapacity", IllegalArgumentException.class,
                () -> ConcurrentHashMap.newKeySet(-1));
    }

    private static void expectFailure(
            String label, Class<? extends RuntimeException> expected,
            Runnable action) {
        try {
            action.run();
            throw new AssertionError("expected " + expected.getSimpleName());
        } catch (RuntimeException ex) {
            if (!expected.isInstance(ex)) {
                throw ex;
            }
            System.out.println(label + " -> " + ex.getClass().getSimpleName());
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Lệnh chạy:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all MappedValueContractDemo.java
java MappedValueContractDemo
```

Stdout khi chạy thành công:

```text
same value reference = true
values after edit = {a=[tag], b=[tag]}
size with initialCapacity 1 = 3
add null -> NullPointerException
contains null -> NullPointerException
remove null -> NullPointerException
null mapped value -> NullPointerException
negative initialCapacity -> IllegalArgumentException
```

Chương trình chạy trong một luồng. Nó dùng `==` để kiểm tra `a` và `b` trỏ tới cùng danh sách, rồi sửa danh sách một lần và quan sát cả hai ánh xạ cùng nhìn thấy `[tag]`.

Thí nghiệm này minh chứng chia sẻ tham chiếu, không chứng minh rằng nhiều luồng được phép đồng thời sửa một `ArrayList`. `ConcurrentHashMap` bảo vệ ánh xạ; nó không tự làm danh sách giá trị trở thành collection concurrent.

### 6.3. Không có phần tử null

Khóa của `ConcurrentHashMap` không nhận null, nên set từ `newKeySet` không lưu phần tử null. Trong chương trình, các lệnh `add`, `contains`, `remove` với null được thử trên set hỗ trợ thêm và đều ném `NullPointerException`.

`map.keySet(null)` cũng không hợp lệ: muốn có một khung nhìn hỗ trợ thêm, phải cung cấp một giá trị mặc định khác null. Điều này không mâu thuẫn với `map.keySet().getMappedValue()` trả null để báo không hỗ trợ thêm.

Với một thao tác vừa không được hỗ trợ vừa có đối số không hợp lệ, đừng xây dựng thuật toán dựa vào việc ngoại lệ nào được kiểm tra trước. Hãy xác định đúng loại khung nhìn và chỉ truyền đối số hợp lệ.

### 6.4. `initialCapacity` là gợi ý định cỡ, không phải giới hạn

`newKeySet(1)` vẫn có thể chứa ba phần tử như chương trình cho thấy. Đối số hỗ trợ định cỡ nội bộ để dự kiến chứa số phần tử đó; nó không tạo một set có sức chứa cố định hay hạn mức đăng ký.

Giá trị âm bị từ chối bằng `IllegalArgumentException`. Không nên thử giá trị cực lớn chỉ để quan sát cấp phát; chọn dự kiến theo dữ liệu thực tế. [ConcurrentHashMap — newKeySet(int)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#newKeySet(int))

Nếu cần giới hạn tối đa N thành viên, `if (set.size() < N) set.add(x)` vẫn là một chuỗi có khoảng tranh chấp. Phải có cơ chế giữ đúng yêu cầu giới hạn; tham số định cỡ không thay thế cơ chế đó.

## 7. Mức bảo đảm đồng thời của khung nhìn

### 7.1. Iterator nhất quán yếu, không phải ảnh chụp

Iterator của `KeySetView` được quy định là nhất quán yếu (weakly consistent). Nó có thể duyệt trong lúc map được cập nhật mà không dùng cơ chế fail-fast để báo thay đổi nguồn. Tuy vậy, toàn bộ lượt duyệt không được chốt thành một ảnh chụp map tại một thời điểm. [KeySetView — iterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.KeySetView.html#iterator())

Không được yêu cầu mọi khóa thêm sau khi tạo iterator đều xuất hiện trong lượt đó, cũng không lấy một kết quả trên một bản JDK làm thứ tự cam kết.

Một tác vụ nên sở hữu iterator của nó. Khả năng một luồng duyệt khi luồng khác sửa map không đồng nghĩa hai luồng cùng chia sẻ một con trỏ iterator là an toàn.

`size`, `isEmpty` và kết quả duyệt tổng hợp có thể thay đổi trong lúc các bên khác cập nhật. Chương trình hai tác vụ đã chờ mọi bên ghi hoàn tất trước khi đòi kết quả chính xác 2.001; điều kiện đó không có sẵn trong mọi ứng dụng.

### 7.2. Khả năng sửa qua set không gộp mọi công việc thành giao dịch

`addAll` trên khung nhìn hỗ trợ thêm thực hiện thêm các phần tử theo ngữ nghĩa của từng lần `add`. Không suy từ đó rằng mọi người đọc chỉ thấy hoàn toàn trước hoặc hoàn toàn sau cả nhóm.

`removeAll`, `retainAll`, `removeIf` hoặc `clear` cũng có thể tác động tới nhiều ánh xạ. Chúng không phải lời hứa phối hợp mọi bất biến nghiệp vụ của map. Đặc biệt, một lỗi đầu vào hay lỗi hàm kiểm tra không nên được hiểu là mọi sửa đổi trước đó đã được hoàn tác.

Nếu nguồn phần tử của `addAll` đang bị sửa, còn phải tuân thủ hợp đồng duyệt của nguồn đó. Set đích concurrent không tự sửa mọi vấn đề của collection nguồn.

Khi cần “chỉ xóa khóa nếu trạng thái vẫn là PENDING”, xóa đơn thuần qua tập khóa không diễn đạt điều kiện giá trị. Đoạn minh họa không độc lập nên thao tác trên map:

```java
boolean removed = states.remove("task-7", "PENDING");
```

Thao tác có điều kiện này ghép kiểm tra và xóa theo hợp đồng `ConcurrentMap`. Tập khóa bỏ qua chiều giá trị, nên nó không phải công cụ phù hợp để biểu diễn mọi quy tắc chuyển trạng thái. [ConcurrentMap — remove có điều kiện](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html#remove(java.lang.Object,java.lang.Object))

### 7.3. Đăng ký mã không đồng nghĩa hoàn tất công việc đúng một lần

`if (ids.add(id))` có thể chọn một lần đăng ký thắng trong phạm vi set và vòng đời khóa được quy định. Nó không tự chứng minh tác vụ sau đó hoàn thành thành công đúng một lần.

Cần xác định set giữ loại trạng thái nào:

- **Đang xử lý:** khóa có thể được xóa khi công việc kết thúc để lần sau được vào lại.
- **Đã xử lý:** khóa có thể cần được giữ để nhận biết kết quả trước đó.
- **Đã đăng ký trong phiên:** mất set khi tiến trình/phiên kết thúc có thể là hành vi mong muốn.

Nếu đánh dấu trước rồi công việc thất bại, chương trình cần quyết định cách thử lại. Nếu xóa khóa để cho thử lại, phải xét những tác vụ còn chạy. Nếu cần giữ trạng thái/kết quả/phiên bản, một map có kiểu giá trị rõ ràng có thể phù hợp hơn set chỉ có sự hiện diện.

Set cũng không tự có thời gian hết hạn hay hạn mức số phần tử. Các yêu cầu đó cần được thiết kế theo vòng đời dữ liệu; không thể suy ra từ việc cấu trúc chứa an toàn đa luồng.

## 8. Chọn API và giữ đúng quyền của bên sử dụng

### 8.1. Bảng quyết định

| Nhu cầu | API/cách biểu diễn phù hợp để xem xét | Điểm cần giữ rõ |
| --- | --- | --- |
| Set đồng thời độc lập, chỉ lưu sự hiện diện | `ConcurrentHashMap.newKeySet()` | Không phải khung nhìn của một map có sẵn |
| Set tương tự với dự kiến kích thước ban đầu | `newKeySet(initialCapacity)` | Không phải sức chứa tối đa |
| Xem/xóa khóa của map đang có, không thêm qua set | `map.keySet()` | Có quyền xóa cả ánh xạ |
| Cho thêm khóa vào map với một giá trị mặc định chung | `map.keySet(value)` | Không lọc theo value, không ghi đè giá trị của khóa đã có |
| Mỗi khóa cần giá trị được tạo riêng hoặc chuyển trạng thái | API map phù hợp | Một giá trị chung không phải hàm tạo theo khóa |
| Chỉ công khai quyền đọc tập khóa sống | View không cho sửa bọc quanh khung nhìn | Nguồn vẫn có thể thay đổi |
| Muốn bản sao tách cấu trúc khỏi map | Sao chép tập khóa trong điều kiện thu thập phù hợp | Nguồn concurrent không tự thành ảnh chụp nhất quán toàn cục |

Tên biến cũng nên phản ánh đúng nghĩa. `pendingKeys = map.keySet("PENDING")` dễ khiến người đọc tưởng đây là bộ lọc; nếu dùng tên đó, tài liệu hoặc thiết kế xung quanh phải làm rõ. Một tên như `keysWithPendingDefault` có thể nói đúng vai trò hơn khi đây là API cho phép thêm.

Nếu thật sự cần tập các khóa đang có giá trị PENDING, phải định nghĩa một truy vấn/lượt thu thập riêng. Trong lúc map thay đổi, còn cần quyết định kết quả truy vấn có được trộn thời điểm hay không.

### 8.2. Bọc để không cho bên nhận sửa

Đoạn minh họa:

```java
Set<String> visibleKeys =
        Collections.unmodifiableSet(states.keySet());
```

Với `states` là `ConcurrentHashMap<String, String>`, bên nhận không được sửa qua `visibleKeys` hoặc iterator của nó. Nhưng nếu bên sở hữu sửa `states`, khung nhìn vẫn phản ánh dữ liệu nền; đây không phải bản sao đóng băng. [Collections — unmodifiableSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableSet(java.util.Set))

Chỉ đổi kiểu khai báo từ `KeySetView` thành `Set` không tự cấm xóa. Kiểu khai báo giúp chọn bề mặt API thông thường, còn khả năng sửa do đối tượng thực tế và đối tượng bọc quyết định.

Nếu người gọi không được quyền xóa dữ liệu map, đừng trả trực tiếp `map.keySet()` rồi mô tả nó là chỉ đọc.

### 8.3. Bản sao độc lập và tính nhất quán khi sao chép

Có thể tạo một `HashSet` mới từ tập khóa để các lần thêm/xóa sau này trên bản sao không sửa map gốc. Tuy nhiên, nếu map gốc đang cập nhật, quá trình lấy khóa vẫn tuân theo chính sách duyệt của nguồn.

Bản sao ổn định **sau khi tạo** và dữ liệu nguồn thuộc **cùng một phiên bản lúc thu thập** là hai yêu cầu khác nhau. Nếu cần yêu cầu thứ hai, mọi bên ghi và quá trình chụp phải cùng một giao thức phù hợp.

Khóa bên ngoài quanh khung nhìn hoặc map không tự buộc các luồng chỉ gọi API `ConcurrentHashMap` phải lấy khóa đó. Điều cần chứng minh là mọi đường liên quan thực sự phối hợp, không phải sự hiện diện của một từ khóa `synchronized` ở một chỗ.

### 8.4. Quan hệ với `Collections.newSetFromMap`

Một cách ghép khác là:

```java
Set<String> ids = Collections.newSetFromMap(
        new ConcurrentHashMap<String, Boolean>());
```

Đây là khai báo minh họa với import tương ứng. Set mang các đặc tính thứ tự, đồng thời và hiệu năng của map nền theo hợp đồng factory.

Với `Collections.newSetFromMap`, map đầu vào phải trống và tài liệu hướng dẫn không truy cập trực tiếp map đó sau khi factory trả về. Truyền map mới trực tiếp như trên giúp giữ đúng cách dùng này. [Collections — newSetFromMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#newSetFromMap(java.util.Map))

Không nhầm quy tắc đó với `existingMap.keySet(value)`: khung nhìn tập khóa được dùng trên map đang có dữ liệu và được thiết kế để liên kết với map đang tiếp tục sử dụng. Khi nhu cầu chỉ là một set dựa trên `ConcurrentHashMap`, `newKeySet` thể hiện ý định trực tiếp hơn.

### 8.5. Suy luận kiểu với `var`

Hai khai báo minh họa không có cùng kiểu phần tử:

```java
var broad = ConcurrentHashMap.newKeySet();
var strings = ConcurrentHashMap.<String>newKeySet();
```

Khai báo thứ nhất không có kiểu đích `Set<String>` để ràng buộc tham số kiểu, nên phần tử được suy luận là `Object`. Khai báo thứ hai chỉ định `String` tường minh.

Nếu muốn chỉ chứa chuỗi, dùng kiểu đích:

```java
Set<String> ids = ConcurrentHashMap.newKeySet();
```

hoặc dạng `var strings` có `<String>` ở trên. Khi kiểu phần tử là `String`, lệnh `strings.add(42)` bị trình biên dịch từ chối. Không dùng raw type để vượt qua kiểm tra này.

## 9. Luyện tập

### Bài 1 — Giá trị mặc định có phải bộ lọc?

Map chứa `"a" -> "DONE"` và `"b" -> "PENDING"`. Lấy `keys = map.keySet("PENDING")`.

**Câu hỏi:** `keys` có chứa `"a"` không? `keys.clear()` có chỉ xóa `"b"` không?

**Đối chiếu:** `keys` chứa cả hai khóa. Giá trị truyền vào chỉ phục vụ thêm khóa mới. `clear` xóa mọi ánh xạ của map nền, không lọc theo giá trị PENDING.

### Bài 2 — Không thêm được có phải chỉ đọc?

Một API trả trực tiếp `map.keySet()`. Người gọi không thêm được nhưng vẫn gọi `remove("invoice-7")`.

**Câu hỏi:** Dữ liệu giá trị tại khóa đó có được giữ trong map không? Nếu chỉ muốn công khai quyền đọc thì cần thay đổi gì?

**Đối chiếu:** Xóa khóa qua khung nhìn xóa cả ánh xạ, nên giá trị không được giữ tại khóa đó. Có thể bọc khung nhìn bằng `Collections.unmodifiableSet` nếu yêu cầu là tập khóa sống không cho sửa qua đường công khai; nếu cần bản sao thì phải tạo và công bố bản sao phù hợp.

### Bài 3 — Thêm khóa đã có

Map chứa `"task" -> "DONE"`. Một khung nhìn có giá trị mặc định `"PENDING"` gọi `add("task")`.

**Câu hỏi:** Giá trị cũ có bị thay không? Khi nào nên dùng thao tác map thay vì thêm qua set?

**Đối chiếu:** Không bị thay; lần thêm không thay đổi set và trả false trong bối cảnh không có thao tác khác xen kẽ. Nếu mục tiêu là chuyển trạng thái của khóa đang có, cần thao tác map với điều kiện giá trị/phiên bản phù hợp.

### Bài 4 — Hai khóa, một danh sách

Khung nhìn tạo bằng `map.keySet(sharedList)` thêm `"x"` và `"y"`, rồi chương trình sửa `sharedList`.

**Câu hỏi:** Có hai bản danh sách riêng không? Map concurrent có tự làm sửa danh sách an toàn giữa nhiều luồng không?

**Đối chiếu:** Hai ánh xạ cùng tham chiếu một giá trị đã truyền. Không có sao chép hay gọi hàm tạo cho từng khóa. Tính an toàn của trạng thái danh sách là yêu cầu riêng.

### Bài 5 — Boolean false trong map nền

Một `KeySetView<String, Boolean>` từ `newKeySet` được lấy map nền rồi ghi `"x" -> false`.

**Câu hỏi:** `set.contains("x")` có trả false vì giá trị false không? `set.add("x")` có đổi giá trị thành true không?

**Đối chiếu:** Khóa có mặt nên `contains` là true. Việc thêm không ghi đè ánh xạ đã tồn tại, nên trong bối cảnh tuần tự nó trả false và giữ giá trị false.

### Bài 6 — Có set không trùng nhưng xử lý vẫn trùng

Hai luồng dùng `if (!ids.contains(id))` rồi `ids.add(id)` và cùng chạy công việc phía sau.

**Câu hỏi:** Vì sao set không có phần tử trùng vẫn chưa đủ? Cần dựa vào kết quả nào?

**Đối chiếu:** Cả hai có thể qua phép kiểm tra trước khi một bên thêm. Cần dựa vào kết quả của chính `ids.add(id)` để chọn lần đăng ký làm thay đổi set, rồi còn phải định nghĩa vòng đời khóa và cách xử lý thành công/thất bại của công việc.

## 10. Tài liệu đối chiếu

- [ConcurrentHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): các factory `newKeySet` và hai overload `keySet`.
- [ConcurrentHashMap.KeySetView Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.KeySetView.html): quyền thêm/xóa, map nền, giá trị mặc định và iterator.
- [Set Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html): quy tắc thành viên, phần tử trùng và hợp đồng bằng nhau.
- [ConcurrentMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html): các thao tác có điều kiện trên ánh xạ.
- [Collections Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html): view không cho sửa và `newSetFromMap`.

