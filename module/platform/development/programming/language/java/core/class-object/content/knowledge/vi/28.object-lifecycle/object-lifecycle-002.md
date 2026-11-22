# Biến cục bộ, trường và các đường tham chiếu giữ đối tượng tồn tại — Java 17

## Mục tiêu

Khi viết Java, ta tạo các đối tượng bằng `new`, lưu tham chiếu trong biến cục bộ, instance field, static field, phần tử mảng hoặc collection, rồi truyền các tham chiếu ấy qua những lời gọi phương thức. Để hiểu **vòng đời đối tượng**, điều quan trọng không phải chỉ là biến nào đang được khai báo, mà là **còn đường tham chiếu nào từ một ngữ cảnh đang hoạt động đến đối tượng hay không**.

Một đối tượng **reachable** nếu chương trình còn có thể truy cập nó theo những đường tham chiếu phù hợp. Garbage collector (GC) có thể thu hồi vùng nhớ của những đối tượng **không còn reachable theo quy tắc của JVM/Java Memory Model**, nhưng việc thu hồi diễn ra khi nào là quyết định của runtime: **Java không bảo đảm cứ hết khối lệnh, đặt biến bằng `null` hoặc gọi `System.gc()` là đối tượng được thu gom ngay**.

Bài học thuộc **Java Core — Class/Object — Vòng đời đối tượng**, sử dụng Java 17, tập trung vào:

- Phân biệt **đối tượng**, **biến tham chiếu**, **reference value** và **đường tham chiếu**.
- Hiểu tác dụng khác nhau của **biến cục bộ**, **instance fields**, **static fields**, **array elements**, **collections**, **closure/lambda**, **inner classes** và **ThreadLocal** đối với reachability.
- Đọc **đồ thị tham chiếu** bắt đầu từ các **GC roots**; xác định khi nào một đối tượng còn có đường mạnh và khi nào có thể trở thành unreachable.
- Phân biệt **thời hạn tên biến có hiệu lực (scope)**, **thời điểm tham chiếu còn sống (liveness)**, **thời điểm có thể thu gom**, **thời điểm GC thực sự thu gom** và **lifecycle của tài nguyên**.
- Nhận diện **memory leaks theo nghĩa Java**: đối tượng vẫn reachable nhưng chương trình không còn cần nó.
- Sử dụng đúng `WeakReference`, `ReferenceQueue`, `WeakHashMap`, `Reference.reachabilityFence` và `AutoCloseable` khi thích hợp, không biến GC thành cơ chế cleanup chính.
- Tập đọc tình huống alias, reassignment, cycles, object graph, listener registration, caches và thread pools.

Các chương trình có tên file riêng, lệnh `javac --release 17`/`java` và stdout xác định; các nhận định về thời điểm GC được nêu với giới hạn phù hợp.

## 1. Đối tượng không đồng nghĩa với biến tham chiếu

Xét:

```java
StringBuilder first = new StringBuilder("A");
StringBuilder second = first;
```

Có **một đối tượng `StringBuilder`** được tạo. Hai local variables `first` và `second` chứa **hai reference values** đang cùng trỏ đến đối tượng ấy.

`first` và `second` không phải hai “bản sao đối tượng”. Việc gán `second = first` sao chép giá trị tham chiếu, không gọi constructor hay clone.

Đồ thị:

```text
Local variable first  ─┐
                       ├──▶ StringBuilder("A")
Local variable second ─┘
```

Nếu `first = null;`, đường tham chiếu từ `first` biến mất, **nhưng `second` vẫn trỏ tới đối tượng**. Không thể kết luận đối tượng không còn reachable chỉ từ việc một biến thành null.

### Định nghĩa cần tách riêng

- **Object**: thực thể runtime có identity/state/behavior.
- **Variable**: chỗ lưu giá trị có kiểu; với reference type, giá trị thường là reference hoặc null.
- **Reference**: giá trị giúp tham chiếu một object (hoặc null).
- **Alias**: nhiều references trỏ cùng object.
- **Reference graph**: các đối tượng/roots là nodes; references tạo các edges.
- **Reachability**: có hay không đường hợp lệ từ nguồn có thể truy cập tới một object, với các loại tham chiếu và quy tắc JVM tương ứng.

## 2. Runnable: hai local references cùng giữ một đối tượng

Lưu **`LocalAliasesDemo.java`**:

```java
public class LocalAliasesDemo {
    public static void main(String[] args) {
        StringBuilder first = new StringBuilder("Java");
        StringBuilder second = first;

        System.out.println(first == second);
        first = null;

        second.append(" 17");

        System.out.println(second);
        System.out.println(first == null);
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 LocalAliasesDemo.java
java LocalAliasesDemo
```

Stdout:

```text
true
Java 17
true
```

Đặt `first = null` chỉ thay **giá trị của một local variable**. Nó không xóa đối tượng và không vô hiệu hóa alias `second`.

## 3. “Giữ đối tượng tồn tại” chính xác nghĩa là gì?

Trong cách nói thực dụng, một đường **strong reference** có thể sử dụng được từ một **GC root** là lý do để GC không coi đối tượng đích là rác. Tuy nhiên nên phân biệt hai mức:

1. **Mô hình suy luận:** một live root trỏ tới object A; A có field trỏ B; B có field trỏ C. Còn đường root → A → B → C thì C còn strong-reachable.
2. **Triển khai JVM:** compiler/JIT và collector xác định liveness/roots ở các thời điểm phù hợp, có thể tối ưu hóa variables và allocation. Một biến còn nằm trong lexical scope **không mặc nhiên buộc** object phải sống cho đến cuối block.

Nói cách khác, **scope của tên biến không phải đồng hồ đếm ngược cho GC**.

### GC roots thường gặp về mặt thực thi

Tùy collector và điểm quan sát, những nơi được xem xét như roots có thể gồm:
- Các tham chiếu còn **live** trong stack frames/registers của threads đang hoạt động.
- Một số tham chiếu từ static state của các classes còn sống.
- Runtime/JNI/native handles và những cấu trúc đặc biệt do JVM quản lý.
- Các references cần thiết cho thực thi tiếp theo.

Không phải mọi biến cục bộ từng được khai báo hoặc mọi field static từng tồn tại đều là **root vĩnh viễn**. Một instance field **không tự là root**: nó chỉ tạo thêm một cạnh nếu object chủ sở hữu của field đã reachable.

## 4. Đọc một đường tham chiếu từ root tới object

Giả sử:

```text
[GC root: live local variable]
             │
             ▼
          Session
             │ user
             ▼
            User
             │ cart
             ▼
         ShoppingCart
             │ items
             ▼
         ArrayList
             │ element[0]
             ▼
          CartItem
```

Nếu một local reference đang live trỏ tới Session, và các instance fields/collection elements được giữ như hình, thì CartItem có một **đường tham chiếu mạnh** từ root.

Nếu Session không còn reachable theo bất kỳ root/path mạnh nào, toàn bộ graph có thể không còn strong-reachable, trừ các đường khác (chẳng hạn một static cache khác giữ User hoặc CartItem).

### Quy tắc quan trọng

Không cần **một biến local trực tiếp** trỏ CartItem. Đường gián tiếp qua nhiều fields và collection elements vẫn có thể giữ CartItem reachable.

## 5. Biến cục bộ: vị trí khai báo và thời hạn tồn tại

Biến cục bộ (*local variable*) được khai báo trong method, constructor, block, `for` hoặc các scope phù hợp:

```java
void process() {
    Object item = new Object();
    use(item);
}
```

Khi gọi `process()`, reference `item` có thể là một root-reachable reference trong thời gian còn cần cho thực thi. Sau khi method trả về, caller không nhận hay lưu item ở nơi khác, đường tham chiếu local đó không còn.

Tuy nhiên:
- Không có quy tắc “sau dấu `}` JVM lập tức gọi GC”.
- Object có thể trở nên không còn cần thiết **trước** dấu `}` nếu không còn lần dùng nào ảnh hưởng thực thi và runtime có thể chứng minh liveness phù hợp.
- Reference có thể thoát (*escape*) qua return, field, collection hoặc callback, khiến object sống lâu hơn lời gọi method.
- JVM có thể tối ưu allocation; không nên khẳng định lúc nào cũng có một heap object thực sự được materialize cho mọi `new`.

**Scope quyết định bạn được dùng tên local ở chỗ nào. Reachability quyết định object còn có thể được truy cập theo những đường còn sống nào.** Hai khái niệm có liên quan nhưng không đồng nhất.

## 6. Runnable: một block scope không quyết định GC

Lưu **`LocalScopeDemo.java`**:

```java
public class LocalScopeDemo {
    public static void main(String[] args) {
        StringBuilder retained;

        {
            StringBuilder temporary = new StringBuilder("data");
            retained = temporary;
        }

        System.out.println(retained);
        retained.append("-kept");
        System.out.println(retained);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 LocalScopeDemo.java
java LocalScopeDemo
```

Stdout:

```text
data
data-kept
```

Tên `temporary` hết scope khi rời block, nhưng object vẫn truy cập được qua `retained`. Scope của biến **không ràng buộc lifetime của object** khi reference đã được sao chép sang nơi khác.

## 7. Reassignment chỉ đổi một cạnh

```java
Node a = new Node("A");
Node b = new Node("B");

a = b;
```

Sau dòng cuối, reference variable `a` cũng trỏ tới object B. Đối tượng A ban đầu **có thể** mất đường từ `a`, nhưng còn reachable hay không tùy có đường khác trỏ A không.

Đồ thị lý tưởng hóa:

```text
Trước:
a ──▶ [A]
b ──▶ [B]

Sau a = b:
a ──┐
    ├──▶ [B]
b ──┘
[A] không còn cạnh từ hai local này.
```

Không có lệnh `delete A` tương ứng trong Java. GC tự theo dõi reachability, không đồng nhất với phép gán.

### Đặt `null` cũng là reassignment

`a = null;` không gọi destructor trên object đích cũ. Nó chỉ loại bỏ cạnh reference từ một vị trí lưu trữ; các references khác có thể giữ object tồn tại.

## 8. Runnable: reassignment không hủy các alias

Lưu **`ReferenceReassignmentDemo.java`**:

```java
final class Item {
    final String id;

    Item(String id) {
        this.id = id;
    }
}

public class ReferenceReassignmentDemo {
    public static void main(String[] args) {
        Item original = new Item("old");
        Item alias = original;
        Item replacement = new Item("new");

        original = replacement;

        System.out.println(original.id);
        System.out.println(alias.id);
        System.out.println(original == alias);
        System.out.println(original == replacement);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ReferenceReassignmentDemo.java
java ReferenceReassignmentDemo
```

Stdout:

```text
new
old
false
true
```

Dù `original` được trỏ lại, object cũ vẫn còn reference `alias` trong phần chương trình còn sử dụng nó.

## 9. Java truyền tham số theo giá trị — giá trị có thể là reference

Khi gọi:

```java
change(object);
```

Java truyền **một bản sao của reference value** vào parameter. Đây là *pass-by-value*, không phải “pass-by-reference” theo nghĩa function có thể thay trực tiếp biến reference ở caller.

Hệ quả:
- Method có thể **mutate object** qua reference (nếu object/method cho phép).
- Method **không thể gán lại chính local variable của caller** chỉ bằng cách gán lại formal parameter.
- Nếu method lưu reference vào field/static/list, object có thể thoát ra ngoài lifetime của caller.

### Hai thao tác cần so sánh

```java
void replace(StringBuilder p) {
    p = new StringBuilder("new");
}

void change(StringBuilder p) {
    p.append("!");
}
```

`replace` đổi parameter local; `change` làm thay đổi state của object được chia sẻ.

## 10. Runnable: gán parameter vs sửa object

Lưu **`ParameterReferenceDemo.java`**:

```java
public class ParameterReferenceDemo {
    static void replace(StringBuilder value) {
        value = new StringBuilder("replaced");
    }

    static void mutate(StringBuilder value) {
        value.append("!");
    }

    public static void main(String[] args) {
        StringBuilder text = new StringBuilder("hello");

        replace(text);
        System.out.println(text);

        mutate(text);
        System.out.println(text);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ParameterReferenceDemo.java
java ParameterReferenceDemo
```

Stdout:

```text
hello
hello!
```

Trong `replace`, object mới được tạo nhưng reference mới **không thoát khỏi method**; điều đó khác với `mutate` tác động đúng object caller còn giữ.

## 11. Trường đối tượng (*instance fields*) tạo những cạnh kéo dài qua method

Một instance field nằm trong object chủ sở hữu:

```java
final class Profile {
    Address address;
}
```

Khi một reachable `Profile` có field `address` trỏ `Address`, đường:

```text
root → Profile → address → Address
```

có thể giữ Address strong-reachable.

Instance field **không tự là root**. Điều kiện chính là owner object Profile có reachable không, và có thể có các cạnh khác cùng trỏ Address.

### Field assignment làm đổi đồ thị

`profile.address = replacement;` thay cạnh từ Profile đến Address mới. Address cũ không nhất thiết được thu gom nếu còn một biến khác giữ nó.

`profile.address = null;` xóa một cạnh. Không nhất thiết khiến Address cũ unreachable nếu map/cache/owner khác còn giữ.

## 12. Runnable: local chỉ giữ owner, owner field giữ child

Lưu **`InstanceFieldGraphDemo.java`**:

```java
final class Address {
    final String city;

    Address(String city) {
        this.city = city;
    }
}

final class User {
    final String name;
    Address address;

    User(String name, Address address) {
        this.name = name;
        this.address = address;
    }
}

public class InstanceFieldGraphDemo {
    public static void main(String[] args) {
        Address first = new Address("Hanoi");
        User user = new User("An", first);

        first = null;

        System.out.println(user.name);
        System.out.println(user.address.city);

        user.address = new Address("Hue");
        System.out.println(user.address.city);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 InstanceFieldGraphDemo.java
java InstanceFieldGraphDemo
```

Stdout:

```text
An
Hanoi
Hue
```

Sau `first = null`, owner `user` vẫn giữ Address("Hanoi") qua field. Sau khi thay field, object Address cũ có thể không còn đường từ graph này, **nhưng không có bằng chứng về thời điểm GC**.

## 13. Field chain: các đường dài là điều bình thường

Giả sử:

```java
company.department.manager.address.city
```

Biểu thức truy cập nhiều fields. Nếu `company` là một reference đang dùng được, mỗi field trỏ object phù hợp, thì đọc `city` đi theo nhiều **cạnh** trong graph.

Một sơ đồ:

```text
live root
  └──▶ company
           └── department ──▶ Department
                                └── manager ──▶ Manager
                                                 └── address ──▶ Address
```

Khi cần giải thích memory retention:
1. Xác định object đang bị giữ (ví dụ Address).
2. Tìm tất cả **incoming strong edges** đến nó.
3. Lần ngược tới GC root đang giữ graph sống.
4. Xác định cạnh nào đáng lẽ được xóa khi kết thúc nghiệp vụ.

Một object có thể có **nhiều đường độc lập**. Xóa một đường không đủ nếu đường khác vẫn nối root đến object.

## 14. Mảng là tập các ô chứa reference

Với array of references:

```java
Object[] slots = new Object[3];
Object value = new Object();
slots[0] = value;
```

Array `slots` là object. Phần tử `slots[0]` là một vị trí chứa reference đến `value`.

Nếu một root còn giữ array:
- `slots[0]` là một cạnh giữ object đích.
- `value = null;` chỉ bỏ cạnh local; array vẫn giữ.
- `slots[0] = null;` bỏ cạnh từ array.
- Mảng primitive như `int[]` chứa primitive values, không chứa references đến `Integer` objects trên từng element.

Đặc biệt với array dài, một phần tử giữ reference tới object đồ sộ có thể khiến object graph lớn còn reachable ngoài ý muốn.

## 15. Runnable: phần tử mảng giữ đối tượng

Lưu **`ArrayReferenceDemo.java`**:

```java
public class ArrayReferenceDemo {
    public static void main(String[] args) {
        StringBuilder[] slots = new StringBuilder[2];

        StringBuilder value = new StringBuilder("kept");
        slots[0] = value;

        value = null;

        System.out.println(slots[0]);
        System.out.println(slots[1] == null);

        slots[0] = null;
        System.out.println(slots[0] == null);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ArrayReferenceDemo.java
java ArrayReferenceDemo
```

Stdout:

```text
kept
true
true
```

Đây là một demo **reference graph**, không phải bằng chứng GC đã chạy khi `slots[0] = null`.

## 16. Collection giữ các tham chiếu đến phần tử

Một collection như `ArrayList<Customer>`, `HashSet<Customer>` hoặc `HashMap<Key,Value>` có thể lưu những references trong cấu trúc nội bộ của nó.

Ví dụ:

```java
List<Order> orders = new ArrayList<>();
Order order = new Order(...);
orders.add(order);
order = null;
```

Nếu `orders` vẫn reachable thì `Order` vẫn có một đường tham chiếu mạnh qua collection.

### Những thao tác thay đổi đường giữ

- `list.remove(element)` hoặc `list.clear()` bỏ references do list giữ đến các entries phù hợp.
- `map.remove(key)` hoặc `map.clear()` bỏ các mappings/references của map.
- `set.remove(element)` bỏ entry tương ứng.
- Vẫn cần xét **các aliases ở chỗ khác**.
- `clear` không làm GC ngay; nó chỉ thay đổi graph/collection state.
- Một collection thường còn có chính các internal backing arrays/buckets đang sống như phần của collection object; capacity không đồng nghĩa còn giữ các element references cũ sau khi clear theo contract thích hợp.

### Map giữ cả keys và values

Trong `HashMap<K,V>` bình thường, khi map object reachable, nó giữ **strong references** đến keys và values. Một value có thể còn giữ rất nhiều objects phía dưới nó.

## 17. Runnable: list giữ object sau khi local đổi

Lưu **`ListRetentionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ListRetentionDemo {
    public static void main(String[] args) {
        List<StringBuilder> values = new ArrayList<>();

        StringBuilder original = new StringBuilder("saved");
        values.add(original);

        original = null;

        System.out.println(values.get(0));
        System.out.println(values.size());

        values.clear();

        System.out.println(values.isEmpty());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ListRetentionDemo.java
java ListRetentionDemo
```

Stdout:

```text
saved
1
true
```

Sau `original = null`, list vẫn giữ StringBuilder. Sau `clear()`, đường từ list tới phần tử bị loại bỏ; điều này không khẳng định phần tử đã được GC.

## 18. Static field: đường giữ vượt qua một method và nhiều instances

Ví dụ:

```java
final class Cache {
    static Object saved;
}
```

Nếu class tương ứng vẫn đang được JVM xem là live theo quy tắc class loading/lifetime, một static field `Cache.saved` trỏ tới object có thể là đường tham chiếu mạnh giữ object đó.

`Cache.saved` không thuộc về **một instance Cache** cụ thể. Nó là state của class, có thể được nhiều method, nhiều object sử dụng.

### Tình huống hay gây leak

```java
static final List<Session> sessions = new ArrayList<>();
```

`final` chỉ ngăn **gán lại reference field `sessions`**. Nó **không** ngăn `sessions.add(...)` và không ngăn collection giữ những Session objects lâu hơn cần thiết.

### Static không đồng nghĩa tồn tại vĩnh viễn

Không nên tuyên bố “static object luôn sống cho tới khi JVM tắt” trong mọi môi trường:
- Class loaders/modules và class unloading có quy tắc lifetime riêng.
- Objects trong static fields có thể được thay, xóa hoặc không còn reachable khi class/class loader không còn sống.
- Một số optimizations của runtime ảnh hưởng object materialization/liveness.

Trong một application long-running, **static cache/list là một root path cần điều tra đầu tiên** khi nghi ngờ retention, nhưng phải kiểm tra thực tế.

## 19. Runnable: static reference tiếp tục giữ qua nhiều lời gọi

Lưu **`StaticReferenceDemo.java`**:

```java
final class SharedCache {
    static StringBuilder saved;

    static void remember(StringBuilder value) {
        saved = value;
    }

    static void clear() {
        saved = null;
    }
}

public class StaticReferenceDemo {
    static void createAndRemember() {
        StringBuilder temporary = new StringBuilder("cached");
        SharedCache.remember(temporary);
    }

    public static void main(String[] args) {
        createAndRemember();

        System.out.println(SharedCache.saved);
        System.out.println(SharedCache.saved != null);

        SharedCache.clear();

        System.out.println(SharedCache.saved == null);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 StaticReferenceDemo.java
java StaticReferenceDemo
```

Stdout:

```text
cached
true
true
```

Local `temporary` đã ra khỏi method, nhưng reference được lưu trong static field. `clear()` xóa **cạnh static cache → object**, không phải gọi destructor.

## 20. Static field, instance field và local: bảng tổng hợp

| Loại chỗ giữ reference | Thuộc về đâu? | Đường tham chiếu có thể kéo dài bao lâu? | Sai lầm điển hình |
| --- | --- | --- | --- |
| Local variable | Execution của method/block | Khi reference còn cần cho thực thi | Đồng nhất scope với lifetime |
| Formal parameter | Một lần gọi method/constructor | Có thể thoát nếu được lưu/trả | Nghĩ method gán parameter sẽ thay biến caller |
| Instance field | Một object owner | Khi owner reachable và field giữ reference | Tưởng field tự là GC root |
| Static field | Runtime class state | Có thể vượt nhiều method/instances | Cache không eviction, nghĩ static luôn sống mãi |
| Array element | Array object | Khi array reachable và entry còn reference | Chỉ gán null cho local nhưng quên array |
| Collection entry | Collection/backing structure | Khi collection reachable và entry tồn tại | Quên remove listener/cache/map item |
| Lambda/closure field | Functional object | Khi callback/functional object reachable | Cất lambda lâu dài nhưng quên captured object |
| Non-static inner class | Inner instance | Có thể giữ enclosing instance | Outer unexpectedly retained |
| ThreadLocal mapping | State gắn với thread | Theo thread/cleanup rules | Không remove trong thread pool |

Bảng này mô tả **đường tham chiếu**, không đưa ra lịch GC cụ thể.

## 21. Chu trình tham chiếu (*reference cycle*) không tự là memory leak

Hai objects giữ nhau:

```java
Node a = new Node();
Node b = new Node();
a.next = b;
b.next = a;
```

Đồ thị:

```text
root → A ──▶ B
       ▲     │
       └─────┘
```

Nếu root vẫn giữ A, cả A và B reachable. Nếu không còn bất kỳ đường từ roots tới A/B, **chỉ riêng chu trình A↔B không đủ giữ hai objects strong-reachable**.

Điểm này khác với một số mô hình quản lý bộ nhớ chỉ dựa vào đếm tham chiếu đơn giản. Các garbage collectors theo reachability/tracing trong JVM có thể thu gom cyclic object graphs khi graph unreachable; không cần tự “break every cycle” chỉ để GC có thể xử lý.

**Nhưng** nếu một static map, long-lived thread hoặc object root vẫn giữ A, cả cycle vẫn còn reachable và có thể trở thành leak theo nghĩa sử dụng bộ nhớ ngoài ý muốn.

## 22. Runnable: đọc một reference cycle

Lưu **`ReferenceCycleDemo.java`**:

```java
final class Node {
    final String label;
    Node next;

    Node(String label) {
        this.label = label;
    }
}

public class ReferenceCycleDemo {
    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");

        a.next = b;
        b.next = a;

        System.out.println(a.next.label);
        System.out.println(b.next.label);
        System.out.println(a.next.next == a);

        a = null;
        System.out.println(b.next.label);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ReferenceCycleDemo.java
java ReferenceCycleDemo
```

Stdout:

```text
B
A
true
A
```

Sau `a = null`, local `b` vẫn trỏ tới B, và B.next trỏ A. Đừng tuyên bố cycle bị thu gom vào thời điểm này. Nếu tất cả roots/path tới graph mất đi, cyclicity tự nó không ngăn GC.

## 23. Hai đường độc lập: xóa một vẫn còn đường kia

Một object có thể nằm trong cả hai collections:

```text
root → customersCache ──▶ Customer#42
root → recentCustomers ───▶ Customer#42
```

Xóa entry khỏi `customersCache` **không đủ** nếu `recentCustomers` còn giữ cùng object.

Khi phân tích memory retention, hỏi:
1. Có bao nhiêu **incoming strong paths** tới object?
2. Mỗi path bắt đầu từ đâu?
3. Có root path nào sống lâu hơn expected object lifecycle?
4. Ai sở hữu trách nhiệm remove/clear reference?
5. Nếu giải pháp chỉ dọn một container, container khác còn giữ không?

Một object có thể là key của Map A, value của Map B, listener của EventBus và field của một singleton service cùng lúc.

### Identity của object vs equality của keys

Map/Set dựa trên `equals/hashCode` cho lookup logic; nhưng chúng vẫn giữ **object references thực tế** trong entries. Hai objects bằng nhau theo `equals` không có nghĩa chúng là một object ở memory graph.

## 24. Runnable: hai containers cùng giữ một object

Lưu **`MultipleOwnersDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class MultipleOwnersDemo {
    public static void main(String[] args) {
        List<StringBuilder> left = new ArrayList<>();
        List<StringBuilder> right = new ArrayList<>();

        StringBuilder shared = new StringBuilder("shared");

        left.add(shared);
        right.add(shared);

        left.clear();

        System.out.println(right.get(0) == shared);
        System.out.println(right.get(0));

        right.clear();
        System.out.println(right.isEmpty());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 MultipleOwnersDemo.java
java MultipleOwnersDemo
```

Stdout:

```text
true
shared
true
```

Sau khi left được clear, right vẫn giữ shared. Trong program này local `shared` còn là một path khác; vì vậy ngay cả clear cả hai lists cũng không chứng minh object đã unreachable ngay lập tức.

## 25. Đối tượng trả về có thể sống lâu hơn method tạo nó

```java
static StringBuilder make() {
    StringBuilder local = new StringBuilder("created");
    return local;
}
```

Khi return, reference được chuyển tới caller:

```java
StringBuilder result = make();
```

Local `local` biến mất sau call, nhưng caller có `result`. Object **escape qua return value**.

Trái lại, nếu một method tạo object, chỉ sử dụng cục bộ và không lưu/trả nó, sau điểm cuối nó được sử dụng thì có thể trở nên unreachable (tùy các paths khác).

### Không hiểu return như sao chép object

Java trả reference value, không tự clone StringBuilder. Nếu caller sửa object trả về, caller đang sửa chính object mà method tạo.

## 26. Runnable: return chuyển một đường tham chiếu sang caller

Lưu **`ReferenceReturnDemo.java`**:

```java
public class ReferenceReturnDemo {
    static StringBuilder create() {
        StringBuilder local = new StringBuilder("hello");
        return local;
    }

    public static void main(String[] args) {
        StringBuilder returned = create();
        returned.append("-caller");

        System.out.println(returned);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ReferenceReturnDemo.java
java ReferenceReturnDemo
```

Stdout:

```text
hello-caller
```

Sự kết thúc của method `create` không kết thúc lifetime của object trả về.

## 27. Lambda và capture có thể giữ một object sống qua method

Lambda có thể capture một **effectively final local variable**. Nếu một functional object chứa/có cách giữ reference đến captured object, và chính functional object được lưu lâu dài, đường tham chiếu tới captured object có thể kéo dài lâu hơn local scope.

Ví dụ:

```java
StringBuilder data = new StringBuilder("A");
Runnable task = () -> System.out.println(data);
```

Dù method tạo lambda đã return, caller hoặc registry giữ `task` có thể giữ luôn `data`.

**Cần phân biệt hai điều:**
- Lambda capture một local **reference value**, không phải “biến local sống trên stack mãi”.
- Java compiler/JVM có quyền lựa chọn implementation details của lambda; không nên xây logic dựa vào tên field bên trong synthetic lambda class.

### Effectively final

Biến local được capture phải final hoặc effectively final. Điều đó **không** khiến referenced object immutable.

`StringBuilder` vẫn có thể bị thay đổi qua method `append`. Nếu bạn cố gán lại chính biến local đã bị capture, compiler từ chối.

## 28. Runnable: callback giữ một object sau method return

Lưu **`LambdaCaptureDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class LambdaCaptureDemo {
    static final List<Runnable> TASKS = new ArrayList<>();

    static void register() {
        StringBuilder message = new StringBuilder("captured");
        TASKS.add(() -> System.out.println(message));
    }

    public static void main(String[] args) {
        register();
        TASKS.get(0).run();

        TASKS.clear();
        System.out.println(TASKS.isEmpty());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 LambdaCaptureDemo.java
java LambdaCaptureDemo
```

Stdout:

```text
captured
true
```

`register` đã return trước `TASKS.get(0).run()`, nhưng lambda vẫn in được message vì callback được registry giữ. `clear` bỏ đường từ TASKS tới callback; GC không được kiểm chứng bằng output ở đây.

## 29. Listener registration: nguồn retention rất thường gặp

Một object owner đăng ký callback vào một long-lived event bus:

```text
GC root
  └── static EventBus
        └── listeners list
              └── lambda/listener
                    └── captured view/controller
                          └── UI subtree
```

Nếu màn hình đã đóng nhưng listener vẫn còn trong bus, graph màn hình có thể vẫn reachable.

Đây là **memory leak theo nghĩa ứng dụng**: bộ nhớ không được reclaim vì code còn giữ reference mà nó **không còn có mục đích sử dụng**.

Cách xử lý:
- Đăng ký và gỡ đăng ký theo cùng lifecycle: `addListener`/`removeListener`.
- Trả về một `Registration`/`Subscription` có `close()`.
- Với framework có lifecycle, dùng API cleanup đúng như `dispose`, `stop`, `onDestroy` phù hợp.
- Weak listener là lựa chọn trong một số thiết kế, nhưng không thay thế việc xác định owner lifecycle một cách tự động.
- Không chỉ gọi `System.gc()`: strong path của listener vẫn tồn tại.

## 30. Runnable: đăng ký và hủy listener có kiểm soát

Lưu **`ListenerRetentionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class EventBus {
    private final List<Runnable> listeners = new ArrayList<>();

    void subscribe(Runnable listener) {
        listeners.add(listener);
    }

    void unsubscribe(Runnable listener) {
        listeners.remove(listener);
    }

    void fire() {
        for (Runnable listener : listeners) {
            listener.run();
        }
    }

    int count() {
        return listeners.size();
    }
}

public class ListenerRetentionDemo {
    public static void main(String[] args) {
        EventBus bus = new EventBus();
        StringBuilder screen = new StringBuilder("screen");

        Runnable listener = () -> System.out.println(screen);

        bus.subscribe(listener);
        bus.fire();

        System.out.println(bus.count());
        bus.unsubscribe(listener);
        System.out.println(bus.count());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ListenerRetentionDemo.java
java ListenerRetentionDemo
```

Stdout:

```text
screen
1
0
```

Gỡ registration xóa một **đường reference** từ EventBus đến callback. Biến local `listener` và `screen` vẫn tồn tại ở main trong ví dụ này; thao tác unsubscribing không đồng nghĩa được GC ngay.

## 31. Non-static inner class thường giữ enclosing instance

Trong Java 17, một **non-static inner class** có một enclosing instance association. Nếu inner object cần dùng members của outer object, rõ ràng có đường trỏ từ inner instance tới outer.

```java
class Outer {
    String name;

    class Inner {
        String label() {
            return name;
        }
    }
}
```

Nếu một long-lived registry giữ Inner, nó có thể giữ Outer thông qua enclosing-instance reference/association. Điều này quan trọng khi Outer là controller/activity/window với graph lớn.

### Dùng static nested class khi không cần outer

`static class Nested` không tự yêu cầu một enclosing Outer instance. Nếu nested implementation chỉ cần dữ liệu riêng, một static nested class kèm constructor nhận đúng dependency có thể tránh reference giữ owner ngoài ý muốn.

**Không dùng nhận định quá tuyệt đối về hình dạng synthetic fields**: compiler/JVM có implementation freedom. Thiết kế source-level enclosing instance và sử dụng outer state mới là điều cần hiểu.

## 32. Runnable: inner object dùng state của outer

Lưu **`InnerOuterReferenceDemo.java`**:

```java
final class Outer {
    private final String label;

    Outer(String label) {
        this.label = label;
    }

    class Inner {
        String describe() {
            return "outer:" + Outer.this.label;
        }
    }

    Inner createInner() {
        return new Inner();
    }
}

public class InnerOuterReferenceDemo {
    public static void main(String[] args) {
        Outer outer = new Outer("parent");
        Outer.Inner inner = outer.createInner();

        outer = null;

        System.out.println(inner.describe());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 InnerOuterReferenceDemo.java
java InnerOuterReferenceDemo
```

Stdout:

```text
outer:parent
```

Dù local `outer` được gán null, inner instance vẫn truy cập state outer qua `Outer.this`. Đây là ví dụ rõ ràng về một đường reference **gián tiếp** vượt qua local.

## 33. Bound method reference cũng có thể giữ receiver

Java method reference có hai dạng ý nghĩa khác nhau:

```java
Runnable task = object::run;
```

Với **bound instance method reference**, `object` là receiver đã được đánh giá/bind lúc tạo method reference. Functional object có thể giữ receiver để dùng khi callback được gọi sau này.

Ngược lại:

```java
Function<Item, String> fn = Item::label;
```

đây là **unbound** instance method reference: receiver được truyền vào khi gọi `fn.apply(item)`. Việc tạo `fn` không tự capture một Item object cụ thể.

### Khi phân tích retention

Một long-lived scheduler/registry giữ `object::onEvent` có thể gián tiếp giữ cả graph của object receiver. Cần unregister/cancel đúng lifecycle.

## 34. Runnable: bound receiver vẫn được callback sử dụng

Lưu **`BoundMethodReferenceDemo.java`**:

```java
final class Printer {
    private final String value;

    Printer(String value) {
        this.value = value;
    }

    void print() {
        System.out.println(value);
    }
}

public class BoundMethodReferenceDemo {
    public static void main(String[] args) {
        Printer printer = new Printer("receiver");
        Runnable callback = printer::print;

        printer = null;
        callback.run();
    }
}
```

```bash
javac --release 17 -encoding UTF-8 BoundMethodReferenceDemo.java
java BoundMethodReferenceDemo
```

Stdout:

```text
receiver
```

`callback` vẫn có receiver gắn sẵn từ thời điểm tạo method reference. Không phải local `printer` còn giá trị khác null.

## 35. `ThreadLocal`: đường giữ gắn với thread sống lâu

`ThreadLocal<T>` giúp mỗi thread truy cập một giá trị “riêng” qua thread-local storage. Nhưng khi dùng **thread pool**, worker thread có thể tồn tại rất lâu sau một request.

Nếu code:

```java
CURRENT_USER.set(userContext);
```

rồi quên:

```java
CURRENT_USER.remove();
```

giá trị từ request cũ có thể còn gắn với thread đang được tái sử dụng. Vấn đề gồm:
- Rò rỉ context giữa hai requests.
- Giữ references tới large object graphs ngoài thời gian cần thiết.
- Hành vi khó đoán khi task tiếp theo chạy trên cùng worker thread.
- Class-loader retention trong môi trường nhiều lần redeploy, tùy framework.

**Thực hành:** khi context có lifetime theo một task/request, đặt cleanup trong `finally`, không chỉ trong nhánh thành công. Lưu ý `ThreadLocal` không tự truyền context qua những threads khác.

## 36. Runnable: thread pool tái sử dụng giá trị nếu chưa remove

Lưu **`ThreadLocalLifecycleDemo.java`**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ThreadLocalLifecycleDemo {
    private static final ThreadLocal<String> CONTEXT =
            new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<?> first = pool.submit(
                    () -> CONTEXT.set("request-A"));
            first.get();

            Future<String> second = pool.submit(CONTEXT::get);
            System.out.println(second.get());

            Future<?> third = pool.submit(CONTEXT::remove);
            third.get();

            Future<String> fourth = pool.submit(CONTEXT::get);
            System.out.println(fourth.get() == null);
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ThreadLocalLifecycleDemo.java
java ThreadLocalLifecycleDemo
```

Stdout:

```text
request-A
true
```

`newSingleThreadExecutor()` thực thi các tasks tuần tự trên cùng worker thread trong demo, nên task 2 đọc được context do task 1 lưu. `remove()` làm task 4 thấy null. Trong production, thường bọc `set/use/remove` trong **một task** với `try/finally` để tránh context cũ sống tới task sau.

## 37. Runnable: mẫu `try/finally` cho ThreadLocal

Lưu **`ThreadLocalCleanupDemo.java`**:

```java
public class ThreadLocalCleanupDemo {
    private static final ThreadLocal<String> USER =
            new ThreadLocal<>();

    static void runRequest(String name) {
        USER.set(name);
        try {
            System.out.println(USER.get());
        } finally {
            USER.remove();
        }
    }

    public static void main(String[] args) {
        runRequest("An");
        System.out.println(USER.get() == null);

        runRequest("Binh");
        System.out.println(USER.get() == null);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ThreadLocalCleanupDemo.java
java ThreadLocalCleanupDemo
```

Stdout:

```text
An
true
Binh
true
```

Đây là pattern cleanup **đáng tin cậy theo control flow**, không cần suy đoán khi nào GC thu gom objects.

## 38. Vì sao một chương trình Java vẫn có memory leak?

Trong môi trường GC, *leak* không chỉ là “quên `free(ptr)`”. Một đối tượng có thể **vẫn reachable** mặc dù phần mềm **không còn cần nó**.

Ví dụ:
- Static `Map` không có eviction.
- List listeners không unregister.
- Cache giữ cả key và value mãi.
- ThreadLocal không remove trong thread pool.
- Executor queue chứa nhiều pending tasks capture large graphs.
- Long-lived singleton giữ lastRequest/session.
- Non-static inner object sống lâu hơn outer intended lifecycle.
- Mảng vẫn giữ một phần tử đã “logically removed”.
- Một map value trỏ ngược về key, gây bẫy khi dùng WeakHashMap.

**GC không thể tự biết object nào hết ý nghĩa nghiệp vụ.** Nếu vẫn có đường strong reference và program có thể sử dụng nó, collector thường phải giữ.

### Phân biệt logical leak và GC bug

Trước khi kết luận JVM không dọn rác, hãy tìm strong reference paths. Nếu object đã unreachable nhưng heap còn chưa giảm tức thì, đó chưa phải leak: collector có thể chưa chạy, heap có thể giữ pages/reserved capacity cho future allocations.

## 39. Mô hình reachability và GC không hứa hẹn thời điểm thu gom

Một câu dễ sai:

> “Đặt biến bằng null sẽ lập tức giải phóng bộ nhớ.”

Không đúng.

Điều có thể nói:
- Gán `null` bỏ một reference **ở chỗ lưu trữ đó**.
- Nếu object không còn đường mạnh nào từ roots, nó có thể trở thành **eligible for garbage collection** trong ngữ cảnh thích hợp.
- JVM quyết định thời điểm phát hiện và thu hồi.
- Việc heap còn allocated/reserved không chứng minh object còn live.
- `System.gc()` là lời yêu cầu/hint; không bảo đảm GC hoàn tất, không bảo đảm object cụ thể được thu gom.
- Một chương trình không thể dự đoán chính xác thứ tự/ thời điểm finalization/reclamation.

### Điểm tinh tế: lexical scope ≠ liveness

Biến `obj` có thể còn trong source block nhưng không còn được sử dụng. JVM/JIT có thể coi nó không còn live ở một thời điểm trước cuối block, trong giới hạn specification.

Nếu ứng dụng **thực sự phải giữ object reachable đến một điểm xác định** (ví dụ wrapper của native handle vẫn phải sống trong lúc native code dùng resource), xem `Reference.reachabilityFence` thay vì dựa vào một biến “còn trong ngoặc nhọn”.

## 40. `WeakReference`: không phải một strong path

Package `java.lang.ref` cung cấp các loại tham chiếu với GC semantics đặc biệt.

`WeakReference<T>` không giữ referent sống bằng strong reachability giống local/field/list bình thường. Nếu không còn strong reachability theo rule của GC, weak reference có thể được **cleared** và `weak.get()` có thể trả null.

**Không dùng `WeakReference` làm cơ chế lưu trữ dữ liệu chắc chắn tồn tại.** Nó phù hợp cho một số caches/registries có thể tái tạo giá trị hoặc các kỹ thuật quan sát/cleanup đã được thiết kế cẩn thận.

### Điều có thể kiểm chứng chắc trong ví dụ

Khi một strong reference đang được dùng rõ ràng trong phép so sánh, weak reference mới tạo trỏ cùng object đó. Không được viết test kỳ vọng GC sẽ clear weak ref ngay sau `strong = null`.

## 41. Runnable: weak reference khi còn strong reference

Lưu **`WeakReferenceDemo.java`**:

```java
import java.lang.ref.Reference;
import java.lang.ref.WeakReference;

public class WeakReferenceDemo {
    public static void main(String[] args) {
        Object strong = new Object();
        WeakReference<Object> weak = new WeakReference<>(strong);

        System.out.println(weak.get() == strong);

        Reference.reachabilityFence(strong);
        strong = null;

        // Không assert weak.get() ở đây:
        // GC có thể đã chạy hoặc chưa chạy.
        System.out.println("no-gc-assumption");
    }
}
```

```bash
javac --release 17 -encoding UTF-8 WeakReferenceDemo.java
java WeakReferenceDemo
```

Stdout:

```text
true
no-gc-assumption
```

`WeakReference` không phải strong retention edge. `reachabilityFence` trong ví dụ làm mốc để giữ referent strongly reachable đến fence, nhưng không yêu cầu GC chạy sau đó.

## 42. Strong, soft, weak, phantom: bản đồ khái niệm

| Loại tham chiếu | Mục đích điển hình | Có giữ object như strong reference không? | Điều không nên giả định |
| --- | --- | --- | --- |
| Strong (tham chiếu Java thông thường) | Fields, locals, arrays, collections | Có khi còn path mạnh live | Scope = thời gian sống tuyệt đối |
| `SoftReference` | Một số memory-sensitive caches | Không giữ như strong; GC có chính sách soft reachability | “Giá trị luôn sống cho đến khi gần hết RAM” |
| `WeakReference` | Weak keys/listeners/caches có thể mất referent | Không | `get()` luôn non-null sau khi local null |
| `PhantomReference` | Theo dõi post-mortem cleanup phối hợp ReferenceQueue | Không cung cấp referent qua `get()` | Có thể dùng `get()` lấy object |
| `ReferenceQueue` | Nhận thông tin refs được enqueue | Không tự schedule cleanup code | Enqueue xảy ra tại thời điểm có thể dự đoán |

Đây là tóm lược định hướng. `SoftReference`, `WeakReference`, `PhantomReference` có những bước GC/queue semantics riêng; hãy đọc Java SE 17 `java.lang.ref` khi thiết kế cache/cleanup chuyên sâu.

**Dù sử dụng weak/soft refs, vẫn cần quản lý lifecycle dữ liệu, bounds và errors**. Không nên dùng reference tricks thay cho một chính sách eviction rõ ràng khi cache có giới hạn.

## 43. Runnable: `PhantomReference.get()` không trả referent

Lưu **`PhantomReferenceDemo.java`**:

```java
import java.lang.ref.PhantomReference;
import java.lang.ref.Reference;
import java.lang.ref.ReferenceQueue;

public class PhantomReferenceDemo {
    public static void main(String[] args) {
        Object resource = new Object();
        ReferenceQueue<Object> queue = new ReferenceQueue<>();

        PhantomReference<Object> phantom =
                new PhantomReference<>(resource, queue);

        System.out.println(phantom.get() == null);

        Reference.reachabilityFence(resource);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 PhantomReferenceDemo.java
java PhantomReferenceDemo
```

Stdout:

```text
true
```

`PhantomReference.get()` luôn trả null theo API contract. Ví dụ **không dự đoán** thời gian queue được enqueue hoặc collector chạy.

## 44. `WeakHashMap`: weak keys, nhưng không tự chống mọi leak

`WeakHashMap<K,V>` dùng weak references cho keys, nên entries có thể bị loại bỏ khi keys không còn strong-reachable.

**Bẫy quan trọng:** map vẫn giữ strong references đến **values**. Nếu value trực tiếp/gián tiếp trỏ ngược về key, có thể hình thành path:

```text
root → WeakHashMap → strongly held Value → Key
```

Khi đó key vẫn reachable qua value, không được giải phóng chỉ vì map dùng weak keys.

Một key cũng có thể được giữ bởi một collection khác; weak map không can thiệp vào strong paths ấy.

### Không dùng WeakHashMap như database

Entries có thể biến mất dựa trên GC behavior, không phải nghiệp vụ thời gian hết hạn cố định. Nếu cần timeout/size bounds/refresh policy, hãy dùng cache implementation có eviction rõ và test được.

## 45. Runnable: WeakHashMap với key còn mạnh

Lưu **`WeakHashMapDemo.java`**:

```java
import java.lang.ref.Reference;
import java.util.WeakHashMap;

public class WeakHashMapDemo {
    public static void main(String[] args) {
        WeakHashMap<Object, String> map = new WeakHashMap<>();

        Object key = new Object();
        map.put(key, "value");

        System.out.println(map.get(key));
        System.out.println(map.containsKey(key));

        Reference.reachabilityFence(key);

        // Không dự đoán điều gì sau khi mất strong key:
        // entry removal tùy GC và các refs khác.
    }
}
```

```bash
javac --release 17 -encoding UTF-8 WeakHashMapDemo.java
java WeakHashMapDemo
```

Stdout:

```text
value
true
```

Mọi assertion đều diễn ra khi `key` vẫn có đường strong reference rõ. Không viết ví dụ kiểu “gọi `System.gc()` rồi chắc map trống” vì không có bảo đảm như vậy.

## 46. `Reference.reachabilityFence` giải quyết tình huống nào?

Thông thường, bạn **không cần** tự thêm fences vào ứng dụng. Nhưng có tình huống resource wrapper chứa native handle:

```text
Java wrapper ──native handle──▶ OS/native resource
```

Nếu Java compiler/JIT xác định wrapper không còn dùng trước khi native operation thực sự kết thúc, một cleanup mechanism dựa vào reachability có thể gặp vấn đề. `Reference.reachabilityFence(wrapper)` đảm bảo strong reachability của referent tới điểm gọi fence theo API contract.

Ví dụ dạng schematic:

```java
nativeUse(handle);
Reference.reachabilityFence(wrapper);
```

Đây là **snippet** phụ thuộc native API bên ngoài. Không tự tưởng tượng `reachabilityFence` giữ object vĩnh viễn; nó chỉ thiết lập mốc reachability cho một code path cụ thể.

### Không biến fence thành GC trigger

`Reference.reachabilityFence` không gọi GC, không close resource, không bảo đảm object đã unreachable sau fence. Nó có ý nghĩa giới hạn **khoảng mà object phải được coi là strongly reachable**.

## 47. GC giải phóng memory khác với đóng tài nguyên

Một đối tượng Java có thể bao bọc:
- File descriptor;
- Socket;
- JDBC connection;
- Native buffer;
- Thread;
- Lock/transaction;
- Streams.

Không nên chờ GC để giải phóng những tài nguyên ấy đúng lúc.

Java 17 dùng `AutoCloseable`/`Closeable` và **try-with-resources** để có cleanup theo control flow:

```java
try (Resource resource = new Resource()) {
    resource.use();
}
```

`close()` được gọi khi rời try block theo quy tắc, kể cả khi có exception (với các điều kiện xử lý thích hợp). Điều này **không tương đương** với GC reclaim object.

**`finalize()`** đã bị deprecated và đặc biệt không đáng tin cho resource management; không dùng finalizer làm cơ chế đóng file/socket. `Cleaner` chỉ thích hợp như safety net trong một số thiết kế, không thay deterministic close.

## 48. Runnable: try-with-resources đóng đúng lúc

Lưu **`ResourceLifecycleDemo.java`**:

```java
final class DemoResource implements AutoCloseable {
    private boolean closed;

    void use() {
        if (closed) {
            throw new IllegalStateException("closed");
        }
        System.out.println("using");
    }

    @Override
    public void close() {
        closed = true;
        System.out.println("closed");
    }
}

public class ResourceLifecycleDemo {
    public static void main(String[] args) {
        try (DemoResource resource = new DemoResource()) {
            resource.use();
        }

        System.out.println("after-try");
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ResourceLifecycleDemo.java
java ResourceLifecycleDemo
```

Stdout:

```text
using
closed
after-try
```

`close` xảy ra theo cấu trúc chương trình, không cần gọi `System.gc()`. Object `DemoResource` vẫn có thể còn trong bộ nhớ tạm thời sau khi đóng; **resource state** và **object memory lifetime** là hai chuyện khác nhau.

## 49. `final` reference field không ngăn object bị mutate

```java
final class Holder {
    final StringBuilder text = new StringBuilder();
}
```

`final` ngăn gán lại `text` sau khi được khởi tạo đúng, nhưng:

```java
holder.text.append("new content");
```

vẫn được phép. Object có thể thay đổi nội dung.

Về reachability, `final` không tự biến field thành GC root vĩnh viễn. Khi owner Holder reachable, field reference góp phần giữ referent; khi owner không còn reachable, final không ngăn graph được thu gom.

### Runnable

Lưu **`FinalReferenceDemo.java`**:

```java
final class Holder {
    final StringBuilder buffer = new StringBuilder("a");
}

public class FinalReferenceDemo {
    public static void main(String[] args) {
        Holder owner = new Holder();

        owner.buffer.append("b");

        System.out.println(owner.buffer);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 FinalReferenceDemo.java
java FinalReferenceDemo
```

Stdout:

```text
ab
```

“Reference field final” khác “object immutable” và khác “object được pin mãi trong heap”.

## 50. Weak vs strong path: khi nào GC được quyền clear weak ref?

Về nguyên tắc, collector có thể clear weak references tới object khi object không còn strongly/softly reachable theo các quy tắc soft/weak reachability tương ứng, tại processing phase phù hợp.

Điểm người dùng API cần nhớ:
- `WeakReference.get()` có thể trả null bất kỳ lúc nào nếu không còn bảo đảm strong reachability; kết quả không giữ object sống suốt một thao tác khác nếu không lưu giá trị trả về vào strong local thích hợp.
- Nếu `T value = weak.get()` trả non-null, local `value` có thể cung cấp strong reference cho phần sử dụng đang diễn ra.
- Không viết `if (weak.get() != null) weak.get().call();` vì giữa hai lần `get()` có thể không còn cùng bảo đảm; lưu một lần.
- Không dự đoán enqueue timing của `ReferenceQueue`.
- Không dùng weak refs khi ứng dụng **bắt buộc** giữ dữ liệu đến khi sự kiện nghiệp vụ kết thúc.

### Mẫu kiểm tra một lần

```java
Object value = weak.get();
if (value != null) {
    use(value);
}
```

Đây là **snippet**: `weak` và `use` phải được khai báo trong ngữ cảnh tương ứng. Một local strong reference `value` giúp giữ referent khả dụng trong quá trình sử dụng, nhưng nếu logic native đặc biệt cần mốc đến sau last apparent use thì `reachabilityFence` có thể thích hợp.

## 51. Không dựa vào `System.gc()` để kiểm thử object lifetime

Code kiểm thử dễ sai:

```java
// Pseudocode anti-pattern:
object = null;
System.gc();
assertNull(weak.get());
```

Không đáng tin vì:
- `System.gc()` không phải lời hứa collector hoàn tất.
- JDK flags/GC implementation có thể bỏ qua explicit GC request.
- Runtime có thể chưa cần reclaim memory.
- Một reference khác có thể vẫn giữ object.
- JVM optimizations/liveness khiến hành vi không nhất quán giữa builds.

**Test nên kiểm tra logic do bạn kiểm soát**:
- Sau unsubscribe, registry size giảm.
- Sau `remove()`, ThreadLocal trong thread ấy không còn value.
- Sau close, trạng thái resource đổi và use bị từ chối.
- Sau cache eviction, map entry không còn.
- Sau assign, các aliases trỏ đúng objects.

Nếu làm memory-retention tests chuyên sâu, dùng heap dumps, GC diagnostics và profiling với các điều kiện đủ chặt; không biến một kết quả GC timing ngẫu nhiên thành unit-test contract.

## 52. GC “eligible” không có nghĩa JVM phải giải phóng ngay

Một đối tượng có thể:
1. Được cấp phát hoặc được tối ưu hóa theo runtime;
2. Được dùng qua local/field/path;
3. Trở nên không còn strongly reachable ở một thời điểm;
4. Được collector phát hiện và xử lý theo chính sách;
5. Memory có thể được reclaim hoặc còn được quản lý cho các allocations sau.

Các bước 3–5 không đồng thời, và không phải tất cả đều quan sát được chính xác từ Java source.

`Runtime.totalMemory()`/`freeMemory()` hay OS process RSS cũng không bằng “bao nhiêu objects không còn reachable”. JVM có thể giữ heap committed memory sau collection để tái sử dụng.

### Chú ý finalization và resurrection

Java 17 vẫn có legacy finalization semantics trong một số hoàn cảnh, với khả năng object resurrection phức tạp. Đây không phải kỹ thuật quản lý vòng đời nên dùng. Tránh `finalize()`; dùng `AutoCloseable`/`Cleaner` phù hợp và không dựa vào finalize timing để chứng minh GC.

## 53. Những cấu trúc thường giữ objects không mong muốn

### 53.1. Static caches

`Map<Key,Value>` sống lâu mà không có giới hạn size/TTL làm giữ keys/values và toàn graph phía sau.

**Giải pháp:** size bounds, expiry/eviction, ownership rõ, metrics.

### 53.2. Event listeners

Event bus sống lâu, listener capture controller. Controller đã đóng UI nhưng callback chưa unsubscribe.

**Giải pháp:** registration token có lifecycle, unregister trong cleanup.

### 53.3. ThreadLocals

Thread trong pool sống lâu qua nhiều tasks, context không remove.

**Giải pháp:** try/finally remove; tránh lưu heavyweight object ngoài nhu cầu.

### 53.4. Pending tasks

Executor queue giữ Runnable/Callable đang chờ; callback capture request payload.

**Giải pháp:** backpressure, bounded queues, cancellation, shutdown và tránh capture cả graph.

### 53.5. Inner classes, lambdas và method references

Một object callback có thể giữ enclosing/receiver/captured object.

**Giải pháp:** hiểu capture, dùng static nested classes hoặc truyền minimal state, unregister đúng lúc.

### 53.6. Historical snapshots

Một danh sách snapshots/past states không có retention policy làm object graphs vẫn reachable.

**Giải pháp:** giới hạn số snapshots, streaming, persistence + paging, cache eviction.

### 53.7. Maps giữ value trỏ ngược tới key

Đặc biệt khi dùng WeakHashMap, value → key strong edge có thể vô hiệu hóa ý định weak-key behavior.

**Giải pháp:** tách references/metadata, thiết kế weak-value hoặc explicit eviction phù hợp.

## 54. Runnable: cache có giới hạn theo logic ứng dụng

Lưu **`BoundedCacheDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.Map;

public class BoundedCacheDemo {
    public static void main(String[] args) {
        Map<Integer, String> cache =
                new LinkedHashMap<>(16, 0.75f, true) {
                    @Override
                    protected boolean removeEldestEntry(
                            Map.Entry<Integer, String> eldest) {
                        return size() > 2;
                    }
                };

        cache.put(1, "A");
        cache.put(2, "B");
        cache.put(3, "C");

        System.out.println(cache.containsKey(1));
        System.out.println(cache.containsKey(2));
        System.out.println(cache.containsKey(3));
        System.out.println(cache.size());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 BoundedCacheDemo.java
java BoundedCacheDemo
```

Stdout:

```text
false
true
true
2
```

Chính sách eviction làm cache không giữ entry 1 sau khi vượt giới hạn size 2. Mục tiêu là **giảm paths đến dữ liệu không còn cần**, không phải yêu cầu GC lập tức thu hồi String hay entry nodes.

## 55. Biến cục bộ kiểu primitive không phải reference path tới object

```java
int count = 7;
double ratio = 0.5;
boolean active = true;
```

Các local primitives này chứa primitive values, không chứa object references tới `Integer`/`Double`/`Boolean` theo cách parameterized references được lưu.

Ngược lại:

```java
Integer count = Integer.valueOf(7);
```

là reference đến một wrapper object (hoặc cached wrapper theo API/implementation), và về nguyên tắc nó tham gia reference reachability như các object references khác.

### Boxing có ảnh hưởng gì?

Autoboxing có thể tạo hoặc tái sử dụng wrapper objects theo quy tắc runtime. Không cần dùng object wrapper chỉ để diễn đạt một giá trị nguyên thủy nếu primitive phù hợp, đặc biệt trong loops hoặc arrays lớn.

Không phán đoán reference identity của boxed values tùy ý bằng `==`. Với wrapper, dùng `equals` khi muốn so nội dung.

## 56. Runnable: primitive khác reference alias

Lưu **`PrimitiveVsReferenceDemo.java`**:

```java
public class PrimitiveVsReferenceDemo {
    public static void main(String[] args) {
        int a = 5;
        int b = a;

        a = 9;

        StringBuilder x = new StringBuilder("X");
        StringBuilder y = x;

        x.append("Y");

        System.out.println(b);
        System.out.println(y);
        System.out.println(x == y);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 PrimitiveVsReferenceDemo.java
java PrimitiveVsReferenceDemo
```

Stdout:

```text
5
XY
true
```

Primitive copy tạo giá trị độc lập; reference copy tạo alias đến cùng object.

## 57. Nhiều đối tượng bằng nhau không nhất thiết là cùng object

Java `equals` có thể định nghĩa value equality. Một object reference graph vẫn quan tâm **chính xác instance nào** được trỏ tới.

```java
String one = new String("A");
String two = new String("A");
```

`one.equals(two)` true; `one == two` false vì hai lệnh `new` tạo hai String objects khác identity.

Trong memory analysis:
- Collection giữ `one` không đồng nghĩa collection giữ `two`.
- Hai objects bằng nhau vẫn có reference graph và lifetime riêng.
- Record `equals` cũng không tự đồng nhất hai instances thành một heap object.

### Runnable

Lưu **`IdentityAndEqualityDemo.java`**:

```java
public class IdentityAndEqualityDemo {
    public static void main(String[] args) {
        String first = new String("same");
        String second = new String("same");

        System.out.println(first.equals(second));
        System.out.println(first == second);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 IdentityAndEqualityDemo.java
java IdentityAndEqualityDemo
```

Stdout:

```text
true
false
```

GC không dùng “hai objects bằng nhau theo `equals`” làm lý do để tự gộp chúng thành một object theo logic source.

## 58. Class loaders và static field lifetime

Trong ứng dụng bình thường, static fields của classes ứng dụng có thể sống trong phần lớn đời process. Trong servers, plugins, testing frameworks hoặc containers, có thể tồn tại nhiều class loaders.

Nếu một long-lived object ở class loader A giữ object/class loader B, một graph lớn thuộc module/redeployment cũ có thể không được unload.

Ví dụ loại path đáng quan tâm:

```text
application-wide root
  └── static registry
        └── plugin callback
              └── plugin instance
                    └── plugin Class
                          └── plugin ClassLoader
```

**Không đơn giản hóa rằng “static field là một global root mãi mãi”** hoặc “class unload ngay khi ta bỏ class loader variable”. Hãy xác định reachability thực tế và behavior của JVM/container.

### Thực hành khi develop plugins

- Gỡ listeners/registrations khi unload plugin.
- Shutdown executors/threads do plugin tạo.
- Remove ThreadLocal values khỏi threads sống lâu.
- Tránh static caches ở parent loader giữ objects của child loader.
- Dùng heap analyzer để lần theo **GC root paths**.

## 59. Công cụ chẩn đoán khi nghi memory retention

Các dấu hiệu nên theo dõi:
- Live heap sau nhiều lần collections tiếp tục tăng khi workload ổn định.
- Object counts của một số classes tăng mãi theo số requests.
- Retained size của một cache/registry vượt budget.
- Hàng đợi callbacks hoặc pending tasks không giảm.
- Old plugin class loaders còn tồn tại sau nhiều redeploy cycles.

Công cụ Java 17 và hệ sinh thái:
- **JDK Flight Recorder (JFR)** và Java Mission Control cho profiling/analysis.
- **`jcmd`** cho một số diagnostics, class histograms và heap dumps khi môi trường cho phép.
- **Heap dump** + Eclipse Memory Analyzer Tool (MAT) để xem **dominator tree, retained size, paths to GC roots**.
- **GC logs** qua `-Xlog:gc*` để xem hoạt động collector, không suy trực tiếp object nào đang bị một listener giữ.
- **Application metrics** cho size/age của caches, listener counts, ThreadLocal lifecycle.

Các công cụ có phiên bản/đối số/quyền truy cập riêng. Với production, phải cân nhắc chi phí/gián đoạn và privacy của heap dumps chứa dữ liệu nhạy cảm.

## 60. Chiến lược điều tra leak theo reference paths

1. **Định nghĩa hành vi mong muốn:** đối tượng A lẽ ra hết tác dụng ở sự kiện nào?
2. **Tái hiện ổn định:** tạo/dọn các sessions hoặc screens lặp lại, quan sát memory sau nhiều chu kỳ.
3. **Thu thập bằng chứng:** heap dump/JFR/metrics trong môi trường phù hợp.
4. **Tìm object type nghi ngờ:** số lượng, retained size, tuổi thọ.
5. **Xem paths to GC roots:** static map? singleton? thread? listener? lambda capture? class loader?
6. **Đọc reference graph thực tế:** có phải strong path không, có weak/soft/phantom edge không?
7. **Xác định ownership:** ai đăng ký, ai gỡ, ai được phép clear?
8. **Sửa đường giữ sai:** remove/clear/close/cancel bounded cache, không dựa vào GC hint.
9. **Kiểm thử hành vi nghiệp vụ:** object không còn ở registry, context xóa đúng lúc, resource đóng.
10. **Đo lại:** so số entries/retained size/memory trend trước và sau trên workload đại diện.

Câu hỏi mạnh nhất khi debug: **“Object này còn sống vì đường tham chiếu mạnh nào, từ root nào?”**

## 61. Những điều không nên “tối ưu” bằng cách đặt `null` khắp nơi

Trong code thông thường:

```java
process(item);
item = null;
```

việc gán null sau last use thường **không cần thiết**, vì JIT/GC đã có phân tích liveness. Nó còn dễ làm code khó đọc, che khuất bug logic hoặc tạo NPE nếu người viết tiếp tục sử dụng biến.

Các trường hợp thật sự có thể đáng đổi reference:
- **Long-lived fields** sau khi một phase nghiệp vụ kết thúc.
- **Large arrays** có slots không còn dùng nhưng mảng vẫn sống.
- **Caches/collections** cần remove old entries.
- **Object pools** giữ references và cần clear slots đúng cách.
- **Listeners/registrations** phải unregister.

Tập trung vào **đường reference có owner sống lâu**, không áp đặt một thói quen đặt null cho mọi locals.

## 62. Hiểu vòng đời của một đối tượng qua ví dụ tổng hợp

Xét:

```java
final class Customer {
    final String name;

    Customer(String name) {
        this.name = name;
    }
}
```

Các bước:

1. `Customer c = new Customer("An");` — tạo một Customer và local c trỏ tới object.
2. `List<Customer> list = new ArrayList<>();` — tạo list object khác.
3. `list.add(c);` — list giữ reference tới Customer.
4. `Cache.saved = list;` — static field trỏ tới list, tạo path từ class state qua list tới Customer.
5. `c = null;` — local c bỏ reference; Customer vẫn có đường qua Cache.saved.
6. `list = null;` — local list bỏ reference; static Cache.saved vẫn giữ ArrayList.
7. `Cache.saved.clear();` — list bỏ reference tới Customer.
8. `Cache.saved = null;` — static cache bỏ reference tới list.
9. Nếu không có roots/paths khác, những objects ấy có thể trở nên unreachable.
10. JVM **không bắt buộc** thu hồi chúng ngay ở bước 9.

Điều cần học không phải “bước 8 gọi GC”, mà là **mỗi thao tác làm biến đổi graph ra sao**.

## 63. Runnable: đối chiếu trạng thái của graph tổng hợp

Lưu **`ReachabilityPathsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Cache {
    static List<StringBuilder> saved;
}

public class ReachabilityPathsDemo {
    public static void main(String[] args) {
        StringBuilder item = new StringBuilder("important");
        List<StringBuilder> list = new ArrayList<>();

        list.add(item);
        Cache.saved = list;

        item = null;
        list = null;

        System.out.println(Cache.saved.get(0));
        System.out.println(Cache.saved.size());

        Cache.saved.clear();
        System.out.println(Cache.saved.isEmpty());

        Cache.saved = null;
        System.out.println(Cache.saved == null);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ReachabilityPathsDemo.java
java ReachabilityPathsDemo
```

Stdout:

```text
important
1
true
true
```

Không có bước nào in “đã GC thành công”, bởi đó không phải behavior Java source có thể cam kết.

## 64. Checklist phân tích một object có được giữ không

- [ ] Đã phân biệt biến tham chiếu với object chưa?
- [ ] Biết object đang bị giữ là **instance nào**, không chỉ class name?
- [ ] Có những local variables hoặc parameters nào còn được dùng?
- [ ] Có instance fields nào từ owner reachable trỏ object?
- [ ] Owner của field có đường từ GC root nào?
- [ ] Có static field/cache nào giữ owner hoặc chính object?
- [ ] Object có trong array slot hoặc collection entry không?
- [ ] Có nhiều incoming references/aliases không?
- [ ] Có return value hoặc parameter escape giữ object lâu hơn method không?
- [ ] Có lambda/anonymous class/bound method reference capture object không?
- [ ] Có non-static inner object giữ enclosing instance không?
- [ ] Có listener/subscription chưa unregister không?
- [ ] Có ThreadLocal sống qua thread pool tasks không?
- [ ] Có executor pending tasks giữ captured payload không?
- [ ] Có cycle và có root path thực sự tới cycle không?
- [ ] Nếu cycle không có path từ roots, không coi chỉ riêng cycle là leak?
- [ ] Phân biệt static field với instance field và local?
- [ ] Phân biệt `final` field với immutable referent?
- [ ] Phân biệt `equals` với identity của reference?
- [ ] Nếu WeakReference được dùng, code có xử lý null từ `get()`?
- [ ] Có tránh khẳng định GC xảy ra ngay sau `System.gc()`?
- [ ] Có tách lifecycle tài nguyên `close()` khỏi GC memory reclamation?
- [ ] Có profile/heap dump nếu cần xác nhận đường giữ ngoài ý muốn?
- [ ] Cleanup có owner, sự kiện và đường test xác định?
- [ ] Có quan sát regression sau fix, thay vì chỉ đặt null cho biến local?

## 65. Bài tập 1 — Hai aliases

```java
Object first = new Object();
Object second = first;
first = null;
```

Hỏi: object còn đường reference từ `second` không?

**Đáp án:** Có. Gán null cho first không làm second trở thành null và không xóa object.

## 66. Bài tập 2 — Hai objects khác nhau

```java
Object a = new Object();
Object b = new Object();
a = b;
```

Hỏi: số objects được gọi `new Object()` trong source là bao nhiêu và object ban đầu của a còn đường từ a không?

**Đáp án:** Có hai expression `new Object()`; a đã chuyển sang trỏ object của b. Object cũ không còn đường từ a, nhưng còn reachable hay không cần xét paths khác và optimizations, không suy từ một câu lệnh.

## 67. Bài tập 3 — Object trả về

Method tạo object trong local rồi `return` reference. Caller lưu reference.

**Đáp án:** Object có thể sống qua method return vì caller giữ reference. Không tự deep copy.

## 68. Bài tập 4 — Local scope

Object được tạo trong block, reference được gán vào local bên ngoài block.

**Đáp án:** Scope kết thúc của local trong block không làm object unreachable nếu local bên ngoài còn giữ reference.

## 69. Bài tập 5 — Field chain

`root.user.cart.items.get(0)`. Đường nào có thể giữ item?

**Đáp án:** Một path qua root → user → cart → items/list → element. Phải xét root và aliases khác nếu muốn kết luận.

## 70. Bài tập 6 — Instance field có phải root?

Một object A có field tham chiếu B nhưng A không còn reachable.

**Đáp án:** Field không tự là GC root. Nếu không có path khác tới A/B, cả graph có thể unreachable.

## 71. Bài tập 7 — Static cache

Static list chứa session; local tạo session đã ra khỏi method.

**Đáp án:** Session có thể vẫn reachable qua static list nếu class/static state vẫn reachable. Cần eviction/removal phù hợp.

## 72. Bài tập 8 — Mảng

`array[0] = customer; customer = null;` với array còn reachable.

**Đáp án:** Array slot vẫn giữ customer object.

## 73. Bài tập 9 — Collection remove

Object nằm trong hai lists; chỉ list thứ nhất clear.

**Đáp án:** List thứ hai vẫn có reference path. Cần xét cả hai lists và aliases khác.

## 74. Bài tập 10 — Chu kỳ A↔B

A và B tham chiếu lẫn nhau, nhưng không có đường từ live GC roots tới hai objects.

**Đáp án:** Chu trình tự nó không đủ giữ objects strong-reachable; tracing GC có thể reclaim cycle.

## 75. Bài tập 11 — Pass-by-value

Method nhận `StringBuilder p` rồi `p = new StringBuilder("X");`.

**Đáp án:** Caller variable không đổi vì parameter được truyền theo giá trị reference. Nếu method mutate `p.append` trên object cũ thì state thay đổi.

## 76. Bài tập 12 — Final field

`final List<String> values = new ArrayList<>();`. Có gọi `values.add(...)` được không?

**Đáp án:** Có nếu object cho phép. Final ngăn gán lại field/local, không biến ArrayList immutable.

## 77. Bài tập 13 — Lambda capture

Một long-lived registry giữ lambda đã capture controller.

**Đáp án:** Có thể giữ controller qua callback path. Hủy đăng ký theo lifecycle; không chỉ gọi GC.

## 78. Bài tập 14 — Inner class

Một instance của non-static inner class còn được giữ; method inner cần dùng Outer.this.field.

**Đáp án:** Inner có enclosing-instance association để truy cập Outer; outer graph có thể được giữ theo path ấy.

## 79. Bài tập 15 — Bound reference

`Runnable r = printer::print; printer = null; r.run();`.

**Đáp án:** Bound method reference vẫn có thể gọi receiver được bind; việc gán null cho local không xóa receiver của callback.

## 80. Bài tập 16 — ThreadLocal

Thread pool worker xử lý request A và lưu context, quên remove. Worker xử lý request B.

**Đáp án:** Context A có thể bị nhìn thấy/giữ ở B. Dùng try/finally remove theo task/request.

## 81. Bài tập 17 — `System.gc()`

Sau `obj=null; System.gc();`, có thể assert weak reference đã null không?

**Đáp án:** Không. Không có bảo đảm thời điểm/việc thực hiện GC; còn có thể có paths khác.

## 82. Bài tập 18 — Weak reference

Một WeakReference trỏ object, không còn strong paths.

**Đáp án:** Collector có thể clear weak reference theo GC semantics. Đừng yêu cầu `get()` chắc chắn non-null hoặc chắc chắn null ngay lập tức.

## 83. Bài tập 19 — WeakHashMap

Map weak key K giữ value V; V có field trỏ ngược K.

**Đáp án:** Value có strong edge tới K, có thể giữ key reachable. Weak keys không tự giải quyết vòng strong path qua value.

## 84. Bài tập 20 — Phantom get

`PhantomReference.get()` trả referent có thể dùng được không?

**Đáp án:** Không; `get()` luôn trả null. ReferenceQueue thường được dùng cho cleanup coordination không dự đoán thời điểm.

## 85. Bài tập 21 — Close và GC

Một file stream được close khi rời try-with-resources. Object stream đã bị GC ngay không?

**Đáp án:** Không nhất thiết. Resource close là deterministic cleanup; memory reclaim là quá trình khác.

## 86. Bài tập 22 — Resource finalization

Dùng `finalize()` để close socket có nên không?

**Đáp án:** Không. Finalization deprecated/unreliable và timing không xác định. Dùng try-with-resources/close/finally.

## 87. Bài tập 23 — Heap usage

Sau cache.clear(), process RSS không giảm. Có phải clear() thất bại không?

**Đáp án:** Chưa thể kết luận. JVM có thể chưa GC, giữ heap committed để tái sử dụng, hoặc còn đường giữ khác. Cần đo live objects/heap graph đúng.

## 88. Bài tập 24 — Primitive

`int x = 42;` có nghĩa một `Integer` object luôn được tạo không?

**Đáp án:** Không. Local int chứa primitive value. Boxing/reference wrappers là tình huống khác.

## 89. Bài tập 25 — Equality vs identity

Hai `new String("A")` objects `equals` nhau nhưng `==` false. GC có coi chúng là một object vì equals true không?

**Đáp án:** Không. Reachability và identity xét actual reference graph, không dùng `equals` để coi hai instances là cùng object.

## 90. Bài tập 26 — Multiple roots

Hai registries đều giữ cùng listener; bạn remove khỏi một registry.

**Đáp án:** Listener có thể vẫn reachable qua registry còn lại. Phải tìm mọi root paths phù hợp.

## 91. Bài tập 27 — Static lifecycle

Có thể nói “mọi static fields luôn giữ objects đến lúc JVM exit” không?

**Đáp án:** Không tuyệt đối. Class-loader reachability/unloading và field assignments ảnh hưởng lifetime; phải xét runtime.

## 92. Bài tập 28 — Liveness và lexical scope

Một local còn trong source block nhưng đã qua lần sử dụng cuối. Object nhất thiết được giữ cho tới dấu ngoặc đóng block?

**Đáp án:** Không. JIT/GC có thể xác định liveness sớm hơn theo semantics; scope của tên không đồng nhất reachability lifetime.

## 93. Bài tập 29 — Source leak

Một static `List<Screen>` được append mỗi lần mở màn hình, không clear dù màn hình đã đóng.

**Đáp án:** Đây là retained-object memory leak ở cấp ứng dụng: đường static list còn giữ screens. Sửa owner cleanup/bounds và test entry removal.

## 94. Bài tập 30 — Debug retention

Object Report vẫn xuất hiện trong heap dump sau khi request hoàn thành. Bạn cần tìm bằng chứng gì?

**Đáp án:** Paths to GC roots, dominators/retained size, listeners, caches, ThreadLocal, pending tasks, object fields; xác định strong path có chủ đích hay leak. Chỉ có “object xuất hiện trong dump” chưa đủ kết luận.

## 95. Đúng/Sai tổng hợp

1. Hai variables cùng trỏ object nghĩa là hai objects.
2. Gán null cho một variable có thể xóa cạnh reference từ variable đó.
3. Instance field tự là GC root bất kể owner có reachable không.
4. Local scope hết không bảo đảm GC ngay.
5. Static caches có thể giữ object graphs qua nhiều method calls.
6. `List.clear()` tự gọi destructor trên tất cả elements.
7. Strong reference cycle không tự giữ objects nếu không có path từ roots.
8. Lambda/bound method reference có thể capture/giữ objects.
9. ThreadLocal values có thể còn qua nhiều tasks của cùng pooled worker.
10. `WeakReference.get()` được bảo đảm trả null ngay sau `System.gc()`.
11. `final` reference biến StringBuilder thành immutable.
12. `AutoCloseable.close()` và GC reclaim object là một sự kiện.
13. `Reference.reachabilityFence` gọi GC.
14. Những collections còn reachable có thể giữ element references.
15. Xóa một trong nhiều independent strong paths luôn đủ làm object unreachable.

**Đáp án:** 1 sai; 2 đúng; 3 sai; 4 đúng; 5 đúng; 6 sai; 7 đúng; 8 đúng; 9 đúng; 10 sai; 11 sai; 12 sai; 13 sai; 14 đúng; 15 sai.

## 96. Bảng lỗi phổ biến

| Nhầm lẫn | Thực tế | Hướng xử lý |
| --- | --- | --- |
| “Local out of scope = object bị xóa ngay” | Scope ≠ GC timing; references có thể escape | Tìm paths còn tồn tại |
| “`a=null` xóa object” | Chỉ gán lại một reference variable | Kiểm tra aliases/fields |
| “Method truyền object theo tham chiếu” | Java luôn pass-by-value, kể cả reference values | Phân biệt mutate object và reassign parameter |
| “Instance field là GC root” | Owner phải reachable qua root/path | Lần đường từ roots |
| “Static luôn tồn tại mãi mãi” | Class-loader lifetime và field updates có vai trò | Xem đúng root paths |
| “`final` làm referent immutable” | Final chỉ ngăn gán lại variable/field | Dùng immutable values/defensive copy |
| “List.remove giải phóng object ngay” | Remove một đường reference, không lịch GC | Tìm aliases và đo |
| “Reference cycle tự làm memory leak” | Tracing GC xử lý unreachable cycles | Tìm root path vào cycle |
| “WeakReference giữ cache item chắc chắn” | Referent có thể bị cleared | Xử lý null/rebuild |
| “System.gc luôn dọn ngay” | Chỉ request/hint, collector có quyền quyết định | Không test GC timing |
| “WeakHashMap không bao giờ leak” | Values có thể trỏ ngược keys; refs khác giữ | Xem value→key paths |
| “ThreadLocal tự reset mỗi task” | Pooled thread giữ mapping qua tasks nếu không remove | try/finally remove |
| “Listener không còn UI thì tự biến mất” | Event bus có thể giữ callback/capture | unsubscribe/dispose |
| “Close object bằng GC” | Tài nguyên phải close theo control flow | try-with-resources |
| “Object equals true = cùng identity” | Equality khác object reference | Dùng == khi phân tích alias |
| “RSS không giảm = GC lỗi” | Heap committed và live objects là metric khác | Heap dumps/JFR/path analysis |

## 97. Tóm tắt cuối bài

**Biến cục bộ, instance fields, static fields, array slots, collection entries, callbacks và các cơ chế như ThreadLocal** đều có thể tạo những **đường tham chiếu** đến object. Một object có thể tiếp tục được sử dụng ngay cả khi local tạo ra nó đã kết thúc, nếu reference đã được lưu qua field, return value, list hoặc lambda capture.

Trong mô hình GC Java:
- Đối tượng còn đường mạnh từ những roots đang sống thì vẫn **reachable**.
- Một field chỉ là cạnh; bản thân nó không tự là GC root nếu owner không reachable.
- Đặt biến bằng null, xóa entry khỏi collection hay bỏ một path chỉ thay graph. Phải xem **mọi paths còn lại**.
- Một graph cyclic nhưng không còn root path có thể được thu gom; ngược lại, một static registry giữ object không còn cần là nguồn memory leak thực tế.
- **Thời điểm eligible, GC thực hiện và bộ nhớ trả về hệ thống khác nhau**; không viết unit tests phụ thuộc `System.gc()`.
- Weak/soft/phantom references có cơ chế riêng, không thay strong ownership hay deterministic lifecycle.
- **Resource cleanup `close()`** không được giao cho GC; dùng try-with-resources và quản lý subscriptions/ThreadLocals/cache entries đúng lúc.

Câu hỏi cần đặt khi phân tích vòng đời đối tượng không chỉ là **“Biến tạo object đã hết scope chưa?”** mà là:

> **“Còn đường tham chiếu nào từ một GC root tới object này, và đường ấy có còn mang ý nghĩa nghiệp vụ không?”**

Trả lời được câu hỏi đó là nền tảng để debug memory leaks, hiểu aliasing, thiết kế cache/listener lifecycle và làm việc an toàn với Java 17.

## Tài liệu tham khảo chính thức Java SE 17

- **Java Language Specification `12.6 — Finalization of Class Instances**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.6
- **JLS `12.6.1 — Implementing Finalization** (định nghĩa về reachability và các giới hạn liên quan): https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.6.1
- **`java.lang.ref` package**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html
- **`java.lang.ref.Reference` và `reachabilityFence`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html
- **`java.lang.ref.WeakReference`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html
- **`java.util.WeakHashMap`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html
- **`java.lang.AutoCloseable`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html
- **`java.lang.ThreadLocal`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html
