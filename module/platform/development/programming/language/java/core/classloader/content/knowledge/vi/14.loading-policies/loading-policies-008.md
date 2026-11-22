# Phát hiện chu trình ủy quyền và tránh gọi lặp vô hạn trong Java ClassLoader

## 1. Vấn đề: một yêu cầu nạp lớp đi vòng rồi quay lại điểm xuất phát

`ClassLoader` thường phối hợp theo cơ chế **delegation**: một loader nhận tên lớp, hỏi parent và chỉ tự tìm class khi parent không tìm được. Quy trình này giúp chia sẻ các lớp nền tảng, API/SPI chung và hạn chế tạo trùng runtime type. Tuy nhiên, nếu ứng dụng tự xây dựng quan hệ ủy quyền giữa nhiều loader mà **không kiểm soát hướng đi**, một yêu cầu có thể vòng lại loader ban đầu.

Ví dụ về đồ thị được cấu hình sai:

```text
                loadClass("plugin.Report")
                      |
                      v
                PluginLoader A
                      |
                 delegate to
                      v
                PluginLoader B
                      |
                 delegate to
                      v
                PluginLoader A
                      |
                 delegate to B
                      v
                     ...
```

Nếu mỗi loader chỉ chuyển tiếp yêu cầu mà không nhận ra nó đã xuất hiện trên cùng đường xử lý, lời gọi Java có thể lặp tới khi stack cạn, gây `StackOverflowError`. Trong những cài đặt giữ khóa nạp lớp xuyên nhiều loader, một vòng yêu cầu còn có thể dẫn tới **deadlock giữa các luồng**, tùy thứ tự lock và thuật toán delegation.

Chủ đề cần giải quyết gồm:

1. Khi nào một chu trình ủy quyền xuất hiện?
2. Cách phân biệt chu trình **giữa các loader** với đệ quy hợp lệ và với chu trình **kế thừa lớp**.
3. Cách thiết kế một **đồ thị ủy quyền không có chu trình**.
4. Cách phát hiện đường gọi lặp bằng khóa nhận diện **(loader, binary name)**.
5. Vì sao guard theo luồng chỉ giải quyết **đệ quy trên cùng luồng**, không đủ cho mọi bài toán đa luồng.
6. Cách kiểm thử và ghi log mà không làm hỏng nguyên tắc nạp lớp, khóa, parent delegation và type identity.

## 2. Phải phân biệt bốn loại “chu trình”

| Tình huống | Ví dụ | Hậu quả / cách hiểu |
| --- | --- | --- |
| Chu trình **delegation** tự thiết kế | A hỏi B, B hỏi A về cùng `com.acme.Widget` | Có thể lặp lời gọi `loadClass` vô hạn nếu không có guard hoặc hướng thoát |
| Chu trình **quan hệ lớp/interface trong class file** | X extends Y, Y extends X ở bytecode không hợp lệ | JVM có thể ném `ClassCircularityError`; đây không đơn thuần là lỗi gọi lặp giữa hai custom loader |
| Khởi tạo tĩnh đệ quy **cùng luồng** | Trong `<clinit>` của X, một method lại yêu cầu initialization của X | JVM có quy tắc reentrant initialization; không thể tự suy ra `loadClass` của custom loader đã tạo chu trình |
| Deadlock khởi tạo/nạp giữa **các luồng** | Thread T1 giữ một lock/đợi B, T2 giữ lock/đợi A | Có thể bị treo chéo; phát hiện recursion bằng `ThreadLocal` trên từng thread không tự giải quyết được |

Hai loại lỗi Java hay bị nhầm:

- **`StackOverflowError`:** thường là hệ quả của chuỗi lời gọi Java đệ quy quá sâu. Một custom `loadClass` sai có thể gây lỗi này, nhưng không phải chỉ riêng ClassLoader mới gây ra.
- **`ClassCircularityError`:** thuộc họ `LinkageError`, báo chu trình không hợp lệ trong hệ phân cấp class/interface khi JVM kiểm tra định nghĩa. **Không có bảo đảm** JVM sẽ biến mọi vòng `A.loadClass → B.loadClass → A.loadClass` thành lỗi này.

Không nên xử lý chu trình bằng cách `catch (StackOverflowError)` rồi tiếp tục nạp: đến lúc đó tài nguyên stack đã bị dùng quá mức. **Phòng ngừa trước lời gọi đệ quy** là hướng đúng.

## 3. Parent chain thông thường không phải đồ thị ngang tùy ý

Trong ví dụ đơn giản:

```text
Bootstrap
    ^
Platform
    ^
Application
    ^
Plugin A
    ^
Plugin B
```

Mũi tên biểu diễn hướng ủy quyền về phía parent. Một `ClassLoader` thường nhận parent tại lúc khởi tạo qua `super(parent)`; API public thông thường không cung cấp setter để thay parent tùy ý về sau. Với chuỗi parent được tạo theo cách thông thường, loader mới trỏ tới loader đã tồn tại, nên ứng dụng không dễ tạo vòng **bằng riêng quan hệ parent được lưu trong constructor**.

Ngược lại, chu trình hay đến từ **chính sách tùy biến bên ngoài parent chain**, chẳng hạn:

- A override `loadClass` và gửi một số namespace cho B; B lại gửi namespace ấy cho A.
- Plugin A dùng TCCL hoặc service registry để tìm plugin B; một callback của B quay về A và lặp lại yêu cầu nạp cùng class.
- Một router chứa bản đồ `package → delegate` có cấu hình mâu thuẫn: A chuyển `shared.*` cho B và B lại chuyển `shared.*` cho A.
- Một custom loader override `findClass(name)` nhưng thay vì tìm bytecode cục bộ lại gọi `this.loadClass(name)` hoặc vòng qua service khác rồi quay lại cùng yêu cầu.

**Lưu ý:** `getParent()` giúp quan sát parent chain, nhưng nó **không thể hiện hết** các cạnh ủy quyền do custom code tạo. Một chuỗi parent bình thường vẫn có thể đi cùng đồ thị callback/delegation vòng.

## 4. Quy trình loadClass mặc định và nơi dễ phá vỡ

`ClassLoader.loadClass(String, boolean)` trong mô hình mặc định về cơ bản:

1. Sử dụng khóa nạp phù hợp từ `getClassLoadingLock(name)`.
2. Gọi `findLoadedClass(name)` để tránh tìm/định nghĩa lại lớp đã được JVM ghi nhận.
3. Nếu chưa có, hỏi parent hoặc cơ chế bootstrap tương ứng.
4. Nếu parent không tìm được, gọi `findClass(name)` để tìm bytecode riêng.
5. Tùy tham số, thực hiện resolution rồi trả về `Class<?>`.

```text
loadClass("plugin.Report")
   |
   +-- findLoadedClass("plugin.Report") --- thấy ---> trả Class hiện có
   |
   +-- parent.loadClass("plugin.Report") -- thấy ---> trả Class của parent
   |
   +-- findClass("plugin.Report") ------- đọc bytecode -> defineClass
```

Override **chỉ `findClass`** để thay nguồn bytecode thường an toàn hơn override toàn bộ `loadClass`, vì giữ được cơ chế kiểm tra lớp đã nạp, parent-first và khóa nạp. Nếu muốn **child-first có chọn lọc**, việc override `loadClass` có thể cần thiết nhưng phải chủ động duy trì các hợp đồng quan trọng này.

Một anti-pattern dễ tạo recursion:

```java
@Override
protected Class<?> findClass(String name)
        throws ClassNotFoundException {
    return loadClass(name); // Sai: vòng về luồng loadClass hiện tại.
}
```

Đây là **mã lỗi để phân tích**, không phải triển khai sử dụng. Nếu parent không tìm ra lớp, `loadClass` gọi `findClass`; đoạn `findClass` này lại gọi `loadClass` với cùng tên, có thể dẫn đến vòng lặp:

```text
loadClass -> parent không tìm thấy -> findClass
              ^                        |
              |________________________|
```

Cách đúng là `findClass` **tìm bytecode từ nguồn cục bộ rồi `defineClass`**, hoặc ném `ClassNotFoundException` nếu không tìm ra nguồn hợp lệ; không chạy lại toàn bộ thuật toán nạp chính tên ấy.

## 5. Phát hiện đệ quy cùng luồng bằng cặp (loader, binary name)

Một guard điển hình theo dõi các yêu cầu đang nằm trên **đường gọi hiện tại**. Mỗi node được xác định bằng:

```text
(defining/visited loader object identity, requested binary name)
```

Chính xác hơn, ở giai đoạn chưa định nghĩa class thì node là **đối tượng loader đang xử lý request** cùng với tên lớp yêu cầu; chưa thể khẳng định nó sẽ là defining loader. Dùng danh tính đối tượng loader chứ không chỉ chuỗi tên loader, vì hai loader khác nhau có thể cùng hiển thị tên hoặc `toString()`.

Ý tưởng:

1. Trước khi router xử lý `(A, "plugin.Report")`, thêm cặp này vào một tập *in-progress* của thread.
2. Khi A chuyển cho B, thêm `(B, "plugin.Report")`.
3. Nếu B quay lại A với **cùng tên**, cặp `(A, "plugin.Report")` đã tồn tại; đây là tín hiệu đường gọi lặp ngay trên thread đó.
4. Báo lỗi có giải thích chu trình, hoặc thoát theo một chiến lược fallback **đã được thiết kế từ trước**; không tiếp tục chuyển tiếp vô hạn.
5. Trong `finally`, loại bỏ cặp vừa thêm. Khi đường xử lý kết thúc, dọn ThreadLocal để tránh giữ tham chiếu loader trong thread pool.

**Vì sao phải có binary name?** Việc xử lý class A có thể hợp lệ khi cần nạp **class B khác tên**; không phải mọi lần cùng loader xuất hiện trong một call stack đều là chu trình sai. Theo dõi ít nhất `(loader, name)` giúp tránh chặn nhầm phần lớn phụ thuộc hợp lệ. Tuy nhiên, một chu trình có thể đi qua nhiều tên lớp trước khi quay lại; nếu không bao giờ lặp đúng một cặp mà vẫn tạo đồ thị vô hạn theo quy tắc ứng dụng, cần giới hạn độ sâu/độ dài đường và chính sách nạp tổng thể.

**Vì sao không chỉ dùng một biến boolean toàn cục?** Hai thread khác nhau có thể nạp các class khác nhau một cách hợp lệ; một cờ chung dễ chặn nhầm. Đối với deadlock xuyên thread thì cần **phân tích đồ thị wait-for/lock**, không thể lấy một boolean chung làm giải pháp thay thế.

## 6. Ví dụ Java 17 chạy được: A → B → A, rồi chuyển sang đường không có vòng

Chương trình sau cố ý tạo một đồ thị ủy quyền **sai** giữa hai loader để quan sát guard chống recursion. Nó **không định nghĩa class mới**, mà minh họa cách nhận ra một đường gọi lặp của custom routing policy. Vì vậy kết quả độc lập với JAR ngoài và không cần tự tạo class file.

Một điểm thiết kế cần công khai: ví dụ override `loadClass(String)` **chỉ cho namespace kiểm thử `demo.*`** để quan sát guard; những tên khác vẫn dùng triển khai parent-first chuẩn. Đây là thí nghiệm về phát hiện chu trình, **không phải** bộ nạp plugin đa luồng sẵn sàng cho production. Thiết kế production cần các ràng buộc trong phần sau.

Lưu file `DelegationCycleDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;

public class DelegationCycleDemo {

    static final class RoutingLoader extends ClassLoader {
        private static final ThreadLocal<Set<Key>> ACTIVE =
                ThreadLocal.withInitial(HashSet::new);

        private record Key(RoutingLoader loader, String name) {}

        private final String id;
        private RoutingLoader next;

        RoutingLoader(String id) {
            super(ClassLoader.getPlatformClassLoader());
            this.id = id;
        }

        void routeTo(RoutingLoader other) {
            this.next = other;
        }

        @Override
        public Class<?> loadClass(String name)
                throws ClassNotFoundException {

            if (!name.startsWith("demo.")) {
                return super.loadClass(name);
            }

            Set<Key> active = ACTIVE.get();
            Key current = new Key(this, name);

            if (!active.add(current)) {
                throw new ClassNotFoundException(
                        "Delegation cycle at " + id + ": " + name);
            }

            try {
                if (next != null) {
                    return next.loadClass(name);
                }
                return super.loadClass(name);
            } finally {
                active.remove(current);
                if (active.isEmpty()) {
                    ACTIVE.remove();
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        RoutingLoader a = new RoutingLoader("A");
        RoutingLoader b = new RoutingLoader("B");

        a.routeTo(b);
        b.routeTo(a); // Đồ thị sai: A -> B -> A.

        try {
            a.loadClass("demo.Missing");
        } catch (ClassNotFoundException exception) {
            System.out.println(exception.getMessage());
        }

        b.routeTo(null); // A -> B -> platform; không còn vòng.

        try {
            a.loadClass("demo.Missing");
        } catch (ClassNotFoundException exception) {
            System.out.println("acyclic="
                    + exception.getClass().getSimpleName());
        }

        System.out.println("bootstrapString="
                + (a.loadClass("java.lang.String")
                        .getClassLoader() == null));
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac DelegationCycleDemo.java
java DelegationCycleDemo
```

Stdout xác định trong môi trường Java 17 thông thường:

```text
Delegation cycle at A: demo.Missing
acyclic=ClassNotFoundException
bootstrapString=true
```

**Diễn giải từng bước:**

1. `a.loadClass("demo.Missing")` thêm cặp `(A, demo.Missing)` vào tập của thread hiện tại.
2. A chuyển cho B, B thêm cặp `(B, demo.Missing)`.
3. B chuyển về A; lúc A thử thêm cặp cũ, `Set.add` trả `false`. Ví dụ chủ động ném `ClassNotFoundException` có thông điệp `Delegation cycle at A: demo.Missing` **trước khi stack tăng vô hạn**.
4. Các khối `finally` trên B và A dọn đường truy vết; sau đó đổi B thành điểm cuối có parent platform.
5. Lần yêu cầu thứ hai đi A → B → parent; không có vòng, nhưng `demo.Missing` thực sự vắng mặt nên kết thúc bằng `ClassNotFoundException` bình thường. `acyclic=...` cho biết **không tìm thấy class** khác với **đã phát hiện vòng**.
6. Với `java.lang.String`, thí nghiệm không áp dụng routing riêng mà dùng `super.loadClass`. Lớp JDK nền tảng được bootstrap định nghĩa, nên dòng cuối là `true`.

Chương trình dùng `record` và `ThreadLocal` có mặt trong Java 17; bản thân record `Key` so sánh bằng cả tham chiếu đối tượng loader và tên lớp. `ClassLoader` không override `equals` theo danh tính logic khác, nên phép so sánh loader trong record dùng identity của object theo mặc định.

### Điểm hạn chế quan trọng của ví dụ

- Custom `loadClass(String)` trong thí nghiệm là **router mô phỏng** cho `demo.*`; nó không xử lý đầy đủ trường hợp class đã nạp, resolve, namespace policy và đồng bộ như một loader production.
- `next` được thay đổi tuần tự trên một thread trước mỗi lần nạp. Nếu vừa nạp vừa thay đường routing ở nhiều thread, cần cơ chế công bố cấu hình an toàn hoặc tốt hơn là **cấu hình bất biến**.
- Guard `ACTIVE` của một thread không phát hiện chu trình chờ khi hai thread khác nhau đã nắm khóa/tài nguyên của hai loader.
- Khi một class tên `demo.*` tồn tại trong parent nhưng custom router vẫn ép qua peer trước, hành vi khác parent-first và phải được mô tả như policy cụ thể, không xem là hành vi mặc định của `URLClassLoader`.
- Ném `ClassNotFoundException` có thông điệp chu trình giúp ví dụ chạy dễ hiểu; ứng dụng thực tế có thể dùng một exception riêng ở **lớp cấu hình/router** để phân biệt cấu hình vòng với lớp thực sự vắng mặt. Không nên bắt mọi `LinkageError` hay `Throwable` rồi biến thành class-not-found.

## 7. Chiến lược tốt nhất: ngăn chu trình ngay khi cấu hình

Guard runtime giúp chẩn đoán và fail fast; giải pháp bền vững hơn là **không chấp nhận một đồ thị delegation có chu trình**.

Ví dụ một quan hệ policy:

```text
Host / Shared API loader
       ^
       |
Plugin API loader
    ^       ^
    |       |
Plugin A   Plugin B

Mọi plugin -> Shared API theo hướng cố định.
Không đặt cạnh Plugin A -> B và B -> A cho cùng namespace.
```

Đồ thị delegation theo **namespace** mới có ý nghĩa chính xác. Có thể cho A gửi namespace `shared.*` tới host và `pluginB.public.*` tới B, nhưng phải kiểm tra đường đi trên từng tập tên để không tạo vòng cho cùng yêu cầu.

### Kiểm tra đồ thị bằng DFS

Một thuật toán nhận một directed graph của các cạnh router:

1. Mỗi node là một loader hoặc cặp `(loader, namespace)` nếu routing phụ thuộc package/name.
2. Duyệt DFS từ mỗi node.
3. Đánh dấu node là **GRAY** khi đang nằm trên DFS stack; **BLACK** khi mọi cạnh đã duyệt xong.
4. Nếu gặp cạnh tới node GRAY, phát hiện **back edge** và có chu trình.
5. Từ chối cấu hình hoặc báo chính xác đường đi, ví dụ `A → B → C → A`.

```text
DFS(A):
  mark A = GRAY
  visit B:
    mark B = GRAY
    visit C:
      mark C = GRAY
      edge C -> A where A = GRAY   => CYCLE A -> B -> C -> A
```

**Độ phức tạp:** với đồ thị tường minh có V node và E cạnh, DFS phát hiện chu trình trong `O(V + E)` thời gian, bộ nhớ `O(V)`, không tính chi phí biểu diễn chính sách namespace.

Nhưng nếu quyết định route phụ thuộc vào **tên class cụ thể, thời điểm, phiên bản hay trạng thái runtime**, một DAG tĩnh của các loader có thể không phản ánh hết đồ thị gọi thật. Khi ấy nên kết hợp **kiểm tra cấu hình** với guard runtime trên đường thực thi, test mô phỏng và ràng buộc số lần chuyển tiếp.

### Thiết kế trách nhiệm một chiều

- API/SPI dùng chung do host/parent định nghĩa; loader plugin chỉ delegate lên đó.
- Implementation riêng do loader plugin tìm trong nguồn cục bộ (khi parent không có hoặc theo policy chọn lọc).
- Không sử dụng vòng callback “khi không tìm được class thì hỏi plugin khác, plugin khác lại hỏi plugin trước” mà thiếu *visited set*.
- Không định tuyến mọi namespace qua mọi plugin để “tăng khả năng tìm thấy”; cách đó làm type identity và lỗi phụ thuộc khó đoán.
- Cố định route map trước khi phục vụ request; nếu cần update, áp dụng snapshot bất biến hoặc versioned routing.

## 8. Chu trình giữa nhiều thread: ThreadLocal không đủ

Giả sử custom loader giữ lock riêng trong khi chuyển tiếp:

```text
Thread T1:
  giữ lock(A, "plugin.X")
  gọi B.loadClass("plugin.X")
                  \
                   \ chờ lock(B, "plugin.X")

Thread T2:
  giữ lock(B, "plugin.X")
  gọi A.loadClass("plugin.X")
                   \
                    \ chờ lock(A, "plugin.X")
```

Trong một thứ tự xen kẽ bất lợi, T1 chờ T2 và T2 chờ T1. Mỗi thread có **ThreadLocal riêng**, và chưa chắc thread nào từng xử lý cặp cùng tên hai lần. Do đó guard như ở ví dụ không bắt được **cross-thread deadlock**.

Không được suy diễn rằng JVM luôn phát hiện và tự hủy vòng chờ do mọi custom ClassLoader tạo ra. Cách giảm rủi ro:

1. **Tránh đồ thị ủy quyền có chu trình ngay từ kiến trúc.** Đây là biện pháp chính.
2. **Đừng giữ lock dài khi chuyển tiếp sang loader khác** nếu có thể thiết kế để việc tìm nguồn/định nghĩa class nằm trong quyền sở hữu một loader duy nhất. Tuy nhiên đừng tự ý bỏ khóa nạp làm hai thread định nghĩa trùng.
3. Nếu có nhiều khóa, thiết kế thứ tự lấy khóa nhất quán và tránh callback quay về loader trước.
4. Phân biệt khóa nạp class của JVM/loader với khóa ứng dụng trên cache, kho artifact, class loading callback, service registry.
5. Test song song cùng tên và nhiều tên class, dùng timeout trong test để phát hiện tình huống treo; timeout test **không** phải bằng chứng một runtime deadlock đã được “sửa”.
6. Khi nghi deadlock, lấy **thread dump** và đối chiếu các stack/monitor/lock chờ nhau; một số vòng chờ không hiện dưới dạng deadlock monitor chuẩn mà cần phân tích ngữ cảnh loader.

### Parallel capable ClassLoader không sửa chu trình

`ClassLoader.registerAsParallelCapable()` và `getClassLoadingLock(name)` hỗ trợ thiết kế loader nạp song song theo tên lớp khi đáp ứng điều kiện API. Chúng không tự biến đồ thị A→B→A thành DAG, cũng không thay thế logic tìm/định nghĩa một lớp đúng chuẩn.

Một loader override `loadClass` cần hiểu phương thức đồng bộ và những ràng buộc liên quan `findLoadedClass`, `defineClass`, `resolveClass`; lựa chọn khóa sai có thể gây race hoặc deadlock ngay cả khi đã có kiểm tra ThreadLocal.

## 9. Ghi log để tái dựng vòng ủy quyền

Một log đủ hữu ích nên ghi những trường sau:

| Trường | Ví dụ | Mục đích |
| --- | --- | --- |
| Request ID | `req-42` | Liên kết đường đi của một yêu cầu |
| Binary name | `plugin.Report` | Tên class đang được tìm |
| Loader identity | `A#1`, `B#2` | Phân biệt hai loader có thể cùng tên hiển thị |
| Delegate edge | `A → B` | Xác định chính sách chuyển tiếp |
| Thread | `worker-7` | Phân biệt recursion một thread và chờ giữa nhiều thread |
| Stage | `delegating / defined / not-found` | Biết đang tìm ở đâu và điều gì xảy ra |
| Duration/depth | `depth=3` | Nhận ra chuỗi bất thường sớm |
| Defining loader cuối | `HostLoader` hoặc `PluginLoader` | Xác nhận type identity của class trả về |

Ví dụ log minh họa (không phải stdout của chương trình Java ở phần 6):

```text
req=42 thread=main class=plugin.Report loader=A action=delegate target=B
req=42 thread=main class=plugin.Report loader=B action=delegate target=A
req=42 thread=main class=plugin.Report loader=A action=cycle-detected
```

Không log toàn bộ bytecode, token repository, URL bí mật hay đường dẫn nhạy cảm. Trong môi trường nhiều plugin, nên dùng một ID loader ổn định **trong tiến trình hiện tại** và xem `System.identityHashCode(loader)` chỉ là chỉ dấu hỗ trợ, không phải định danh toàn cục tuyệt đối (hash có thể trùng).

Nếu class đã nạp thành công, dùng `clazz.getClassLoader()` để xác minh **defining loader thực sự**; không nhầm với loader ban đầu nhận request hoặc TCCL của thread.

### Khi ứng dụng treo

Trên JVM hỗ trợ các công cụ attach và có quyền tương ứng:

```bash
jcmd <pid> Thread.print
```

Đây là lệnh tham khảo; phải thay `<pid>` bằng PID thật. Stack có thể cho thấy đường `A.loadClass → B.loadClass` hoặc các thread chờ monitor/lock liên quan. Cần đọc nhiều thread cùng lúc thay vì chỉ stack của thread đầu tiên gặp vấn đề.

Có thể kết hợp unified logging:

```bash
java -Xlog:class+load=info -cp app/classes com.acme.Main
```

Những tên classpath/class ở đây là ví dụ. Class-loading log phản ánh các sự kiện JVM nạp lớp; nó **không tự thay thế** log các lời gọi delegation tùy chỉnh. Nếu một chu trình nổ trước lúc định nghĩa class thành công, chỉ tìm log “class loaded” có thể không thấy đường vòng nào.

## 10. ClassCircularityError: lúc nào mới liên quan?

`ClassCircularityError` thuộc `LinkageError` và liên quan một chu trình trong quan hệ định nghĩa lớp/interface mà JVM phát hiện khi nạp/kiểm tra. Một đồ thị quan hệ bất hợp lệ có thể hình dung:

```text
class A extends B
class B extends A
```

Đây là **sơ đồ quan hệ không hợp lệ**, không phải code Java để biên dịch. `javac` thông thường đã từ chối inheritance cycle trong source; bytecode được sinh/biến đổi sai có thể khiến JVM gặp ràng buộc circularity lúc nạp.

So sánh:

- **Delegation cycle:** A-loader hỏi B-loader, B-loader hỏi A-loader về tên class; cốt lõi là **đồ thị lời gọi custom loader**. Nếu không guard, có thể là `StackOverflowError` hoặc deadlock.
- **Class circularity:** định nghĩa lớp/interface tạo **vòng kế thừa/phụ thuộc cấu trúc bị cấm** theo JVMS; có thể gây `ClassCircularityError`.
- **Static initialization cycle:** có thể có reference vòng trong static initializer; JVM có quy tắc initialization riêng, và một vòng chờ giữa hai thread là vấn đề khác.

Không nên viết:

```java
try {
    loader.loadClass(name);
} catch (ClassCircularityError error) {
    // Xem như mọi vòng loader đã được xử lý.
}
```

Đây là **mã sai để phân tích**, giả định có `loader` và `name`; nó vừa không phát hiện các vòng custom delegation thông thường, vừa có nguy cơ nuốt `Error` mang ý nghĩa lỗi bytecode/class graph thực sự.

## 11. Các lỗi thiết kế thường gặp

| Thiết kế sai | Hậu quả | Cách sửa |
| --- | --- | --- |
| Trong `findClass(name)` gọi lại `loadClass(name)` chính loader đó | Recursion khi parent không có class | Tìm bytes local rồi `defineClass` hoặc ném `ClassNotFoundException` |
| A delegate mọi `plugin.*` cho B và B delegate lại cho A | Vòng policy cho cùng namespace | Sửa graph thành hướng một chiều, hoặc trả not-found khi nguồn local không chứa |
| Chỉ dùng boolean `isLoading` toàn cục | False positive giữa nhiều thread/tên class | Theo dõi request theo thread và cặp loader–binary name; vẫn cần concurrency design |
| Chỉ track tên class, không track loader | Có thể chặn nhầm các lượt nạp cùng tên hợp lệ qua nhiều loader | Dùng danh tính loader và tên; xem ngữ cảnh path |
| Không dọn ThreadLocal khi có exception | Giữ lại loader, memory leak, false cycle về sau | Dọn trong `finally` và `ThreadLocal.remove()` khi trống |
| Bắt `StackOverflowError` để fallback | Hệ thống đã cạn stack; trạng thái không đáng tin | Phát hiện trước khi đệ quy bằng graph/visited guard |
| Route map thay đổi lúc nhiều thread load | Một yêu cầu đi theo cấu hình không nhất quán | Snapshot bất biến hoặc synchronization/đồng bộ publication |
| Custom `loadClass` bỏ `findLoadedClass`/locking | Trùng `defineClass`, `LinkageError`, race | Giữ mặc định khi có thể hoặc cài đầy đủ hợp đồng API |
| Cho phép “hỏi tất cả plugin” không giới hạn | Khó dự đoán kiểu, vòng phụ thuộc, chi phí cao | Chỉ định loader sở hữu namespace, giới hạn depth/budget |
| Chỉ kiểm tra thread-local rồi tuyên bố hết deadlock | Bỏ sót vòng chờ giữa các thread | Loại bỏ cạnh vòng, kiểm thử song song, theo dõi locks |
| Nhầm `ClassCircularityError` với vòng delegation | Chẩn đoán sai nguyên nhân | Xem stack, class hierarchy và đường custom loader |

## 12. Kiểm thử chính sách ủy quyền

Một bộ test tối thiểu cho loader/router nên gồm:

1. **Đường hợp lệ:** một tên class thuộc source local được định nghĩa đúng, lớp API chung được parent trả về.
2. **Lớp không tồn tại:** không có chu trình thì nhận `ClassNotFoundException` hữu hạn thời gian, không lặp vô hạn.
3. **Vòng 2 node:** A→B→A phải bị từ chối ở configuration validation hoặc bị runtime guard phát hiện sớm.
4. **Vòng 3 node:** A→B→C→A phải có kết quả tương tự, log chỉ rõ cạnh và class name.
5. **Không chặn nhầm:** A→B để nạp `util.Helper` từ A đang xử lý `plugin.Service` có thể là phụ thuộc hợp lệ nếu không quay lại cùng cặp hoặc vi phạm cấu hình.
6. **Lỗi giữa đường:** dù `ClassNotFoundException`, `IOException` hoặc một exception runtime được ném, state theo thread phải được dọn; lượt sau không bị nhận nhầm là còn nạp dở.
7. **Song song:** hai thread cùng tên và nhiều tên class khác nhau phải không định nghĩa trùng, không gặp deadlock; dùng timeout, thread dump khi test fail.
8. **Loader lifecycle:** sau khi plugin unload, registry/router, TCCL và ThreadLocal không giữ tham chiếu mạnh tới loader cũ ngoài ý muốn.
9. **Parent/bootstrap:** lớp nền tảng không bị định nghĩa lại, API/SPI host được chia sẻ đúng, type identity không sai.
10. **Class initialization:** static initializer không gọi vòng vào plugin router theo cách chờ chéo mà thiết kế chưa cho phép.

### Phân biệt fail-fast và fallback

Khi phát hiện chu trình, một số framework muốn bỏ qua nhánh bị lặp rồi thử **nguồn khác**. Điều này chỉ an toàn nếu:

- Đường tìm nguồn khác đã được mô tả rõ trong policy;
- Không âm thầm chọn bản cùng binary name khác API/ABI khiến kiểu runtime biến đổi khó dự đoán;
- Ghi lại sự kiện cycle và nguồn cuối được chọn;
- Không nuốt các lỗi bytecode/linkage nghiêm trọng để giả vờ chỉ là “class not found”.

Trong nhiều hệ thống, **từ chối cấu hình có chu trình ngay khi khởi động** đơn giản hơn và dễ debug hơn fallback động.

## 13. Bài tập tự kiểm tra

**Câu 1.** Nếu A gọi B để tìm `plugin.Item` và B lại gọi A để tìm cùng tên, JVM có bắt buộc ném `ClassCircularityError` không?

**Đáp án:** Không. Đó là chu trình lời gọi delegation tùy chỉnh, có thể dẫn tới recursion/stack overflow hoặc deadlock; `ClassCircularityError` liên quan đến circularity trong cấu trúc class/interface theo JVM.

**Câu 2.** Vì sao track riêng `binaryName` trong một `ThreadLocal Set<String>` có thể chặn nhầm?

**Đáp án:** Hai loader khác nhau có thể hợp lệ cùng đi qua một binary name trong delegation; cần theo dõi cặp loader object identity + tên, và đánh giá đường request.

**Câu 3.** Vì sao ví dụ dọn `ACTIVE` trong `finally` chứ không ngay sau `next.loadClass`?

**Đáp án:** Vì downstream có thể ném exception. `finally` đảm bảo state in-progress được gỡ ngay cả khi không tìm thấy lớp hoặc xảy ra lỗi.

**Câu 4.** Nếu hai thread T1 và T2 đợi lock của nhau trong hai custom loader, một ThreadLocal guard có giải quyết được không?

**Đáp án:** Không. Hai thread có path riêng; cần thiết kế graph không có vòng, lock ordering và concurrency tests.

**Câu 5.** Với loader chỉ cần đổi nơi đọc bytecode, nên ưu tiên override phương thức nào?

**Đáp án:** `findClass(String)`, để giữ mặc định `loadClass` xử lý parent delegation, lớp đã nạp và locking.

**Câu 6.** Một `findClass` không tìm thấy bytecode local. Có nên gọi `this.loadClass(name)` để “thử lại” không?

**Đáp án:** Không cho cùng tên khi `findClass` đã được `loadClass` gọi sau khi parent fail; nó có thể tạo đệ quy. Nên báo `ClassNotFoundException` hoặc tuân theo một fallback khác được thiết kế tránh vòng.

**Câu 7.** Điều gì cần kiểm tra khi `jcmd Thread.print` cho thấy hai thread kẹt trong hai custom loader?

**Đáp án:** Khóa mỗi thread đang giữ, nơi chờ, class name, các cạnh delegation, callback, static initialization và liệu một request đã được forward quay lại loader trước qua thread khác hay không.

**Câu 8.** Vì sao chuyển mọi package sang child-first để “tránh gọi parent” không phải giải pháp tổng quát?

**Đáp án:** Có thể làm các loader tự định nghĩa bản riêng của API/SPI và gây xung đột type identity. Cần thiết kế namespace rõ và định nghĩa hướng ủy quyền có kiểm soát.

## 14. Checklist thiết kế và vận hành

- [ ] Biết loader nào **sở hữu** từng namespace và loader nào chỉ delegate.
- [ ] Parent chain thông thường và các **cạnh chuyển tiếp custom** đều được mô hình hóa, không chỉ nhìn `getParent()`.
- [ ] Có validation DAG hoặc nguyên tắc routing một chiều trước khi phục vụ request.
- [ ] Với router động, có visited guard theo `(loader identity, binary name)` và bảo đảm dọn state trong `finally`.
- [ ] Không áp dụng guard cùng-thread như giải pháp toàn diện cho deadlock xuyên thread.
- [ ] Không override `loadClass` khi override `findClass` đủ đáp ứng yêu cầu.
- [ ] Không gọi lại `loadClass(name)` từ `findClass(name)` cho cùng tên.
- [ ] Giữ khóa nạp, `findLoadedClass` và chính sách `defineClass` chính xác nếu phải override.
- [ ] Không dùng `catch (StackOverflowError)` làm phương án phát hiện chu trình.
- [ ] Có log đường delegation với loader identity, class name, thread/request ID nhưng không lộ thông tin nhạy cảm.
- [ ] Kiểm thử vòng 2/3 node, đường hợp lệ, class missing và nhiều thread tranh chấp.
- [ ] Có chiến lược cleanup loader, ThreadLocal và routing registry khi unload/redeploy.

## 15. Kết luận và tài liệu tham khảo

Để tránh gọi lặp vô hạn khi tùy chỉnh ClassLoader, giải pháp đầu tiên là **thiết kế đồ thị ủy quyền một chiều hoặc không có chu trình** cho mỗi namespace. Khi chính sách đủ phức tạp để phát sinh vòng runtime, dùng guard theo **(loader object identity, binary name)** trên đường xử lý và dọn state bằng `finally` nhằm fail fast. Tuy nhiên, guard này chủ yếu phát hiện **recursion trong cùng thread**; vòng chờ nhiều thread vẫn đòi hỏi kiểm soát graph và locks.

Cần tiếp tục phân biệt vòng delegation với `ClassCircularityError` và với vòng initialization, giữ quy tắc `loadClass`/`findClass`/`findLoadedClass` đúng chuẩn, và không coi lỗi class-not-found là lý do nạp tùy tiện class cùng tên từ nguồn khác.

Tài liệu chính thức:

- Java SE 17 `ClassLoader` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 `ThreadLocal` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html
- Java SE 17 `ClassCircularityError`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassCircularityError.html
- JVMS 17 §5.3, *Creation of Classes and Interfaces*: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- JLS 17 §12.4.2, *Detailed Initialization Procedure*: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2
