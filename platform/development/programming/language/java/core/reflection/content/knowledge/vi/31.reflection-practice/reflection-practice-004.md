# Đọc object graph bằng Reflection và kiểm soát vòng tham chiếu

Một **object graph** (đồ thị đối tượng) gồm các đối tượng Java là **đỉnh**, còn tham chiếu từ field, phần tử mảng hoặc collection là **cạnh**. Một đối tượng có thể được nhiều đối tượng khác trỏ tới, tự trỏ tới chính mình, hoặc nằm trong vòng tham chiếu như `A.next = B` và `B.next = A`.

Khi viết trình duyệt object graph, debugger, công cụ tạo snapshot, serializer hay bộ chẩn đoán sử dụng Reflection, không thể đơn giản gọi đệ quy trên mọi field đến vô hạn. Phải đồng thời bảo vệ **tính đúng đắn của định danh đối tượng**, **độ sâu**, **số node/phần tử**, **quyền truy cập**, **tính ổn định** và **dữ liệu nhạy cảm**.

Nguyên tắc quan trọng nhất: dùng **định danh tham chiếu (`==`)** thay vì `equals()` để nhận ra một đối tượng đã gặp; ghi nhận nó **trước khi** đi sâu vào các field. Khi thấy lại đối tượng đó, chỉ in tham chiếu đến node đã ghi nhận, không đi tiếp.

## 1. Đồ thị khác cây như thế nào?

Ví dụ:

~~~text
A ──next──> B
^           |
|           |
+──next─────+
A ──items[0]──> B
~~~

Ở đây:

- `A` và `B` là **hai instance** độc lập.
- `A.next` và `A.items[0]` cùng tham chiếu đến **một instance B**. Đây là **shared reference/alias**.
- `B.next` tham chiếu ngược đến `A`. Đây là một **chu trình**.
- Nếu chỉ xem từng cạnh riêng lẻ rồi gọi đệ quy, traversal sẽ lặp mãi `A → B → A → B ...`.

Cần phân biệt **đã từng gặp** với **nằm trong chu trình hiện tại**:

| Trạng thái | Ý nghĩa |
| --- | --- |
| Chưa gặp instance | Có thể cấp ID và đi sâu nếu còn ngân sách |
| Đã gặp trong đường đi đệ quy hiện tại | Có đường vòng (*cycle*) quay lại node đang xử lý |
| Đã gặp nhưng không ở đường đi hiện tại | Tham chiếu dùng chung (*alias*) đến node đã xử lý |
| Chạm ngưỡng độ sâu/số node | Không kết luận phần còn lại có hay không có chu trình; chỉ đánh dấu **bị cắt** |

Với mục tiêu **in đồ thị không lặp và giữ cấu trúc chia sẻ**, một bảng `seen` toàn cục cho *một lượt duyệt* là đủ: mọi lần gặp lại đều in `ref #id`. Nếu muốn **phân loại riêng cycle và alias**, cần thêm tập các node *đang ở trên stack* (thường gọi `active`, `gray` hay DFS recursion stack). Bài thực hành bên dưới chọn biểu diễn `ref #id` để bảo toàn identity đơn giản; không gọi tất cả tham chiếu lặp là “cycle”.

## 2. Vì sao phải dùng `IdentityHashMap`?

Có hai khái niệm dễ bị nhầm:

- **Bằng nhau về nội dung:** `x.equals(y)` có thể là `true` ngay cả khi `x` và `y` là hai instance khác nhau. Ngược lại, một số lớp định nghĩa `equals()`/`hashCode()` dựa trên dữ liệu thay đổi được.
- **Cùng một đối tượng:** `x == y`. Đây là identity cần cho đồ thị object, vì hai instance có nội dung giống nhau vẫn là hai node riêng.

Nếu dùng `HashSet<Object> visited` hoặc `HashMap<Object, Integer>`, Java gọi `equals()` và `hashCode()` của chính đối tượng cần duyệt. Điều này có thể gây kết luận sai, side effect hoặc đệ quy vô hạn nếu hai phương thức ấy lại duyệt graph.

`IdentityHashMap<Object, Integer> seen` sử dụng **reference equality (`==`)** cho khóa. Nó tránh phụ thuộc vào cài đặt `equals()`/`hashCode()` của object.

~~~java
IdentityHashMap<Object, Integer> seen = new IdentityHashMap<>();
seen.put(node, 1);
Integer previousId = seen.get(node); // 1 khi cùng instance node
~~~

Đoạn trên chỉ minh họa cách dùng trong một method; cần `import java.util.IdentityHashMap;`. Không dùng `System.identityHashCode(obj)` làm **ID duy nhất** vì hash có thể va chạm. Trong ví dụ hoàn chỉnh, ta cấp ID số nguyên tăng dần theo thứ tự thăm và lưu trong `IdentityHashMap`.

**Thứ tự đúng:** khi thấy node mới, cấp ID và đưa vào `seen` **trước khi** duyệt children. Nếu chờ đến khi xử lý xong children mới đánh dấu, chu trình `A → B → A` vẫn có thể lặp vô hạn.

## 3. Quy định phạm vi và ngân sách của công cụ

Trước khi quét, phải quyết định những gì được phép đọc. Ví dụ của bài áp dụng các chính sách rõ ràng:

1. **Đối tượng lá:** `null`, `String`, `Number`, `Boolean`, `Character`, `enum`, `Class` được in giá trị, không mở sâu các field. Có thể mở rộng tập leaf theo domain; trong môi trường không tin cậy, ngay cả `toString()` của một subclass `Number` có thể gây side effect, nên chỉ in các kiểu được phép rõ ràng.
2. **Mảng:** dùng `Array.getLength`/`Array.get` để đọc cả mảng primitive và reference. Cắt sau `maxArrayItems` phần tử.
3. **Đối tượng application:** duyệt instance fields từ class tới superclass, bỏ `static` và `synthetic`; gắn **declaring class** vào tên field để phân biệt field bị hide bởi lớp con.
4. **Đối tượng JDK không phải leaf/mảng:** trong demo, dừng như node **opaque** và không phản xạ vào internal fields thuộc package `java.*`. Đây là chính sách mẫu, không thay thế allowlist package/type cần có cho production.
5. **Quyền đọc:** thử `Field.canAccess(receiver)`; khi chưa có quyền, `trySetAccessible()` chỉ được thực hiện nếu đó là chính sách cho phép. Nếu vẫn không được, in `<inaccessible>`. Không giả định module nào cũng cho deep reflection.
6. **Giới hạn:** `maxDepth` giới hạn số lớp lồng nhau, `maxNodes` giới hạn số object/array mới được mở, `maxArrayItems` giới hạn số phần tử mảng được xem.
7. **Thứ tự:** sắp xếp field theo tên rồi theo declaring class. `getDeclaredFields()` không cam kết thứ tự; không dùng kết quả tự nhiên của mảng để xây snapshot có tính lặp lại.
8. **Không gọi getter tự động:** ví dụ chỉ đọc field. Getter và `toString()` tùy ý có thể chạy logic nghiệp vụ, thực hiện I/O, thay đổi trạng thái hoặc ném exception.

Lưu ý: **giới hạn độ sâu/số node/phần tử chưa phải sandbox chống dữ liệu thù địch**. Một class có quá nhiều field, một lời gọi `toString()` không an toàn, getter hoặc traversal collection tùy ý vẫn có thể tốn tài nguyên. Production cần thêm ngân sách thời gian, số field, độ dài chuỗi, bytes đầu ra, cancellation và allowlist adapters.

## 4. Ví dụ Java 17+ đầy đủ: `IdentityHashMap`, mảng và cycle

Tạo một tệp **`ObjectGraphDemo.java`** và sao chép toàn bộ chương trình:

~~~java
import java.lang.reflect.Array;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.IdentityHashMap;
import java.util.List;

public class ObjectGraphDemo {
    private static final class Node {
        private final String name;
        private Node next;
        private Object[] items;

        private Node(String name) { this.name = name; }
    }

    private static final class Walker {
        private final IdentityHashMap<Object, Integer> seen = new IdentityHashMap<>();
        private final int maxDepth;
        private final int maxNodes;
        private final int maxArrayItems;

        private Walker(int maxDepth, int maxNodes, int maxArrayItems) {
            this.maxDepth = maxDepth;
            this.maxNodes = maxNodes;
            this.maxArrayItems = maxArrayItems;
        }

        private static boolean leaf(Class<?> type) {
            return type.isPrimitive()
                    || type == String.class
                    || Number.class.isAssignableFrom(type)
                    || type == Boolean.class
                    || type == Character.class
                    || type.isEnum()
                    || type == Class.class;
        }

        private static List<Field> fields(Class<?> type) {
            List<Field> result = new ArrayList<>();
            for (Class<?> c = type; c != null && c != Object.class;
                    c = c.getSuperclass()) {
                for (Field field : c.getDeclaredFields()) {
                    int modifiers = field.getModifiers();
                    if (!Modifier.isStatic(modifiers) && !field.isSynthetic()) {
                        result.add(field);
                    }
                }
            }
            result.sort(Comparator.comparing(Field::getName)
                    .thenComparing(f -> f.getDeclaringClass().getName()));
            return result;
        }

        private void visit(String label, Object value, int depth) {
            String pad = "  ".repeat(depth);
            if (value == null) {
                System.out.println(pad + label + ": null");
                return;
            }

            Class<?> type = value.getClass();
            if (leaf(type)) {
                System.out.println(pad + label + ": " + value);
                return;
            }

            Integer id = seen.get(value);
            if (id != null) {
                System.out.println(pad + label + ": ref #" + id);
                return;
            }
            if (depth > maxDepth) {
                System.out.println(pad + label + ": <max depth>");
                return;
            }
            if (seen.size() >= maxNodes) {
                System.out.println(pad + label + ": <max nodes>");
                return;
            }

            id = seen.size() + 1;
            seen.put(value, id); // Must precede exploring children.
            System.out.println(pad + label + ": #" + id + " " + type.getSimpleName());

            if (type.isArray()) {
                int length = Array.getLength(value);
                for (int i = 0; i < Math.min(length, maxArrayItems); i++) {
                    visit("[" + i + "]", Array.get(value, i), depth + 1);
                }
                if (length > maxArrayItems) {
                    System.out.println(pad + "  ... <array truncated>");
                }
                return;
            }

            if (type.getPackageName().startsWith("java.")) {
                System.out.println(pad + "  <opaque JDK object>");
                return;
            }

            for (Field field : fields(type)) {
                String fieldLabel = field.getDeclaringClass().getSimpleName()
                        + "." + field.getName();
                try {
                    if (!field.canAccess(value) && !field.trySetAccessible()) {
                        System.out.println(pad + "  " + fieldLabel + ": <inaccessible>");
                        continue;
                    }
                    visit(fieldLabel, field.get(value), depth + 1);
                } catch (IllegalAccessException | RuntimeException ex) {
                    System.out.println(pad + "  " + fieldLabel + ": <inaccessible>");
                }
            }
        }
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");
        a.next = b;
        b.next = a;
        a.items = new Object[] {b, "tail"};

        System.out.println("== graph ==");
        new Walker(4, 20, 10).visit("root", a, 0);

        System.out.println("== limits ==");
        new Walker(0, 1, 10).visit("root", a, 0);
    }
}
~~~

Trong terminal tại thư mục chứa tệp, dùng JDK 17+:

~~~bash
javac --release 17 ObjectGraphDemo.java
java ObjectGraphDemo
~~~

Kết quả được kiểm chứng bằng biên dịch và chạy Java:

~~~text
== graph ==
root: #1 Node
  Node.items: #2 Object[]
    [0]: #3 Node
      Node.items: null
      Node.name: B
      Node.next: ref #1
    [1]: tail
  Node.name: A
  Node.next: ref #3
== limits ==
root: #1 Node
  Node.items: <max depth>
  Node.name: A
  Node.next: <max depth>
~~~

Chương trình này sử dụng `Node` là nested class trong cùng top-level class với `Walker`; theo quy tắc **nestmate** của Java 17+, code có thể đọc các field private của `Node` khi đủ điều kiện. Với lớp của thư viện khác hoặc named module không mở package, việc đọc private có thể bị chặn và output `<inaccessible>` là kết quả hợp lệ.

### Giải thích output theo thứ tự

- `root: #1 Node`: lần đầu gặp instance `A`, cấp ID 1 và đưa ngay vào `seen`.
- `Node.items: #2 Object[]`: mảng là **một đối tượng** có identity riêng, được đánh số #2 và duyệt các phần tử.
- `[0]: #3 Node`: đối tượng `B` chưa gặp nên nhận ID 3.
- `Node.next: ref #1` bên dưới B: `B.next` quay về A đã ghi nhận, nên dừng tại tham chiếu này và không đi vào vô hạn.
- `Node.next: ref #3` bên dưới A: `A.next` dùng lại đúng B; không tạo thêm một bản B. Đây là shared reference; không nhất thiết là một vòng mới.
- Lượt `new Walker(0, 1, 10)` dùng **bảng visited mới**, chỉ mở root ở depth 0; các object ở depth 1 bị cắt bằng `<max depth>`. Field leaf `Node.name` vẫn đọc được giá trị `A`.

Điểm thiết kế quan trọng: `seen` là state của **một lần walk**, không dùng `static` hoặc chia sẻ giữa các request. Một walker mới bắt đầu với namespace ID mới; đồng thời `IdentityHashMap` không an toàn khi nhiều thread cùng thay đổi nó.

## 5. Phân biệt kiểm soát vòng tham chiếu và kiểm soát giới hạn

Một đoạn đệ quy kiểu `walk(field.get(value))` chỉ an toàn khi biết graph là cây không chu trình. Trong graph tổng quát, phải theo dõi identity và áp giới hạn:

| Biện pháp | Ngăn được | Chưa giải quyết |
| --- | --- | --- |
| `IdentityHashMap` visited | Duyệt lặp cùng instance, bao gồm cycle/alias | Graph có vô số node khác nhau hoặc traversal trên nguồn dữ liệu không ổn định |
| Đánh dấu *trước khi* đi vào children | Cycle ngay lập tức `A → A` hoặc `A → B → A` | Hạn mức bộ nhớ/thời gian |
| `maxDepth` | Stack quá sâu và traversal theo chiều sâu quá dài | Graph rất rộng ở độ sâu nhỏ |
| `maxNodes` | Mở quá nhiều object/array độc lập | Mỗi object có quá nhiều field, string quá lớn |
| `maxArrayItems` | Mảng lớn gây quá nhiều lần đọc phần tử | Collection/map lớn và dữ liệu ngoài array |
| Lọc field và kiểu | Truy cập nhầm static/synthetic, JDK internals | Private access hợp lệ, dữ liệu nhạy cảm, hiệu ứng phụ |
| Sắp xếp field | Snapshot lệ thuộc thứ tự mảng Reflection | Graph thay đổi trong lúc duyệt do concurrent mutation |

**Thứ tự các kiểm tra cũng có ý nghĩa:** trong mã, null/leaf được xử lý trước; đối tượng đã nằm trong `seen` được in `ref`; node mới sau đó mới bị xét giới hạn depth/node. Vì thế một tham chiếu lặp tới node đã mở có thể vẫn hiện `ref #id` ngay cả khi sâu hơn `maxDepth`, trong khi node chưa mở tại độ sâu đó hiện `<max depth>`.

Các chuỗi `<max depth>`/`<max nodes>` có nghĩa **“chưa duyệt”**, không có nghĩa con trỏ null hoặc object không tồn tại. Đừng dùng snapshot bị cắt làm căn cứ khẳng định graph không có chu trình.

### Muốn phân biệt cycle với alias thật sự

Mở rộng DFS bằng hai cấu trúc:

- `seen`: instance đã được phát hiện trong cả lượt duyệt (để cấp ID và ngăn duyệt trùng).
- `active`: instance đang nằm trên đường đệ quy hiện tại.

Khi duyệt child, nếu nó ở `active` thì đó là **back-edge/cycle**; nếu chỉ ở `seen` nhưng không ở `active` thì đó là **shared reference**. Xóa instance khỏi `active` trong `finally` khi hoàn tất duyệt nhánh, nhưng **không xóa khỏi `seen`**. Khi traversal bị cắt vì giới hạn, phải giữ trạng thái “truncated” để không suy luận thiếu dữ liệu là bằng chứng về việc không có vòng.

Với snapshot/debug output, chỉ cần `ref #id` thường đã đủ; việc phân biệt alias/cycle tùy mục tiêu ứng dụng.

## 6. Mảng, collection, map và kiểu đặc biệt

Ví dụ hỗ trợ **mảng** trực tiếp bằng `java.lang.reflect.Array`:

- `int[]` chứa primitive nhưng toàn bộ mảng vẫn là **object** có identity; `Array.get(array, i)` trả giá trị boxed như `Integer`.
- `Object[]` có thể chứa null, phần tử chia sẻ instance, hoặc tham chiếu ngược về chính mảng đó. `seen` xử lý được nếu đánh dấu mảng trước khi duyệt.
- Với mảng nhiều chiều, mỗi mảng con có identity riêng. Không giả định mọi hàng có cùng độ dài.

**Collection và map cần adapter chuyên biệt**, chẳng hạn duyệt `List` theo index, `Map` theo key/value hoặc `Optional` theo giá trị. Không nên tự do reflect các field nội bộ của `ArrayList`/`HashMap`: cấu trúc bên trong là chi tiết implementation và có thể bị JPMS chặn.

Khi thêm adapter:

1. Áp dụng **cùng một bảng identity** cho container và các phần tử; container cũng có thể tham chiếu chính nó (ví dụ `list.add(list)`).
2. Đặt hạn mức phần tử để tránh dữ liệu quá lớn.
3. Định nghĩa thứ tự biểu diễn; `HashMap`/`HashSet` không cam kết insertion order. Nếu sắp xếp key, chỉ dùng comparator an toàn cho key tương ứng và tránh gọi tùy tiện `toString`/`compareTo` trên dữ liệu không tin cậy.
4. Không gọi các getter, lazy collections hoặc iterators có side effect trong snapshot chẩn đoán nếu chưa có chính sách/ủy quyền rõ.
5. Đặt chính sách với `WeakReference`, `AtomicReference`, proxy, records và ORM lazy proxies; tham chiếu logic có thể khác field vật lý.

Các đối tượng như `Thread`, `ClassLoader`, `Socket` hoặc dữ liệu nội bộ JDK không phải mặc nhiên là những nút nên mở sâu; tốt hơn là in kiểu, trạng thái được cho phép hoặc marker `opaque`.

## 7. Quyền truy cập Reflection và bảo vệ thông tin

`getDeclaredFields()` trả metadata của field private/protected/package-private nhưng **không bảo đảm caller có quyền đọc giá trị**. Mã có thể cần `Field.canAccess(receiver)`, `trySetAccessible()` và xử lý `IllegalAccessException`; trong named modules, package chưa `opens` cho caller có thể ngăn `trySetAccessible()`. Không ép tất cả package dùng `--add-opens` chỉ để debugger chạy được.

Trong ứng dụng thực, cân nhắc chính sách **public only** hoặc explicit allowlist thay cho việc luôn thử nâng quyền. Ví dụ này có `trySetAccessible()` để minh họa kỹ thuật trong phạm vi được phép; không có nghĩa mọi field private đều nên bị đọc trong hệ thống sản xuất.

Cần **redact hoặc bỏ qua** mật khẩu, token, khóa bí mật, thông tin cá nhân, connection strings, nội dung body HTTP nhạy cảm, bất kể field có modifier gì. Việc reflection đọc được dữ liệu không tạo ra quyền công bố dữ liệu đó.

Một cây output an toàn có thể dùng các marker:

~~~text
user.password: <redacted>
payment.token: <redacted>
jdkObject: #12 SomeJdkType
  <opaque JDK object>
internalField: <inaccessible>
largeGraph: <max nodes>
~~~

Khi logging, cũng cần chặn escape/control characters, giới hạn độ dài string và tổng dung lượng output; ví dụ minh họa chưa thực hiện tất cả các biện pháp này.

## 8. Tính nhất quán và giới hạn thực tế

- **Độ phức tạp:** nếu xét mỗi node/cạnh không bị cắt đúng một lần, duyệt graph có độ phức tạp gần `O(V + E)` cho phần được duyệt, ngoài chi phí phản xạ/sắp xếp field. `seen` cần `O(V)` bộ nhớ theo số instance đã gặp. Bộ giới hạn chỉ đặt trần cho một số tài nguyên cụ thể, không tự chứng minh toàn bộ công cụ đạt giới hạn thời gian.
- **Mutable graph:** graph thay đổi trong lúc đang đọc có thể cho snapshot bất nhất, thậm chí gặp null/giá trị khác giữa hai lần truy cập. `IdentityHashMap` không tạo ra atomic snapshot hoặc thread safety cho object graph. Muốn snapshot nhất quán, cần cơ chế snapshot/locking thích hợp hoặc đọc immutable DTO.
- **Hiệu ứng phụ:** `Field.get` không gọi getter, nhưng xử lý một object bằng `toString()`, iterator hoặc adapter do người dùng định nghĩa có thể chạy logic; cần kiểm soát. Trong demo, leaf `Number` được in bằng phép nối chuỗi; ở hệ thống không tin cậy nên thu hẹp whitelist và chuẩn hóa giá trị.
- **Class loader/proxy:** hai object từ các class loader khác nhau có thể có cùng class name; không nên nhận diện object chỉ bằng tên class hoặc `System.identityHashCode`. Identity dựa trên reference là yếu tố quyết định.
- **Field hiding:** hai field tên giống nhau trong cha/con là hai vị trí lưu trữ độc lập; demo gắn `getDeclaringClass()` vào nhãn để không nhập nhằng. Ở production nên dùng cả tên package/declaring class nếu tên class đơn giản có thể trùng nhau.
- **Ngoại lệ:** `trySetAccessible()` có thể bị từ chối, `Field.get` có thể ném `IllegalAccessException`, phản xạ trên kiểu lạ hoặc class bị nạp động có thể thất bại. Không được nuốt lỗi rồi coi mọi field bị lỗi là null.
- **Truy cập kiểu primitive:** Reflection có thể trả wrapper khi dùng `Field.get`; nếu cần phân biệt primitive declared type hãy xét `field.getType()` thay vì chỉ `value.getClass()`.
- **Bảo toàn output:** khi serializing JSON, không thể tự biểu diễn chu trình bằng đối tượng lồng nhau thông thường. Cần schema xác định (`$id`/`$ref` hoặc equivalent), hoặc chính sách từ chối cycle rõ ràng.

## 9. Các câu hỏi tự kiểm tra

1. Nếu hai instance có `equals() == true` nhưng `a != b`, có nên coi chúng là cùng một node khi duyệt object graph? **Không**; dùng identity.
2. Vì sao phải `seen.put(value, id)` trước khi duyệt field con? Để chu trình quay lại node hiện tại nhận ra ngay.
3. Nếu `A.child` và `B.child` trỏ tới cùng `C` nhưng graph không có cycle, lần xuất hiện thứ hai của `C` nên là gì? **`ref` đến cùng ID**, vì đây là alias.
4. Nếu một object không thể đọc private field do module chưa open, có phải field ấy không tồn tại? **Không**; có metadata nhưng không có quyền truy cập giá trị.
5. Nếu dừng ở `<max depth>`, có thể khẳng định subgraph đã bị cắt không có chu trình không? **Không**.
6. Nếu có `List` chứa chính nó, nên xử lý ra sao khi thêm List adapter? Cấp ID cho List, đánh dấu vào `seen` trước, rồi duyệt phần tử và gặp lại dưới dạng `ref`.

**Ghi nhớ:** đọc object graph bằng Reflection là **duyệt một đồ thị theo identity với giới hạn và quyền truy cập cụ thể**. `IdentityHashMap` + đánh dấu sớm ngăn vòng tham chiếu; depth/node/array budgets giới hạn phạm vi; chính sách kiểu, field, access, redaction và snapshot nhất quán quyết định công cụ có thực sự an toàn và đáng tin hay không.

**Tài liệu Java SE 21:** [`IdentityHashMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/IdentityHashMap.html), [`Class.getDeclaredFields`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getDeclaredFields()), [`Field`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html), [`Array`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Array.html), [`AccessibleObject`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html).