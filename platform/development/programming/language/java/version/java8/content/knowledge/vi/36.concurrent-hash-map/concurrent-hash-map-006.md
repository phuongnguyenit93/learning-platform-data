# ConcurrentHashMap: newKeySet và keySet với giá trị ánh xạ mặc định

## 1. Vì sao `ConcurrentHashMap` có API cho tập hợp khóa?

`ConcurrentHashMap<K,V>` là một map hỗ trợ các thao tác đồng thời. Đôi khi ta **chỉ cần biết một khóa có mặt hay không** chứ không cần gắn dữ liệu có ý nghĩa riêng cho từng khóa. Ví dụ: danh sách ID đã thấy, tập công việc đang được xử lý, tập cờ bật, tập thành viên đã đăng ký hoặc các mã cần loại trùng giữa nhiều thread.

Ta có thể dùng một `Set<K>` concurrent thay vì mỗi lần tự quản lý `ConcurrentHashMap<K,Boolean>`. Từ **Java 8**, `ConcurrentHashMap` cung cấp các factory và key-view để làm việc này:

- `ConcurrentHashMap.newKeySet()` — tạo **set concurrent mới**, được hậu thuẫn bởi một map nội bộ từ khóa tới `Boolean.TRUE`.
- `ConcurrentHashMap.newKeySet(initialCapacity)` — giống trên, nhưng có gợi ý dung lượng khởi tạo.
- `existingMap.keySet()` — lấy **view động** của các khóa trong một map đã tồn tại, **cho phép xem/xóa nhưng không cho thêm qua view** vì không biết phải đặt value nào.
- `existingMap.keySet(mappedValue)` — cũng là view động của map đó, nhưng **cho phép thêm khóa** bằng cách ánh xạ khóa **mới** tới `mappedValue` đã chọn.

Điểm đặc biệt của bài này là **giá trị ánh xạ mặc định** (*default mapped value*): nó là giá trị dùng khi gọi `add`/`addAll` qua `KeySetView`, **không phải** giá trị mặc định trả về từ `Map.get`, **không phải** cơ chế ghi đè các khóa đã có, và **không phải** thuộc tính thay đổi mọi value trong map.

### 1.1. Ví dụ một phút

```java
Set<String> online = ConcurrentHashMap.newKeySet();

online.add("alice"); // true: vừa thêm
online.add("alice"); // false: đã tồn tại
online.contains("alice"); // true
online.remove("alice"); // true
```

Đây là **snippet trong method**, cần `import java.util.Set;` và `import java.util.concurrent.ConcurrentHashMap;`. Việc kiểm tra/tạo mới khóa được thực hiện qua cấu trúc dữ liệu concurrent, không cần bọc toàn bộ `Set` bằng một khóa `synchronized` bên ngoài chỉ để gọi `add` đơn lẻ.

Còn nếu đã có map lưu vai trò:

```java
ConcurrentHashMap<String, String> members =
    new ConcurrentHashMap<>();
members.put("alice", "ADMIN");

Set<String> keysOnly = members.keySet();
// keysOnly.add("bob"); // UnsupportedOperationException.

Set<String> keysWithDefault = members.keySet("PENDING");
keysWithDefault.add("bob");
// members.get("bob") bằng "PENDING".
// members.get("alice") vẫn là "ADMIN".
```

Hai view tham chiếu **chính map `members`**, vì vậy thay đổi một bên phản ánh ở bên còn lại.

## 2. Tổng quan API và điểm khác nhau quyết định

| Lệnh tạo | Tạo map mới hay dùng map cũ? | `add(k)`? | Value cho khóa mới | `remove(k)`? |
| --- | --- | --- | --- | --- |
| `ConcurrentHashMap.newKeySet()` | **Map mới** nội bộ | Có | `Boolean.TRUE` | Có |
| `ConcurrentHashMap.newKeySet(n)` | **Map mới**, có sizing hint | Có | `Boolean.TRUE` | Có |
| `map.keySet()` | View của **map đã có** | **Không**; ném `UnsupportedOperationException` | Không có default | Có |
| `map.keySet(v)` | View của **map đã có** | Có | `v`, phải khác null | Có |

Cả bốn là API **có từ Java 8 và vẫn được duy trì**. Giá trị trả về là `ConcurrentHashMap.KeySetView<K,V>` (hoặc có thể gán cho interface `Set<K>`). `KeySetView` triển khai `Set` và cung cấp thêm `getMap()`, `getMappedValue()`.

**Sự khác nhau quan trọng nhất:** `newKeySet` là một tập hợp có **backing map riêng**, còn `map.keySet(...)` là **một góc nhìn lên dữ liệu của map mà bạn đã có**. Nếu bạn chỉ tạo set riêng, đừng nhầm rằng nó tự dùng chung state với bất kỳ biến `ConcurrentHashMap` nào khác.

### 2.1. Không nhầm `map.keySet()` với `map.keySet(value)`

Cả hai đều xuất phát từ **một map**, đều nhìn thấy các khóa và có thể xóa mapping. Nhưng bản **không tham số** không biết cách tạo value cho khóa được thêm, nên API cố ý không hỗ trợ `add`/`addAll`. Bản **có tham số** dùng cùng một `mappedValue` cho những khóa mới thêm qua chính view ấy.

Đây là khác biệt do **hợp đồng API**, không phải do số thread, không phải do map rỗng và không phải vì `Set` chung vốn không hỗ trợ `add`. Việc map có sẵn value cho một số khóa cũng không làm cho `keySet()` đột nhiên biết value thích hợp cho khóa mới.

## 3. `ConcurrentHashMap.newKeySet()`: một concurrent Set độc lập

Chữ ký rút gọn:

```java
static <K> ConcurrentHashMap.KeySetView<K, Boolean> newKeySet()
```

Factory này tạo một `KeySetView<K,Boolean>` mới, được hậu thuẫn bởi **một `ConcurrentHashMap<K,Boolean>` riêng**. Khi thêm phần tử bằng `add(k)`, khóa `k` được ánh xạ với `Boolean.TRUE`. Khi xóa phần tử bằng `remove(k)`, mapping tương ứng bị xóa khỏi map nội bộ.

```java
ConcurrentHashMap.KeySetView<String, Boolean> visited =
    ConcurrentHashMap.newKeySet();

boolean first = visited.add("article-7"); // true
boolean again = visited.add("article-7"); // false
boolean present = visited.contains("article-7"); // true
Boolean internal = visited.getMap().get("article-7");
// Boolean.TRUE
```

Nếu không cần những API mở rộng của view, bạn có thể dùng biến kiểu `Set<String>`:

```java
Set<String> ids = ConcurrentHashMap.newKeySet();

ids.add("A");
ids.add("B");
ids.remove("A");
```

**Nên chọn `newKeySet` khi:** mục tiêu là một concurrent set để lưu **sự hiện diện của key** và không có map hiện hữu nào cần giữ các value có ý nghĩa.

### 3.1. Tạo nhiều set sẽ tạo nhiều backing map khác nhau

```java
Set<String> first = ConcurrentHashMap.newKeySet();
Set<String> second = ConcurrentHashMap.newKeySet();

first.add("A");
// second.contains("A") == false.
```

Hai set không tự chia sẻ dữ liệu. Nếu muốn nhiều thành phần đồng thời truy cập **cùng** set, phải truyền đúng đối tượng set chung (qua dependency injection, constructor hoặc cùng một holder được công bố thread-safe), chứ không gọi factory mới trong từng request rồi mong các set dùng chung khóa.

### 3.2. Value nội bộ `Boolean.TRUE` là chi tiết có thể kiểm tra qua `getMap()`

`KeySetView.getMap()` trả về **chính backing `ConcurrentHashMap`**, không phải bản sao:

```java
ConcurrentHashMap.KeySetView<String, Boolean> set =
    ConcurrentHashMap.newKeySet();

set.add("A");
ConcurrentHashMap<String, Boolean> backing = set.getMap();
Boolean value = backing.get("A"); // true
```

Đừng tùy tiện sửa backing map thành `Boolean.FALSE` nếu bạn muốn **toàn bộ cấu trúc đại diện thuần set**. Khi đó `set.contains("A")` vẫn có thể là `true` dù map chứa Boolean.FALSE, bởi `KeySetView` chỉ hỏi **khóa có tồn tại không**, chứ không hỏi value có bằng true không.

Không cần gọi `getMap()` trong những use case chỉ muốn `add`, `contains`, `remove`. Giữ quyền truy cập backing map hẹp giúp duy trì bất biến dữ liệu.

## 4. `newKeySet(initialCapacity)`: gợi ý dung lượng chứ không phải giới hạn

Chữ ký:

```java
static <K> ConcurrentHashMap.KeySetView<K, Boolean>
    newKeySet(int initialCapacity)
```

`initialCapacity` là **ước lượng số phần tử ban đầu** giúp implementation có thể sizing bộ nhớ phù hợp. Nó **không** giới hạn số khóa tối đa và **không** mang nghĩa số thread hay số shard bắt buộc.

```java
Set<String> largeSet = ConcurrentHashMap.newKeySet(1_024);
largeSet.add("job-01");
// Vẫn có thể thêm nhiều hơn 1024 phần tử.
```

Các điểm cần nhớ:

- Giá trị âm bị từ chối bằng `IllegalArgumentException`.
- Tham số lớn có thể làm tăng chi phí cấp phát bộ nhớ ban đầu; không tự đặt số cực lớn “cho chắc”.
- Map có thể tăng kích thước khi số phần tử vượt mức dự kiến.
- Nội bộ phân bổ/bucket/resize là **chi tiết implementation** có thể thay đổi theo JDK; không thiết kế dựa vào giả định Java 7-era “một segment cho mỗi thread”.

Đối với đa số set vừa và nhỏ, `newKeySet()` đủ rõ; dùng hint khi có **ước lượng dữ liệu đáng tin** và đã quan sát hiệu năng phù hợp.

## 5. `map.keySet()`: view hiện hữu, có thể xóa nhưng không thể thêm

Với một map có value riêng cho từng khóa, `keySet()` trả một `KeySetView<K,V>` **liên kết trực tiếp** với map đó:

```java
ConcurrentHashMap<String, Integer> counters =
    new ConcurrentHashMap<>();

counters.put("A", 10);
counters.put("B", 20);

ConcurrentHashMap.KeySetView<String, Integer> keys =
    counters.keySet();

keys.contains("A");      // true
keys.remove("B");        // true
counters.containsKey("B"); // false
```

Đây là view **động (backed/live view)**: nó phản ánh các `put`/`remove` trực tiếp lên map. Xóa khóa từ view cũng thực sự xóa **cả mapping** tương ứng trong map; không chỉ “ẩn khóa khỏi một danh sách hiển thị”.

### 5.1. Tại sao không có `add`?

`Set.add(K)` chỉ cung cấp key, không có value. Với một map kiểu `ConcurrentHashMap<String, Integer>`, khi gọi `keys.add("C")`, giá trị của `"C"` là bao nhiêu? Không có căn cứ để tự chọn `0`, `null` hoặc số khác.

Vì vậy:

```java
ConcurrentHashMap<String, Integer> counters =
    new ConcurrentHashMap<>();
Set<String> keys = counters.keySet();

try {
    keys.add("C");
} catch (UnsupportedOperationException expected) {
    // Đúng theo hợp đồng: không có mapped value cho phép thêm.
}
```

Không nên sửa bằng `counters.put("C", null)`: `ConcurrentHashMap` **không hỗ trợ key hoặc value null**. Nếu muốn map gán default khi thêm khóa qua set, hãy chọn một **value khác null có ý nghĩa nghiệp vụ** và dùng `keySet(mappedValue)`.

### 5.2. `getMappedValue()` giúp nhận diện khả năng thêm

```java
ConcurrentHashMap<String, String> map =
    new ConcurrentHashMap<>();
ConcurrentHashMap.KeySetView<String, String> plain =
    map.keySet();

// plain.getMappedValue() == null
```

`null` ở đây báo rằng **view không có default value cho additions**. Nó không có nghĩa map chứa mapping với null, cũng không có nghĩa `getMap()` trả null.

### 5.3. Các phép xóa cũng có tác động tương ứng lên map

`keySet()` hỗ trợ các thao tác xóa từ `Set` như `remove`, `Iterator.remove`, `removeAll`, `retainAll`, `clear`. Khi sử dụng một view chỉ để hiển thị/duyệt khóa, đừng vô ý gọi những phương thức này vì chúng **xóa dữ liệu trong map gốc**.

Nếu cần một tập khóa để xử lý riêng mà không ảnh hưởng map, tạo **bản sao** bằng cấu trúc thích hợp. Bản sao tạo từ map đang bị concurrent update vẫn cần lưu ý iterator có thể cho nội dung yếu nhất quán; nó không phải snapshot nguyên tử chỉ vì ta copy trong một dòng code.

## 6. `map.keySet(mappedValue)`: thêm khóa bằng một value chung

Chữ ký rút gọn:

```java
ConcurrentHashMap.KeySetView<K,V> keySet(V mappedValue)
```

Phương thức này tạo view của **chính map đang gọi**, nhưng ngoài việc đọc và xóa, nó cho phép **thêm khóa** bằng cách dùng `mappedValue` cho những **mapping chưa tồn tại**.

```java
ConcurrentHashMap<String, String> status =
    new ConcurrentHashMap<>();
status.put("alice", "ACTIVE");

ConcurrentHashMap.KeySetView<String, String> pending =
    status.keySet("PENDING");

boolean inserted = pending.add("bob"); // true
String bob = status.get("bob");        // "PENDING"

boolean existing = pending.add("alice"); // false
String alice = status.get("alice");      // "ACTIVE"
```

Ở đây, `"PENDING"` là **giá trị dùng cho thêm mới qua view**, không phải biến làm thay đổi mọi value trong map:

- Thêm `"bob"` mới tạo mapping `bob → PENDING`.
- `"alice"` đã có value `"ACTIVE"`. `add("alice")` không ghi đè thành `"PENDING"`.
- `pending.contains("alice")` vẫn đúng, vì set kiểm tra **sự hiện diện khóa**, không phân loại theo giá trị.
- Nếu code khác `status.put("bob","ACTIVE")`, `pending.contains("bob")` vẫn đúng và `status.get("bob")` trở thành `"ACTIVE"`.
- Gọi `pending.remove("alice")` sẽ xóa mapping `"alice"`, **dù value của nó không bằng `"PENDING"`**.

### 6.1. `mappedValue` phải khác null

`map.keySet(null)` ném `NullPointerException` vì `ConcurrentHashMap` không chấp nhận null value. Tương tự, `set.add(null)` cũng không được hỗ trợ vì null key bị cấm.

```java
ConcurrentHashMap<String, String> map =
    new ConcurrentHashMap<>();

// Không hợp lệ:
 // map.keySet(null);       // NullPointerException
 // map.keySet("NEW").add(null); // NullPointerException
```

Hai dòng comment ở trên cố ý minh họa **điều không nên chạy**. Nếu domain cần biểu diễn "chưa có giá trị", dùng enum/sentinel **khác null** có ý nghĩa hoặc thiết kế result model; không dùng null trực tiếp trong ConcurrentHashMap.

### 6.2. Có thể có nhiều view với default khác nhau trên cùng map

```java
ConcurrentHashMap<String, String> map =
    new ConcurrentHashMap<>();

Set<String> pending = map.keySet("PENDING");
Set<String> active = map.keySet("ACTIVE");

pending.add("alice"); // alice -> PENDING
active.add("bob");     // bob -> ACTIVE
active.add("alice");   // false, alice vẫn PENDING
```

Hai view đều nhìn thấy **cả alice lẫn bob**, không phải một view lọc `PENDING` và view kia lọc `ACTIVE`. Default chỉ quyết định **value khi thêm khóa chưa có**. Nếu cần "tập khóa có value PENDING", phải lọc `entrySet()` theo value ở thời điểm đọc hoặc quản lý một index phụ với chính sách nhất quán.

## 7. `KeySetView.add(k)` làm gì với khóa mới và khóa đã tồn tại?

`KeySetView.add(k)` trên view hỗ trợ additions hoạt động theo **ngữ nghĩa set**:

- Trả `true` nếu thao tác làm tập khóa thay đổi do **thêm mới khóa**.
- Trả `false` nếu khóa đã có mặt tại thời điểm thao tác xác định kết quả, ngay cả khi value lưu trong map **khác với `mappedValue`**.
- Việc thêm mới khóa sử dụng mapped value được cấu hình, không cần caller truyền value theo từng lần add.
- Trên `keySet()` **không có default**, `add` ném `UnsupportedOperationException`.
- Trên `newKeySet()`, mapped value tương đương `Boolean.TRUE`.

Một ví dụ dễ mắc lỗi:

```java
ConcurrentHashMap<String, Boolean> flags =
    new ConcurrentHashMap<>();
flags.put("enabled", Boolean.FALSE);

Set<String> enabledKeys = flags.keySet(Boolean.TRUE);

boolean changed = enabledKeys.add("enabled"); // false
Boolean stored = flags.get("enabled");        // false
boolean present = enabledKeys.contains("enabled"); // true
```

**Không** dùng `flags.keySet(true).add("enabled")` để *bật* một flag đã đang là `false`. Nó chỉ thêm khóa **nếu vắng mặt**, không cập nhật giá trị đã có.

Nếu bạn cần đổi `false → true`, dùng API map có ngữ nghĩa value:

```java
flags.put("enabled", Boolean.TRUE);

// Hoặc cập nhật có điều kiện theo giá trị cũ:
boolean changedOnlyIfFalse =
    flags.replace("enabled", Boolean.FALSE, Boolean.TRUE);
```

Ở snippet hai dòng trên, `replace` sẽ trả `false` nếu mapping không còn là `false`. Chọn `put` hoặc `replace`/`compute`/`merge` theo hợp đồng cập nhật; đừng ép `Set.add` làm nhiệm vụ sửa value.

### 7.1. `add` mang ý nghĩa atomic membership, không phải transaction bên ngoài

Trong bối cảnh hai thread cùng gọi `set.add("A")` trên cùng một concurrent set ban đầu chưa có khóa:

```text
Thread T1: set.add("A") ───┐
                          ├── chỉ một thao tác chèn khóa thắng
Thread T2: set.add("A") ───┘
Kết quả: một lời gọi trả true, lời gọi còn lại trả false
```

**Thứ tự thắng không được dự đoán trước.** Hai thread không thể đồng thời làm cho cùng một khóa “vừa được thêm lần đầu” hai lần theo ngữ nghĩa set. Đây là công cụ hữu ích để loại trùng **trong cùng một tiến trình** khi dữ liệu và set được chia sẻ đúng cách.

Nhưng điều này **không** bảo đảm một tác vụ bên ngoài (ghi DB, chuyển tiền, gửi email) chạy **exactly once** trên mọi tiến trình, restart hay lỗi giữa chừng. Nếu dùng `if (set.add(id)) { publishMessage(id); }`, lỗi sau khi add nhưng trước publish có thể khiến tác vụ không hoàn tất, còn retry có thể bị loại bỏ. Hệ thống có side effect quan trọng cần idempotency key/transaction/outbox theo phạm vi toàn hệ thống.

### 7.2. `addAll` không phải transaction nguyên khối

`addAll(Collection<? extends K>)` thêm từng phần tử như gọi `add` và trả boolean cho biết collection đã thay đổi. Với nhiều thread, các phần tử có thể được nhìn thấy/cạnh tranh **từng khóa**; không có cam kết cả danh sách xuất hiện như **một lần commit nguyên tử**.

```java
Set<String> names = ConcurrentHashMap.newKeySet();
boolean changed = names.addAll(Arrays.asList("A", "B", "C"));
// changed == true trong trường hợp set ban đầu trống.
```

Snippet cần import `Arrays`, `Set` và `ConcurrentHashMap`. Nếu một phần tử null hoặc thao tác phát sinh lỗi, đừng giả định các phần tử trước đó chắc chắn được rollback. Nếu ứng dụng cần “tất cả hoặc không”, thiết kế transaction/cơ chế đồng bộ độc lập.

## 8. View động: thay đổi qua map và qua set nhìn thấy nhau

`map.keySet()` và `map.keySet(mappedValue)` đều **backed by map**. Vì vậy:

```java
ConcurrentHashMap<String, String> map =
    new ConcurrentHashMap<>();
Set<String> view = map.keySet("NEW");

map.put("a", "OLD");
boolean seen = view.contains("a"); // true

view.add("b");
String newValue = map.get("b");     // "NEW"

map.remove("a");
boolean gone = !view.contains("a"); // true
```

Không phải view chỉ được chụp một lần tại thời điểm gọi `keySet`. Nếu map đang bị nhiều thread cập nhật, view cũng quan sát **dữ liệu đang thay đổi**, không có thứ tự duyệt cố định.

### 8.1. `getMap()` trả backing map, không phải clone

```java
ConcurrentHashMap<String, Integer> map =
    new ConcurrentHashMap<>();
ConcurrentHashMap.KeySetView<String, Integer> view =
    map.keySet(0);

boolean sameObject = (view.getMap() == map); // true
Integer defaultForAdd = view.getMappedValue(); // 0
```

`getMap()` hữu ích để hiểu/kiểm thử view đang dựa vào map nào. Nếu API của bạn chỉ nên cho consumer xem set, **đừng tùy tiện lộ `getMap()`** hoặc view có quyền `clear/remove` cho mã không đáng tin. Đây không phải read-only facade.

### 8.2. `getMappedValue()` chỉ là mặc định khi thêm

Một key-view với default `"PENDING"` có thể đang chứa những khóa có value `"ACTIVE"`, `"FAILED"` hoặc `"DONE"`. `getMappedValue() == "PENDING"` không nói rằng tất cả entry trong map đều map tới `"PENDING"`.

Tương tự, `getMappedValue() == null` với view từ `keySet()` có nghĩa **add không hỗ trợ**; không có mapping null nào được tạo.

### 8.3. Tạo view không tự thay đổi các mapping đang có

```java
ConcurrentHashMap<String, String> map =
    new ConcurrentHashMap<>();
map.put("x", "CUSTOM");

ConcurrentHashMap.KeySetView<String, String> view =
    map.keySet("DEFAULT");

// map.get("x") vẫn "CUSTOM"; chỉ việc tạo view không đổi gì.
```

`keySet(mappedValue)` không phải `map.replaceAll(...)`. Nó chỉ ghi nhận một quy tắc dùng khi **sau này thêm phần tử từ view**. Nếu value là object mutable được chia sẻ cho mọi khóa mới, các khóa đó có thể cùng tham chiếu **một object**, nên dễ phát sinh lỗi aliasing. Ưu tiên value mặc định bất biến (enum, Boolean, String bất biến) và dùng API map để tạo value riêng theo từng khóa khi cần.

## 9. Xóa qua set nghĩa là xóa mapping từ map

Cả `newKeySet`, `keySet()` và `keySet(mappedValue)` đều hỗ trợ các thao tác `Set.remove` và các thao tác xóa tập con:

- `remove(key)`: xóa **một mapping** theo key.
- `Iterator.remove()`: xóa mapping cho phần tử mà iterator đang xử lý.
- `removeAll(collection)`: loại các khóa có trong collection.
- `retainAll(collection)`: chỉ giữ lại những khóa thuộc collection được cung cấp.
- `clear()`: xóa **mọi mapping** trong backing map.

**Bẫy quan trọng:** Với `map.keySet("NEW")`, `view.remove("a")` xóa mapping `a` **bất kể value hiện tại của `a` là gì**. Nó không chỉ xóa những entry có value bằng `"NEW"`.

```java
ConcurrentHashMap<String, Integer> map =
    new ConcurrentHashMap<>();
map.put("x", 1);
map.put("y", 2);
map.put("z", 3);

Set<String> keys = map.keySet(0);

keys.retainAll(Arrays.asList("x", "z"));
// map không còn "y", dù value ban đầu của y là 2.

keys.clear();
// map trở thành rỗng.
```

Nếu bạn muốn **chỉ xóa khi value vẫn bằng một giá trị dự kiến**, API phù hợp hơn là `map.remove(key, expectedValue)`:

```java
ConcurrentHashMap<String, String> map =
    new ConcurrentHashMap<>();
map.put("A", "ACTIVE");

boolean removedWrong = map.remove("A", "PENDING"); // false
boolean removedRight = map.remove("A", "ACTIVE");  // true
```

Điều này hữu ích khi nhiều thread cập nhật trạng thái một khóa. Thao tác `view.remove("A")` không có tham số expected value nên có thể xóa mapping đã được thread khác thay giá trị giữa các bước nghiệp vụ.

### 9.1. Không dùng view cho thao tác “read-only” rồi vô tình xóa dữ liệu

Một API trả `Set<K>` không đảm bảo caller chỉ xem. Nếu nó đang trỏ tới `map.keySet()`, lời gọi `clear()` vẫn có thể xóa map. Nếu cần bề mặt không cho mutate, cân nhắc `Collections.unmodifiableSet(map.keySet())` — wrapper này chặn thao tác sửa **qua wrapper**, nhưng **dữ liệu hiển thị vẫn live** khi map bị cập nhật ở nơi khác.

Nếu cần một snapshot không đổi sau thời điểm thu thập, có thể tạo `Collections.unmodifiableSet(new HashSet<>(map.keySet()))` **sau khi các writer đã dừng**. Khi map vẫn đang bị sửa, copy không cam kết snapshot nhất quán tức thời của toàn map vì iterator yếu nhất quán.

## 10. Concurrent add: cùng khóa chỉ có một lần thành công

Lý do chọn `ConcurrentHashMap.newKeySet()` thay vì một `HashSet` thông thường chia sẻ giữa nhiều thread là khả năng thực hiện các thao tác chính trên tập khóa theo cơ chế thread-safe của backing map.

Với thao tác:

```java
if (visited.add(taskId)) {
    // Thread này đã thêm được một key chưa có vào visited.
    processFirstObservation(taskId);
}
```

Đây là snippet kiến trúc; `visited` và `processFirstObservation` do ứng dụng định nghĩa. Khi `add` trả `true`, bạn biết lời gọi đó đã đưa key từ vắng mặt sang có mặt theo contract tại thời điểm chèn. Không cần tự làm:

```java
// Có race khi hai thread cùng thấy absent:
if (!visited.contains(taskId)) {
    visited.add(taskId);
    processFirstObservation(taskId);
}
```

Cả hai thread có thể cùng `contains == false`, rồi cùng tiến vào `processFirstObservation`. `add` đơn lẻ trả boolean mới là tín hiệu để phân biệt bên thắng.

### 10.1. Không suy ra thứ tự khóa từ thứ tự thread

`ConcurrentHashMap` không giữ thứ tự insertion giống `LinkedHashSet`. Output của `for (String s : concurrentSet)` không được đảm bảo theo thứ tự `A,B,C...`. Nếu cần log hoặc test có thứ tự, thu thập khóa **sau khi các writer hoàn thành** rồi sắp xếp:

```java
List<String> sorted = new ArrayList<>(concurrentSet);
Collections.sort(sorted);
System.out.println(sorted);
```

Đây là snippet cần `ArrayList`, `Collections`, `List`, với `concurrentSet` đã tồn tại. Việc sort là để **trình bày ổn định**, không thay đổi bản chất unordered của set.

### 10.2. Không đánh đồng set trong JVM với hệ thống dedup toàn cục

Nếu hai instance backend có **hai** `newKeySet()` riêng, cả hai đều có thể nhận `true` khi thêm cùng task ID. Nếu ứng dụng restart thì set trong RAM mất dữ liệu. Nếu yêu cầu loại trùng xuyên tiến trình hoặc bền qua restart, dùng unique constraint, distributed lock/conditional write hoặc kho idempotency theo domain.

`ConcurrentHashMap.newKeySet` tốt cho **cùng JVM**, nhưng bản thân nó không phải một distributed store.

## 11. Duyệt trên `KeySetView`: weakly consistent, không phải snapshot

Iterator và spliterator của `ConcurrentHashMap.KeySetView` là **weakly consistent**:

- Có thể duyệt trong lúc thread khác thêm/xóa mà không theo mô hình fail-fast iterator truyền thống của `HashMap`.
- Có thể nhìn thấy một số thay đổi concurrent **hoặc không**; không nên khẳng định duyệt sẽ thấy toàn bộ dữ liệu “tại thời điểm bắt đầu” hay “tại thời điểm kết thúc”.
- Thứ tự phần tử không được bảo đảm.
- Một iteration không đại diện cho **snapshot nguyên tử** của toàn bộ map.
- `Spliterator` báo các đặc tính `CONCURRENT`, `DISTINCT` và `NONNULL` cho các khóa.

Ví dụ:

```java
ConcurrentHashMap.KeySetView<String, Boolean> keys =
    ConcurrentHashMap.newKeySet();
keys.add("A");
keys.add("B");

// Thread khác có thể tiếp tục keys.add("C") trong lúc duyệt.
for (String key : keys) {
    // Không được dựa vào việc thấy đúng A, B hay C
    // nếu các cập nhật đồng thời vẫn đang diễn ra.
}
```

Đây là snippet minh họa. Không phải lời khuyên dùng vòng lặp rỗng trong production; thực tế bạn sẽ xử lý mỗi key, đồng thời cần chấp nhận mô hình visibility của tập đang thay đổi.

### 11.1. `size`, `mappingCount` và kiểm tra trong lúc concurrent update

`Set.size()`, `map.mappingCount()` và kết quả iteration có thể thay đổi trong khi các thread đang cập nhật. `mappingCount()` trả kiểu `long` và thích hợp cho map rất lớn, nhưng khi có cập nhật đồng thời, số lượng có thể chỉ là **ước lượng tại một thời điểm**.

Nếu bạn cần “đã xử lý chính xác N task trước khi kết thúc batch”, hãy đồng bộ **vòng đời của batch** bằng `Future.get`, `CountDownLatch`, `Phaser`, transaction hoặc cơ chế hoàn tất công việc; không xem `keys.size() == N` là bằng chứng toàn bộ side effect đã hoàn tất.

### 11.2. `Stream`, `parallelStream` và bulk operations

Bạn có thể gọi `stream()`, `parallelStream()` trên `Set`, nhưng không nên dùng stream để tạo **snapshot nhất quán** khi map đang bị cập nhật. Nếu processing cần độ chính xác per-key, dùng APIs concurrent phù hợp và định nghĩa rõ điều kiện thắng/thua.

`ConcurrentHashMap` còn có các bulk operations `forEach`, `search`, `reduce` phục vụ truy cập dữ liệu concurrent. Chúng không biến iterator thành snapshot transaction và không bắt buộc cho use case set membership đơn giản. Không dùng `parallelStream` chỉ vì set “concurrent”: cần cân nhắc CPU, side effect, executor contention và kích thước dữ liệu.

## 12. Null, equals/hashCode và kiểu khóa

`ConcurrentHashMap` **không cho phép null key hoặc null value**. Vì vậy:

- `newKeySet().add(null)` ném `NullPointerException`.
- `map.keySet(null)` ném `NullPointerException` ngay khi tạo view.
- `view.contains(null)`, `view.remove(null)` cũng không được dùng.
- `newKeySet(-1)` ném `IllegalArgumentException` vì capacity âm.

### 12.1. Membership dựa trên `equals` và `hashCode`

Set ánh xạ các phần tử theo định nghĩa khóa của map. Với custom class:

```java
final class JobKey {
    private final String id;

    JobKey(String id) {
        this.id = id;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof JobKey)) return false;
        JobKey that = (JobKey) other;
        return id.equals(that.id);
    }

    @Override
    public int hashCode() {
        return id.hashCode();
    }
}
```

Đây là **snippet class** chưa có `main`. Hai khóa có cùng `id` được coi như một thành viên set; không dựa vào `==` để so identity nếu business key là value. Cần đảm bảo `id` khác null qua constructor/hợp đồng dữ liệu.

### 12.2. Không mutate những trường quyết định hash sau khi thêm

Nếu khóa chứa trường mutable ảnh hưởng `equals/hashCode`, việc thay đổi nó sau `set.add(key)` có thể làm `contains`/`remove` không tìm được mapping cũ như mong đợi. Đây là quy tắc chung với hash-based collections, và càng khó gỡ khi nhiều thread cùng thao tác.

Ưu tiên khóa bất biến (ví dụ `String`, immutable ID class hoặc `record` nếu dự án dùng Java 16+; `record` **không có trong Java 8**). Nếu dùng key object có nhiều trường, thiết kế rõ trường nào quyết định identity nghiệp vụ.

## 13. Default value chung: khi nào phù hợp và khi nào nguy hiểm?

`keySet(mappedValue)` phù hợp khi **mọi khóa mới thêm qua view đều có thể dùng chung một value**. Giá trị đó thường là:

- `Boolean.TRUE` cho set thuần membership.
- Một enum như `Status.NEW` khi mỗi khóa mới bắt đầu trong trạng thái NEW.
- Một String bất biến như `"PENDING"` cho ví dụ minh họa.
- Một marker object bất biến có thể dùng chung nếu domain định nghĩa rõ.

**Không phù hợp** khi mỗi khóa mới cần value khác nhau, ví dụ một `UserSession` độc lập, một timestamp tạo mới, một counter hoặc một object mutable không thể chia sẻ.

### 13.1. Dùng `putIfAbsent` hoặc `computeIfAbsent` khi value riêng cho từng key

```java
ConcurrentHashMap<String, Integer> attempts =
    new ConcurrentHashMap<>();

Integer first = attempts.putIfAbsent("A", 0);
// Nếu A vắng, đặt A -> 0.

Integer current = attempts.computeIfAbsent("B",
    key -> calculateInitialValue(key));
```

Đây là **snippet**, cần method `calculateInitialValue(key)` do ứng dụng cung cấp. Nếu value tính theo key, dùng `computeIfAbsent` với mapping function phù hợp hơn `keySet(sameValue).add(key)`. Với map chứa các đối tượng mutable hoặc atomic counters, bạn vẫn cần cân nhắc vòng đời, update atomic và chi phí/side effects của mapping function.

### 13.2. Có nhiều giá trị khác nhau trong map? View vẫn thấy mọi khóa

```java
ConcurrentHashMap<String, String> map =
    new ConcurrentHashMap<>();
map.put("a", "ACTIVE");
map.put("b", "FAILED");

Set<String> pendingAdder = map.keySet("PENDING");

// pendingAdder.contains("a") và contains("b") đều true.
// pendingAdder.add("c") sẽ thêm c -> PENDING.
```

Tên biến `pendingAdder` nhấn mạnh đây là **view hỗ trợ thêm với default** chứ không phải `Set` chỉ chứa các key có status PENDING. Nếu cần truy vấn “tất cả khóa có trạng thái PENDING”, hãy lọc các entry theo value hoặc duy trì chỉ mục phù hợp. Khi map biến đổi concurrent, kết quả lọc cũng cần được hiểu theo semantics không snapshot.

## 14. Chương trình đầy đủ: tất cả ba API và phép thêm đồng thời

Ví dụ sau sử dụng **chỉ các API có từ Java 8**, vẫn biên dịch/chạy được trên JDK hiện đại. Nó kiểm thử `newKeySet()`, `newKeySet(int)`, `keySet()`, `keySet(V)`, `getMappedValue`, `getMap`, giá trị không bị ghi đè, null, xóa qua view và ba worker cùng thêm khóa có phần giao nhau.

Để output xác định, chương trình **sắp xếp khóa trước khi in** và **chờ tất cả `Future` của worker kết thúc** thay vì dựa vào thứ tự thread. Bài kiểm tra không sử dụng `Thread.sleep` để đoán kết quả.

Tạo file **ConcurrentKeySetDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Collections;
import java.util.List;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ConcurrentKeySetDemo {
    static String sorted(Collection<String> keys) {
        List<String> result = new ArrayList<>(keys);
        Collections.sort(result);
        return result.toString();
    }

    public static void main(String[] args) throws Exception {
        ConcurrentHashMap.KeySetView<String, Boolean> independent =
            ConcurrentHashMap.newKeySet();
        System.out.println("newKeySet default: " +
            independent.getMappedValue());
        System.out.println("newKeySet add A: " + independent.add("A"));
        System.out.println("newKeySet add A again: " + independent.add("A"));
        System.out.println("newKeySet contains A: " + independent.contains("A"));
        System.out.println("newKeySet backing A: " + independent.getMap().get("A"));

        Set<String> sized = ConcurrentHashMap.newKeySet(32);
        sized.add("capacityHint");
        System.out.println("sized set contains: " + sized.contains("capacityHint"));

        ConcurrentHashMap<String, String> map = new ConcurrentHashMap<>();
        map.put("alice", "OWNER");
        map.put("bob", "REVIEWER");
        ConcurrentHashMap.KeySetView<String, String> plain = map.keySet();
        System.out.println("plain mappedValue is null: " +
            (plain.getMappedValue() == null));
        boolean cannotAdd = false;
        try {
            plain.add("carol");
        } catch (UnsupportedOperationException expected) {
            cannotAdd = true;
        }
        System.out.println("plain add unsupported: " + cannotAdd);

        ConcurrentHashMap.KeySetView<String, String> pending =
            map.keySet("PENDING");
        System.out.println("mapped view default: " +
            pending.getMappedValue());
        System.out.println("mapped view same map: " +
            (pending.getMap() == map));
        System.out.println("add carol: " + pending.add("carol"));
        System.out.println("carol value: " + map.get("carol"));
        System.out.println("add alice again: " + pending.add("alice"));
        System.out.println("alice unchanged: " + map.get("alice"));
        System.out.println("addAll change: " +
            pending.addAll(Arrays.asList("dave", "erin")));
        System.out.println("after addAll keys: " + sorted(map.keySet()));
        System.out.println("dave value: " + map.get("dave"));

        map.put("frank", "ACTIVE");
        System.out.println("view sees direct put: " + pending.contains("frank"));
        System.out.println("view remove bob: " + pending.remove("bob"));
        System.out.println("map removed bob: " + !map.containsKey("bob"));
        System.out.println("plain view remove frank: " + plain.remove("frank"));
        System.out.println("map removed frank: " + !map.containsKey("frank"));

        ConcurrentHashMap<String, Boolean> flags = new ConcurrentHashMap<>();
        flags.put("disabled", Boolean.FALSE);
        ConcurrentHashMap.KeySetView<String, Boolean> enable =
            flags.keySet(Boolean.TRUE);
        System.out.println("existing false add result: " + enable.add("disabled"));
        System.out.println("existing false remains: " + flags.get("disabled"));

        boolean nullMappedRejected = false;
        try {
            map.keySet(null);
        } catch (NullPointerException expected) {
            nullMappedRejected = true;
        }
        System.out.println("null mappedValue rejected: " + nullMappedRejected);
        boolean nullKeyRejected = false;
        try {
            independent.add(null);
        } catch (NullPointerException expected) {
            nullKeyRejected = true;
        }
        System.out.println("null key rejected: " + nullKeyRejected);

        ConcurrentHashMap<String, Integer> deletion = new ConcurrentHashMap<>();
        deletion.put("x", 1);
        deletion.put("y", 2);
        deletion.put("z", 3);
        Set<String> deletionView = deletion.keySet(0);
        System.out.println("retainAll changed: " +
            deletionView.retainAll(Arrays.asList("x", "z")));
        System.out.println("after retainAll: " + sorted(deletion.keySet()));
        deletionView.clear();
        System.out.println("clear removes map mappings: " + deletion.isEmpty());

        final Set<String> concurrentKeys = ConcurrentHashMap.newKeySet();
        ExecutorService executor = Executors.newFixedThreadPool(3);
        CountDownLatch start = new CountDownLatch(1);
        try {
            String[][] batches = {
                {"A", "B", "C"},
                {"B", "C", "D"},
                {"A", "D", "E"}
            };
            List<Future<Integer>> results = new ArrayList<>();
            for (final String[] batch : batches) {
                results.add(executor.submit(new Callable<Integer>() {
                    public Integer call() throws Exception {
                        start.await();
                        int newlyAdded = 0;
                        for (String key : batch) {
                            if (concurrentKeys.add(key)) {
                                newlyAdded++;
                            }
                        }
                        return newlyAdded;
                    }
                }));
            }
            start.countDown();
            int totalSuccessfulAdds = 0;
            for (Future<Integer> result : results) {
                totalSuccessfulAdds += result.get(10, TimeUnit.SECONDS);
            }
            System.out.println("concurrent distinct keys: " + sorted(concurrentKeys));
            System.out.println("concurrent accepted adds: " + totalSuccessfulAdds);
            System.out.println("concurrent set size: " + concurrentKeys.size());
        } finally {
            start.countDown();
            executor.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 8 -encoding UTF-8 ConcurrentKeySetDemo.java
java ConcurrentKeySetDemo
```

Nếu chạy **trực tiếp trên JDK 8** không có cờ `--release`, dùng `javac -encoding UTF-8 ConcurrentKeySetDemo.java`; mã chỉ gọi Java 8 APIs.

**Stdout dự kiến chính xác:**

```text
newKeySet default: true
newKeySet add A: true
newKeySet add A again: false
newKeySet contains A: true
newKeySet backing A: true
sized set contains: true
plain mappedValue is null: true
plain add unsupported: true
mapped view default: PENDING
mapped view same map: true
add carol: true
carol value: PENDING
add alice again: false
alice unchanged: OWNER
addAll change: true
after addAll keys: [alice, bob, carol, dave, erin]
dave value: PENDING
view sees direct put: true
view remove bob: true
map removed bob: true
plain view remove frank: true
map removed frank: true
existing false add result: false
existing false remains: false
null mappedValue rejected: true
null key rejected: true
retainAll changed: true
after retainAll: [x, z]
clear removes map mappings: true
concurrent distinct keys: [A, B, C, D, E]
concurrent accepted adds: 5
concurrent set size: 5
```

### 14.1. Giải thích kết quả theo nhóm

1. **`newKeySet`:** `getMappedValue()` trả `true` vì giá trị mặc định được dùng là `Boolean.TRUE`. Thêm `"A"` lần đầu trả `true`, lần hai trả `false`. `getMap().get("A")` xác nhận backing map chứa `true`.
2. **Dung lượng ban đầu:** `newKeySet(32)` hoạt động như set; `32` chỉ là gợi ý sizing, không có ý nghĩa số phần tử tối đa.
3. **`keySet()` plain:** `getMappedValue() == null` và `add("carol")` ném `UnsupportedOperationException`. Map không tự bịa value cho key.
4. **`keySet("PENDING")`:** view dùng `PENDING` cho khóa mới `carol`, `dave`, `erin`. Khi `add("alice")`, value `OWNER` đã có không đổi.
5. **Tính live:** `map.put("frank","ACTIVE")` làm view nhìn thấy frank; `view.remove("bob")` và `plain.remove("frank")` đều xóa mapping khỏi map.
6. **Có khóa nhưng value false:** view `flags.keySet(Boolean.TRUE)` vẫn chứa khóa `disabled` có value `false`; `add("disabled")` không sửa giá trị đó.
7. **Null bị cấm:** `keySet(null)` và `newKeySet.add(null)` đều ném `NullPointerException`, được mã bắt để in boolean xác định.
8. **Xóa hàng loạt:** `retainAll` giữ `x,z` và loại `y` từ backing map; `clear` xóa tất cả mapping của map thử nghiệm riêng.
9. **Ba worker:** mỗi worker nhận danh sách có khóa trùng, tổng cộng có đúng `A,B,C,D,E` phân biệt. Mỗi khóa chỉ có **một `add` trả true**, nên tổng số lần thêm thành công bằng `5`, bất kể lịch scheduling. Chương trình đợi đủ các `Future` rồi mới sắp xếp/in; output không đoán thứ tự thread.

## 15. Tình huống áp dụng thực tế

### 15.1. Tập ID vừa gặp trong xử lý song song

```java
Set<String> seen = ConcurrentHashMap.newKeySet();

records.parallelStream().forEach(record -> {
    if (seen.add(record.getId())) {
        process(record);
    }
});
```

Đây là snippet kiến trúc; `records` và `process` do ứng dụng định nghĩa. Mục tiêu là tránh xử lý hai bản ghi cùng ID trong phạm vi **một lần chạy**. Cần xác nhận `process` thread-safe, không dựa vào thứ tự; nếu side effect quan trọng, bổ sung transaction/idempotency thay vì cho rằng `seen.add` bảo đảm exactly-once toàn hệ thống. Với I/O, `parallelStream` cũng chưa chắc là lựa chọn executor tối ưu; cân nhắc pool có giới hạn tài nguyên.

### 15.2. Tập token đang chạy trong một service

```java
Set<String> inFlight = ConcurrentHashMap.newKeySet();

boolean claimed = inFlight.add("task-7");
if (claimed) {
    try {
        // Thực hiện công việc được claim.
    } finally {
        inFlight.remove("task-7");
    }
}
```

Đây là snippet minh họa một claim trong cùng tiến trình. Nó có **bẫy ownership** nếu task có retries hoặc một bước hoàn thành/cleanup chậm: `remove` không kiểm tra người sở hữu, nên một worker có thể xóa key đã được một thế hệ công việc khác claim sau khi key bị xóa và thêm lại. Nếu cần kiểm soát owner/token, dùng map `key → token` và `remove(key,token)` có điều kiện.

Không dùng set RAM làm distributed lock hoặc cam kết liveness trong các hệ thống có nhiều instance.

### 15.3. Đăng ký khóa mới với trạng thái mặc định

```java
enum State { NEW, RUNNING, DONE }

ConcurrentHashMap<String, State> jobs =
    new ConcurrentHashMap<>();

Set<String> initial = jobs.keySet(State.NEW);

initial.add("job-1");
// jobs.get("job-1") == State.NEW

jobs.replace("job-1", State.NEW, State.RUNNING);
// Cập nhật có điều kiện, không dùng initial.add("job-1") để đổi state.
```

Đây là snippet trong class hoặc method thích hợp (enum cần được khai báo ở phạm vi hợp lệ). `State.NEW` là default rõ ràng. Sau khi job chuyển `RUNNING` hoặc `DONE`, nó **vẫn nằm trong set view** vì khóa vẫn tồn tại. Nếu muốn tập riêng của job NEW, cần cấu trúc/index riêng hoặc lọc entry theo value.

### 15.4. Đọc khóa từ một map đang lưu dữ liệu có ý nghĩa

```java
ConcurrentHashMap<String, UserProfile> profiles =
    new ConcurrentHashMap<>();

Set<String> userIds = profiles.keySet();
// Dùng contains/iterate khi cần thấy các user ID hiện có.
```

Đây là snippet kiến trúc, `UserProfile` được định nghĩa bởi ứng dụng. Thường **không nên** dùng `profiles.keySet(defaultProfile)` nếu mỗi profile là object độc lập, vì value chung sẽ bị chia sẻ. Muốn tạo profile theo user ID, dùng `computeIfAbsent`/`putIfAbsent` với chính sách tạo object riêng.

## 16. Vấn đề concurrency và hiệu năng

### 16.1. Thread-safe không có nghĩa mọi chuỗi thao tác đều nguyên tử

`set.add(k)` là một thao tác an toàn với cập nhật đồng thời, nhưng:

```java
if (set.contains(k)) {
    // Thread khác có thể remove(k) trước dòng tiếp theo.
    use(k);
}
```

Đây là snippet kiến trúc. Kết quả `contains` là thông tin tại thời điểm gọi, không là khóa giữ membership vĩnh viễn. Nếu cần một đoạn logic nhiều bước được bảo vệ, phải có phối hợp thêm — ví dụ map cập nhật có điều kiện, state machine, lock riêng hoặc giao thức task ownership.

Tương tự, `size()==0` trước `add` không ngăn thread khác chèn key; đừng dựa vào `if (set.isEmpty())` để thực thi side effect một lần trong hệ thống concurrent.

### 16.2. Map-key view và memory visibility

`ConcurrentHashMap` được thiết kế cho truy cập đồng thời và cung cấp các bảo đảm visibility cho các thao tác cập nhật/truy xuất trên key. Nhưng điều đó không tự làm object mutable được lưu làm **value** trở thành thread-safe sau khi thêm. Nếu một value được chia sẻ giữa các key hoặc các thread tiếp tục sửa state bên trong nó, vẫn phải thiết kế synchronization/immutability cho object đó.

Với các cấu trúc có ý nghĩa chỉ là key presence, `newKeySet()` dùng Boolean.TRUE tránh việc mỗi key cần object value phức tạp.

### 16.3. Kích thước lớn và giữ khóa mãi mãi

Một set lưu mọi ID đã thấy **không tự hết hạn**, không tự giới hạn dung lượng và có thể tăng mãi nếu key đến liên tục. `newKeySet(initialCapacity)` chỉ gợi ý kích thước khởi đầu; nó **không** áp dụng TTL, LRU, max size hoặc eviction policy.

Nếu bài toán cần dedup cửa sổ 10 phút hoặc cache bounded, cân nhắc một cache có expiration/maximumSize hoặc cấu trúc lưu thời điểm với chính sách cleanup được thiết kế rõ. Đừng chỉ tạo `newKeySet` rồi kỳ vọng runtime tự thu hồi key chưa bị xóa.

### 16.4. Khi cần thống kê chính xác hay snapshot toàn bộ

Để thống kê cuối batch, chờ hoàn thành các worker trước khi gọi `size`/duyệt. Nếu cần snapshot nhất quán trong khi vẫn có concurrent writes, phải định nghĩa cơ chế đồng bộ hoặc phiên bản dữ liệu riêng; copy set qua một iterator yếu nhất quán không tự biến thành transaction.

Không benchmark bằng cảm tính. Để so `ConcurrentHashMap.newKeySet` với một thiết kế khác, dùng workload thật với đủ warm-up và các mức contention khác nhau; trên Java có thể sử dụng JMH. Không mặc định “mọi thao tác concurrent luôn nhanh hơn HashSet” vì `HashSet` thường tốt khi **không có chia sẻ thread**.

## 17. Những lỗi phổ biến cần tránh

1. **Dùng `map.keySet().add(k)`:** ném `UnsupportedOperationException`. Muốn thêm qua view, dùng `map.keySet(nonNullDefault).add(k)`.
2. **Cho rằng `newKeySet()` nối với một map có sẵn:** sai, factory tạo backing map **riêng**; dùng `map.keySet(...)` khi cần tác động map đang tồn tại.
3. **Tưởng `keySet(mappedValue)` lọc những key có value bằng default:** sai, nó hiển thị **mọi khóa** của map.
4. **Tưởng `add(existingKey)` ghi đè value cũ:** sai, nó trả false và giữ mapping đã tồn tại.
5. **Dùng `keySet(true).add(k)` để chuyển value từ false sang true:** sai; dùng `put`/`replace`/`compute`.
6. **Truyền null làm mapped value hoặc key:** `ConcurrentHashMap` không cho phép null key/value.
7. **Nhầm `getMappedValue()==null` với một mapping null:** giá trị null ở getter này nghĩa view không hỗ trợ additions.
8. **Xóa qua view mà quên map bị ảnh hưởng:** `remove`/`retainAll`/`clear` xóa mapping thật; không phải chỉnh bộ lọc hiển thị.
9. **Dùng `remove(k)` khi chỉ muốn xóa một value cụ thể:** có thể xóa state đã được thread khác cập nhật; dùng `map.remove(k,expectedV)`.
10. **Cho rằng `addAll` là transaction nguyên tử:** nó là tập thao tác thêm nhiều phần tử, không cam kết all-or-nothing.
11. **Lặp qua set và kỳ vọng thứ tự ổn định:** iterator weakly consistent, không bảo đảm insertion order hay snapshot.
12. **Dùng `contains` rồi `add` để quyết định ai sở hữu khóa:** có race; xét trực tiếp boolean của `add`.
13. **Tin `size` chứng minh mọi side effect của task đã xong:** set membership chỉ ghi nhận key, không phải task completion.
14. **Đưa object mutable làm mappedValue chung:** nhiều khóa có thể cùng tham chiếu một object; cần kiểm soát aliasing.
15. **Dùng key mutable thay đổi `equals/hashCode` sau khi add:** membership/remove có thể không tìm được key cũ.
16. **Tưởng `newKeySet(int)` giới hạn số phần tử:** không, đó chỉ là capacity hint.
17. **Dùng set JVM để loại trùng trên nhiều server:** trạng thái không chia sẻ xuyên tiến trình/restart; cần kho chung/transaction.
18. **Để set cache giữ ID mãi:** không có TTL/eviction mặc định, có thể tăng memory liên tục.
19. **Đưa live `KeySetView` ra ngoài như tập đọc thuần:** caller vẫn có thể gọi các thao tác remove/clear. Dùng facade/wrapper phù hợp.
20. **Phụ thuộc vào chi tiết segment của ConcurrentHashMap cũ:** cách cài đặt nội bộ thay đổi theo các JDK, chỉ dựa vào API concurrency hiện được tài liệu hóa.

## 18. Bảng quyết định theo nghiệp vụ

| Tình huống | Cách dùng phù hợp | Vì sao |
| --- | --- | --- |
| Chỉ cần một Set concurrent mới | `ConcurrentHashMap.newKeySet()` | Không cần tự quản lý value |
| Ước lượng ban đầu có nhiều key | `newKeySet(initialCapacity)` | Gợi ý sizing, không giới hạn |
| Đã có map, muốn xem khóa | `map.keySet()` | View live; không thêm qua view |
| Đã có map, thêm khóa với value chung | `map.keySet(defaultValue)` | `add` tạo mapping mới tới default |
| Muốn thêm vào map nhưng mỗi key có value khác | `putIfAbsent`/`computeIfAbsent` | Có thể tạo value theo key |
| Muốn đổi value khi key đã tồn tại | `put`/`replace`/`compute`/`merge` | `Set.add` không ghi đè |
| Muốn xóa key bất kể value | `map.keySet().remove(k)` hoặc `map.remove(k)` | Xóa mapping theo key |
| Chỉ xóa khi value vẫn như dự kiến | `map.remove(k,expectedV)` | Bảo vệ cập nhật concurrent |
| Muốn những khóa có value `PENDING` | Lọc `entrySet()` theo value, hoặc index riêng | `keySet("PENDING")` không lọc |
| Chống lặp ID trong cùng JVM | `if (set.add(id))` | Chỉ một lần thêm mới theo key |
| Loại trùng nhiều server/restart | Database unique key/kho idempotency chung | Set trong RAM không chia sẻ |
| Duyệt để debug, yêu cầu output ổn định | Sau khi writer dừng, copy và sort | Set không hứa thứ tự |
| Tập khóa dùng cho read-only API | Wrapper chỉ đọc hoặc copy khi phù hợp | View live vẫn có quyền xóa |
| Cần số liệu nhất quán toàn bộ map | Đồng bộ batch hoặc cơ chế snapshot riêng | Iterator/size không phải transaction |
| Muốn set tự hết hạn | Cache TTL/bounded có chính sách rõ | `newKeySet` không tự eviction |

## 19. Câu hỏi tự luyện và đáp án

**1.** `ConcurrentHashMap.newKeySet()` dùng default mapped value gì?  
**Đáp án:** `Boolean.TRUE` trong backing `ConcurrentHashMap<K,Boolean>` mới.

**2.** `map.keySet()` có thể thêm khóa mới bằng `add` không?  
**Đáp án:** không. Nó ném `UnsupportedOperationException` vì không có default mapped value cho additions.

**3.** `map.keySet("NEW").add("A")` làm gì nếu `"A"` chưa có?  
**Đáp án:** thêm mapping `A → NEW` vào map, trả true.

**4.** Nếu `map.get("A") == "ACTIVE"`, `map.keySet("NEW").add("A")` có đổi thành NEW không?  
**Đáp án:** không; `add` trả false, giữ value `ACTIVE`.

**5.** Có thể dùng hai view `map.keySet("NEW")` và `map.keySet("DONE")` để phân nhóm các khóa theo trạng thái không?  
**Đáp án:** không. Cả hai đều thấy tất cả key trong cùng map; khác nhau ở default value **khi thêm**.

**6.** `KeySetView.getMappedValue() == null` biểu thị điều gì?  
**Đáp án:** view không có default cho `add`, thường là view tạo bởi `map.keySet()`, không phải có entry với null value.

**7.** `KeySetView.getMap()` trả clone hay map gốc?  
**Đáp án:** trả **backing map thật**; các thay đổi qua một phía tác động phía còn lại.

**8.** `map.keySet("NEW").remove("A")` có chỉ xóa nếu value vẫn là NEW không?  
**Đáp án:** không. Nó xóa mapping theo key bất kể value hiện tại; cần `map.remove("A","NEW")` cho conditional remove.

**9.** Tại sao `keySet(Boolean.TRUE).add("A")` không “bật” được key A đang map tới Boolean.FALSE?  
**Đáp án:** key đã tồn tại, `add` chỉ xét membership và không cập nhật value.

**10.** `newKeySet(100)` có giới hạn tối đa 100 phần tử không?  
**Đáp án:** không, `100` chỉ là initial capacity hint.

**11.** `newKeySet().add(null)` và `map.keySet(null)` có hợp lệ không?  
**Đáp án:** không, đều bị từ chối bằng `NullPointerException`.

**12.** Iterator của `KeySetView` có cam kết luôn nhìn thấy mọi insert xảy ra trong lúc đang duyệt không?  
**Đáp án:** không. Nó weakly consistent, không hứa snapshot hoặc đầy đủ thay đổi concurrent.

**13.** Hai thread cùng `add("X")` khi X ban đầu vắng mặt có thể cả hai đều nhận true không?  
**Đáp án:** không đối với thao tác thêm mới cùng khóa đó; chỉ một lời gọi tạo thành viên mới thành công, nếu không có thao tác remove/xóa giữa hai lần add.

**14.** Nếu một thread remove X giữa hai lần add của hai thread khác thì có thể có hơn một `add("X") == true` theo thời gian không?  
**Đáp án:** có. Vì sau remove, X lại vắng mặt; một lần add khác có thể tạo membership mới. “Một lần đầu tiên” chỉ đúng cho **mỗi giai đoạn không có remove**.

**15.** `Set.size() == 5` khi có nhiều writer đang chạy có chứng minh 5 tác vụ đã xử lý xong không?  
**Đáp án:** không. Đây là số phần tử quan sát được, không phải trạng thái side effect; cần chờ completion/đồng bộ workflow.

**16.** Muốn mỗi key mới có một object cấu hình riêng, nên dùng `keySet(sharedMutableObject)` hay `computeIfAbsent`?  
**Đáp án:** thường dùng `computeIfAbsent` để khởi tạo theo key; không chia sẻ một mutable object vô tình.

**17.** `view.clear()` trên view của một map có value riêng có giữ nguyên map gốc không?  
**Đáp án:** không. Nó xóa tất cả mapping trong backing map.

**18.** `addAll` qua view có được coi là một giao dịch nguyên tử không?  
**Đáp án:** không. Nó thực hiện các phép thêm từng phần tử theo contract Collection, không có bảo đảm transaction toàn bộ.

**19.** Khi cần một Set thread-safe cho ID đã thấy trong cùng JVM, lựa chọn ngắn gọn là gì?  
**Đáp án:** `Set<Id> ids = ConcurrentHashMap.newKeySet();` với `Id` là kiểu khóa thích hợp.

**20.** Khi cần dedup xuyên nhiều instance và bền qua restart, chỉ dùng `newKeySet` đủ chưa?  
**Đáp án:** chưa. Cần cơ chế lưu trữ/điều phối chung theo domain.

## 20. Tài liệu API chính thức vẫn được duy trì

Các API chính trong bài đều xuất hiện từ **Java 8** và còn được hỗ trợ. Không có phụ thuộc vào thiết kế segment cũ hay API legacy:

- [`ConcurrentHashMap` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): `newKeySet`, `keySet()`, `keySet(mappedValue)`, cập nhật đồng thời, null, iterator yếu nhất quán, `mappingCount`.
- [`ConcurrentHashMap.KeySetView` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.KeySetView.html): `getMap()`, `getMappedValue()`, `add`/`addAll`, `remove`, `clear` và các phương thức Set.
- [`ConcurrentHashMap` — Java 8 API](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/ConcurrentHashMap.html): chứng thực các overload `newKeySet()`, `newKeySet(int)` và `keySet(V)` có từ Java 8.
- [`Set` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html): `add`, `remove`, `equals`/`hashCode`, ngữ nghĩa membership.
- [`Map` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html): `putIfAbsent`, `remove(key,value)`, `computeIfAbsent` và phân biệt thao tác trên key/value.
- [`CountDownLatch` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CountDownLatch.html): phối hợp thời điểm bắt đầu của worker.
- [`ExecutorService` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html): chạy worker và giải phóng pool.
