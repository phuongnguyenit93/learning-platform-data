# Nhận diện mutable collaborator làm phá vỡ thread safety trong Java

Một class có thể dùng `private`, `final` và `synchronized` đúng cú pháp nhưng vẫn **không thread-safe** vì nó phụ thuộc vào một đối tượng có thể thay đổi mà thread khác cũng giữ tham chiếu. Đối tượng phụ thuộc đó gọi là **collaborator**. Nếu collaborator có **mutable state** (trạng thái có thể thay đổi) và không được bảo vệ bởi cùng một giao thức đồng bộ, các giả định an toàn của class bên ngoài có thể bị phá vỡ.

Ví dụ thường gặp là một class có khóa bảo vệ `List` nhưng nhận `ArrayList` từ caller rồi lưu nguyên tham chiếu, hoặc trả thẳng list nội bộ qua getter. Caller có thể chỉnh list mà không lấy khóa của class. Khóa bên trong dù hoàn hảo cũng **không thể điều phối đường truy cập bên ngoài mà nó không kiểm soát**.

Bài này tập trung vào **Java concurrency nói chung**: object graph, aliasing, encapsulation, memory visibility, defensive copying, immutable snapshots, thread-safe collaborators và cách kiểm tra hợp đồng đồng bộ. Các cơ chế riêng của Spring nằm ngoài phạm vi.

## 1. “Mutable collaborator” là gì?

**Collaborator** là object mà một thành phần gọi hoặc dùng để thực hiện công việc: dependency truyền qua constructor/setter, một collection được lưu vào field, cache, formatter, callback, clock, client, repository, listener hoặc một object chứa những object khác. Collaborator có thể là thư viện Java, class tự viết hoặc API của hệ thống khác.

**Mutable collaborator** là collaborator có trạng thái nội bộ hoặc dữ liệu tham chiếu tới có thể thay đổi sau khi được chia sẻ. Ví dụ:

- `ArrayList`, `HashMap`, `HashSet` và phần tử mutable bên trong collection.
- `StringBuilder`, `StringBuffer`, `java.util.Date`, `Calendar`, `ByteBuffer`.
- `SimpleDateFormat` (có trạng thái định dạng và không an toàn để nhiều thread dùng đồng thời khi không đồng bộ).
- Một object cấu hình có setter, bộ đếm, cache, registry hoặc worker tự quản lý state.
- Một collaborator trả mutable data qua `getItems()`, `getConfig()`, `getBuffer()`, kể cả khi bản thân accessor được đồng bộ.
- Một callback hoặc listener lưu lại tham chiếu tới object mà component nghĩ mình sở hữu riêng.

Điểm nguy hiểm là **nhiều thread có thể tiếp cận cùng mutable object** và ít nhất một thread có thể thay đổi nó theo đường mà class chính không kiểm soát.

### Object graph và alias

```java
List<String> supplied = new ArrayList<>();
Registry registry = new Registry(supplied);
```

Nếu constructor `Registry` chỉ gán `this.entries = supplied`, thì `registry.entries` và `supplied` là **hai tham chiếu tới cùng một object**. Đây là *aliasing*, không phải hai bản sao độc lập. Thread bên ngoài vẫn có thể gọi `supplied.add(...)`, kể cả sau khi `registry` đã được công bố cho các thread khác.

Một trường `private final List<String> entries` không chặn điều đó: `private` chỉ hạn chế đường truy cập theo ngôn ngữ; `final` bảo đảm không gán lại **tham chiếu** qua field sau khi xây dựng, không làm nội dung `List` bất biến.

### Khi nào collaborator không gây vấn đề?

- Một collaborator được **thread-confined**: chỉ một thread sở hữu, không escape sang thread khác.
- Collaborator được thiết kế **bất biến thực sự**, đã được công bố an toàn, và không chứa nhánh object mutable bị lộ.
- Collaborator tự thread-safe theo **đúng operation cần dùng**, hoặc tất cả thread tham gia cùng cơ chế khóa/giao thức nhất quán.
- Class sở hữu **bản sao riêng** của dữ liệu nhận vào và chỉ phát hành immutable value/snapshot, nên caller không thể mutate state nội bộ qua alias.

Một mutable object chưa chắc có bug; cần xét **nó được chia sẻ với ai, đường nào có thể mutate, invariant nào đang được bảo vệ và có happens-before phù hợp không**.

## 2. Vì sao một class “đã khóa hết method” vẫn sai?

Xem class minh họa sau (snippet, chưa có `main`):

```java
import java.util.List;

class Registry {
    private final List<String> entries;

    Registry(List<String> supplied) {
        this.entries = supplied; // Lưu nguyên alias của caller
    }

    synchronized int size() {
        return entries.size();
    }

    synchronized void add(String value) {
        entries.add(value);
    }

    synchronized List<String> entries() {
        return entries; // Lộ tham chiếu nội bộ
    }
}
```

Mỗi lời gọi `size()`, `add()`, `entries()` sử dụng monitor của cùng instance `Registry`. Nhưng:

```java
List<String> callerList = new ArrayList<>();
Registry registry = new Registry(callerList);

callerList.add("ngoai-khoa");          // Đi vòng qua monitor Registry
registry.entries().clear();           // Getter trả thẳng list nội bộ
```

Đây cũng là snippet, cần import `java.util.ArrayList`, `java.util.List` và class `Registry` bên trên. Cả hai thay đổi đều **không lấy monitor của Registry**. `synchronized` trên getter chỉ bảo vệ khoảng thời gian tạo/trả reference; nó **không mang khóa theo reference** tới các lời gọi `add`, `clear` diễn ra sau này.

Một số hậu quả có thể xảy ra nếu các thread thực sự truy cập đồng thời không đồng bộ:

1. **Data race** trên trạng thái nội bộ của collection/element do không có quan hệ happens-before.
2. **Mất invariant**: class kỳ vọng số phần tử, tổng, thứ tự hoặc uniqueness chỉ thay đổi qua method được kiểm soát, nhưng collaborator bị sửa bên ngoài.
3. **Visibility sai**: thread giữ khóa class vẫn không được bảo đảm thấy cập nhật qua một đường không dùng chung khóa như một chu trình đồng bộ đúng.
4. **Exception hoặc dữ liệu không nhất quán**: khi iterate và bị sửa đồng thời có thể gặp `ConcurrentModificationException`, bỏ sót phần tử, hoặc nhận kết quả không định trước. Không dựa vào fail-fast iterator làm cơ chế bảo vệ: exception **không được bảo đảm** xảy ra mọi lần.
5. **Cấp quyền ngoài ý muốn**: caller có thể mutate trạng thái private bằng alias, ngay cả khi tất cả method public của class đã cấm hoặc kiểm tra thao tác đó.

**Quy tắc:** tính an toàn của một thành phần phụ thuộc vào **mọi đường truy cập đến cùng mutable state**, không chỉ những method nhìn thấy trong class chính.

## 3. Thí nghiệm Java 17: phá invariant dù owner đang giữ khóa

Ví dụ dưới dùng hai `CountDownLatch` để tạo lịch rõ ràng. Worker đang giữ monitor của object `UnsafeInventory` khi nó chờ main sửa trực tiếp danh sách `seed` mà constructor đã giữ nguyên alias. Sau đó worker quan sát danh sách đã đổi **trong chính critical section** của nó.

Ta chủ động đặt thứ tự hai lần đọc quanh lần sửa; chương trình chứng minh **khóa của Inventory không bảo vệ được đường sửa ngoài**, chứ không cần dựa vào một data race ngẫu nhiên.

Tạo `LeakyInventoryExample.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class LeakyInventoryExample {
    static class UnsafeInventory {
        private final List<String> items;

        UnsafeInventory(List<String> supplied) {
            this.items = supplied;
        }

        synchronized int countChangesWhileLocked(
                CountDownLatch entered, CountDownLatch externalChanged)
                throws InterruptedException {
            int before = items.size();
            entered.countDown();

            if (!externalChanged.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("External update timed out");
            }

            return items.size() - before;
        }

        synchronized int size() {
            return items.size();
        }

        synchronized List<String> getItems() {
            return items;
        }
    }

    public static void main(String[] args) throws Exception {
        List<String> seed = new ArrayList<>(List.of("A"));
        UnsafeInventory inventory = new UnsafeInventory(seed);
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch externalChanged = new CountDownLatch(1);
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<Integer> difference = pool.submit(
                    () -> inventory.countChangesWhileLocked(
                            entered, externalChanged));

            if (!entered.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not enter lock");
            }

            seed.add("B"); // Không hề lấy monitor của inventory
            externalChanged.countDown();

            System.out.println("changedWhileLocked="
                    + difference.get(5, TimeUnit.SECONDS));

            inventory.getItems().add("C"); // Alias bị lộ từ getter
            System.out.println("sizeAfterEscapedMutation="
                    + inventory.size());
        } finally {
            externalChanged.countDown();
            pool.shutdownNow();
        }
    }
}
```

Biên dịch/chạy bằng Java 17+:

```bash
javac LeakyInventoryExample.java
java LeakyInventoryExample
```

Stdout khi chương trình hoàn tất bình thường:

```text
changedWhileLocked=1
sizeAfterEscapedMutation=3
```

**Tại sao kết quả xác định?**

- Main ban đầu có một phần tử `"A"`; constructor lưu đúng object `seed`, không copy.
- Worker lấy monitor của `inventory`, đọc size `1` rồi báo `entered.countDown()`. Worker **chưa nhả monitor** vì đang chờ `externalChanged` ngay trong synchronized method.
- Main nhận tín hiệu `entered` rồi gọi `seed.add("B")` trực tiếp. Main không cần lấy monitor của `inventory`; kết quả size trở thành `2`.
- Main phát `externalChanged.countDown()`; worker chờ xong, đọc size `2` khi **vẫn đang giữ monitor** và trả `2 - 1 = 1`.
- Sau `Future.get`, main gọi getter (đã được synchronized) nhưng nhận reference nội bộ; rồi `add("C")` **sau khi getter đã nhả monitor**, size thành `3`.

Các latch thiết lập thứ tự đọc/sửa trong **thí nghiệm có kiểm soát**. Vì vậy không dùng kết quả này làm chứng cứ một data race không có happens-before đã thực sự xảy ra ở các bước đo; nó chứng minh lỗi **ownership/encapsulation**: code bên ngoài có thể sửa tài nguyên mà class tưởng đang độc quyền.

**Bài học chính:** bên trong method `synchronized` không có nghĩa tất cả collaborator được bảo vệ. Khóa chỉ phát huy khi **mọi actor thay đổi state đều tuân thủ cùng lock**. Chính đường truy cập trực tiếp qua `seed` và getter đã phá hợp đồng đó.

## 4. Hai cửa ngõ phổ biến: đầu vào và đầu ra

### 4.1. Constructor/setter giữ nguyên input mutable

```java
class UnsafeSettings {
    private final List<String> hosts;

    UnsafeSettings(List<String> hosts) {
        this.hosts = hosts; // Caller vẫn giữ reference
    }
}
```

Nếu caller đổi `hosts` sau khi tạo `UnsafeSettings`, state của object cũng đổi. Việc đánh dấu field `final` chỉ làm reference không thể được gán lại từ chính class; không hề sao chép cấu trúc hay phần tử.

**Cách xử lý:** khi component muốn sở hữu dữ liệu, sao chép input vào cấu trúc riêng tại ranh giới ownership. Nếu không cần mutate nội bộ, `List.copyOf(input)` cho một danh sách không sửa được và không chia sẻ **cấu trúc list** để caller thay đổi; nhưng lưu ý các phần tử vẫn có thể mutable. Nếu cần mutate nội bộ, dùng `new ArrayList<>(input)` (copy nông) và bảo vệ mọi lần truy cập nội bộ bằng một giao thức khóa phù hợp.

**Điều kiện của copy:** nguồn phải ổn định trong lúc sao chép hoặc caller phải phối hợp. Copy một `ArrayList` bị thread khác sửa **ngay trong lúc constructor đang copy** không tự an toàn. Thường cần contract “input không bị sửa trong lúc handoff”, hoặc snapshot được lấy dưới lock của owner nguồn.

### 4.2. Getter trả thẳng mutable object

```java
synchronized List<String> getEntries() {
    return internalEntries;
}
```

Đây là snippet, giả sử có field `internalEntries`. Getter được khóa **chỉ trong thời gian method thực thi**. Caller sau đó cầm reference và có thể `clear`, `add`, iterate hay chuyển reference sang thread khác.

**Cách xử lý:** cung cấp method operation có kiểm soát (`add`, `remove`, `getSnapshot`) thay vì cho phép mutate toàn bộ data structure. Khi trả danh sách chỉ đọc, dùng snapshot như `List.copyOf(internalEntries)` **khi đang giữ lock** (nếu phần tử bất biến). Trả một *live view* là một lựa chọn API khác, đòi hợp đồng đồng bộ riêng; đừng mặc định gọi nó là snapshot.

### 4.3. Setter và callback cũng làm lộ collaborator

Một getter không phải nơi duy nhất alias có thể escape:

- Setter nhận mutable object rồi giữ nguyên reference.
- Method đưa `this`, collection nội bộ, buffer hoặc mutable entry vào callback/listener bên ngoài; listener có thể giữ lại.
- Iterator, `Map.Entry`, sublist, view từ `Map.keySet()` / `values()` / `entrySet()` có thể liên kết tới collection nguồn.
- `Collections.unmodifiableList(backing)` cấm sửa **qua view**, nhưng owner vẫn có thể sửa `backing` và view phản ánh thay đổi: đó là *unmodifiable live view*, không nhất thiết là snapshot.
- `ByteBuffer.slice()` / `duplicate()` thường chia sẻ vùng dữ liệu backing với buffer gốc; các object wrapper khác nhau không chứng minh bộ nhớ dữ liệu độc lập.
- Closure/lambda hoặc asynchronous task capture tham chiếu mutable có thể kéo dài lifetime và đưa object sang thread khác.

Nên rà soát mọi ranh giới mà **reference** đi qua, không chỉ mọi lệnh `synchronized`.

## 5. Java 17: sửa bằng defensive copy và immutable snapshot

Một bản sửa trực tiếp: copy danh sách input khi tạo, mọi mutation nội bộ qua method có khóa, và getter tạo bản snapshot không sửa được. Ví dụ này dùng phần tử `String` bất biến, nên copy cấu trúc list là đủ cho phạm vi trạng thái minh họa.

Tạo `SafeInventoryExample.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class SafeInventoryExample {
    static class SafeInventory {
        private final List<String> items;

        SafeInventory(List<String> source) {
            this.items = new ArrayList<>(source);
        }

        synchronized void add(String item) {
            items.add(Objects.requireNonNull(item));
        }

        synchronized int size() {
            return items.size();
        }

        synchronized List<String> snapshot() {
            return List.copyOf(items);
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>(List.of("A"));
        SafeInventory inventory = new SafeInventory(input);

        input.add("B"); // Không thay đổi bản copy bên trong
        System.out.println("afterCallerMutation=" + inventory.size());

        List<String> oldSnapshot = inventory.snapshot();
        inventory.add("C");

        System.out.println("snapshotSize=" + oldSnapshot.size());
        System.out.println("currentSize=" + inventory.size());

        try {
            oldSnapshot.add("D");
            System.out.println("snapshotMutable=true");
        } catch (UnsupportedOperationException expected) {
            System.out.println("snapshotMutable=false");
        }
    }
}
```

Chạy:

```bash
javac SafeInventoryExample.java
java SafeInventoryExample
```

Stdout chính xác:

```text
afterCallerMutation=1
snapshotSize=1
currentSize=2
snapshotMutable=false
```

**Giải thích:**

- `new ArrayList<>(source)` tạo **cấu trúc list riêng** ngay tại constructor. Caller thêm `"B"` vào list ban đầu không còn sửa inventory.
- `synchronized` trên `add`, `size` và `snapshot` sử dụng **cùng monitor** để bảo vệ những thao tác trên state sở hữu riêng.
- `List.copyOf(items)` trả collection không hỗ trợ thay đổi cấu trúc qua reference được trả; khi inventory thêm `"C"`, snapshot cũ vẫn size `1`.
- Vì phần tử là `String` bất biến, caller không thể mutate element để làm đổi nội dung snapshot/inventory qua alias phần tử. Với phần tử là object mutable, cần bảo vệ thêm tầng phần tử.
- Nếu contract cho phép `null` trong list thì `List.copyOf` không phù hợp vì từ chối phần tử null; điều chỉnh representation hoặc validate input rõ ràng thay vì giả định mọi collection chấp nhận null.

**Không phải lúc nào cũng cần khóa:** nếu class chỉ lưu một immutable list được công bố an toàn, không cho update về sau và các phần tử cũng immutable, reader có thể đọc mà không cần khóa quanh từng lần truy cập. Ví dụ ở trên cố ý cho phép mutation qua `add` nên lựa chọn một monitor chung để dạy rõ ownership.

## 6. Bẫy lớn: defensive copy nông không bảo vệ phần tử mutable

`new ArrayList<>(source)` và `List.copyOf(source)` đều không tự *deep-copy* các object bên trong. Với một `List<MutableUser>`, cả list copy lẫn list gốc vẫn tham chiếu **cùng User instances**. Vì vậy một class có thể đã copy collection nhưng vẫn lộ collaborator ở tầng phần tử.

Tạo `ShallowCopyExample.java`:

```java
import java.util.List;

public class ShallowCopyExample {
    static class MutableUser {
        private String name;

        MutableUser(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }

        void rename(String name) {
            this.name = name;
        }
    }

    record UserView(String name) { }

    public static void main(String[] args) {
        MutableUser user = new MutableUser("An");
        List<MutableUser> copied = List.copyOf(List.of(user));

        user.rename("Binh");
        System.out.println("copiedElementName="
                + copied.get(0).name());

        List<UserView> valueSnapshot = copied.stream()
                .map(u -> new UserView(u.name()))
                .toList();

        user.rename("Chi");
        System.out.println("valueSnapshotName="
                + valueSnapshot.get(0).name());
        System.out.println("originalName=" + user.name());
    }
}
```

Chạy Java 17+:

```bash
javac ShallowCopyExample.java
java ShallowCopyExample
```

Stdout:

```text
copiedElementName=Binh
valueSnapshotName=Binh
originalName=Chi
```

List `copied` là **unmodifiable**, nhưng phần tử `MutableUser` có method `rename`. Khi sửa object `user`, `copied.get(0)` quan sát tên mới vì đây vẫn là **cùng instance**. Sau đó chương trình tạo `UserView` chứa `String` (bất biến), nên việc đổi tên `user` lần tiếp theo không làm đổi snapshot giá trị.

Đây là thí nghiệm tuần tự để giải thích alias; trong môi trường multi-thread thực tế, nếu một thread rename còn thread khác đọc tên không có đồng bộ, vấn đề visibility cũng phát sinh.

### Làm sao thiết kế owner thực sự an toàn khi element mutable?

- Tại ranh giới vào: nếu owner cần giữ mutable entity, tạo **bản sao độc lập của từng element**, hoặc chuyển thành immutable value object. Hợp đồng phải nói rõ có deep copy hay không.
- Trong owner: bảo vệ **mọi cập nhật và mọi snapshot** bằng cùng lock, hoặc tổ chức state thành immutable aggregate và thay reference theo cơ chế atomic.
- Tại ranh giới ra: chỉ trả **value snapshot** (ví dụ record chứa `String`, `int` và những value immutable) hoặc defensive copies không chia sẻ mutable child; đừng trả mutable entity nội bộ.
- Nếu record chứa `List<MutableUser>`, tên `record` không tự deep-freeze list và element. Record chỉ tạo field final và một số method tự sinh; cần defensive copy/validation trong constructor và accessor khi có mutable member.
- Copy càng sâu càng tốn CPU/memory; cân nhắc immutable model từ thiết kế, thay vì copy toàn bộ graph ở mọi request.

## 7. Đồng bộ đúng class nhưng sai lock identity

Giả sử một `Account` giữ một mutable collaborator `Ledger`. Account khóa `this`, nhưng code khác trực tiếp sửa Ledger hoặc khóa `ledger` thay vì `account`:

```java
class Account {
    private final Ledger ledger;

    Account(Ledger ledger) {
        this.ledger = ledger;
    }

    synchronized void debit(int amount) {
        ledger.debit(amount);
    }
}
```

Đây là snippet, `Ledger` chưa được định nghĩa; không phải chương trình độc lập. `synchronized` trên `Account.debit` chỉ chặn những caller cũng muốn sở hữu monitor **của cùng Account instance**. Nó **không buộc** code có reference tới `ledger` phải lấy monitor ấy. Hai `Account` khác nhau có thể cùng tham chiếu một `ledger` nhưng lấy **hai monitor khác nhau**. Vì vậy trạng thái Ledger vẫn có thể bị cập nhật đồng thời.

Ba cách giải, tùy ownership và hợp đồng:

1. **Account sở hữu Ledger độc quyền:** constructor nhận dữ liệu dạng value và tạo Ledger nội bộ; không phát hành reference Ledger, chỉ cung cấp operation/snapshot.
2. **Ledger được chia sẻ và tự thread-safe:** tất cả operation Ledger phải có contract atomicity/visibility phù hợp. Nhưng nếu nghiệp vụ cần “kiểm tra số dư rồi trừ”, phải bảo vệ **cả chuỗi**, không chỉ từng method đơn lẻ.
3. **Một lock/protocol chung cho mọi actor:** chỉ khi tất cả đường truy cập thật sự tuân thủ cùng lock có thể bảo vệ compound invariant. Truyền một lock object ra khắp hệ thống có chi phí thiết kế và nguy cơ deadlock; nếu quản lý khó, thiết kế ownership/encapsulation thường rõ ràng hơn.

### Lock order và gọi collaborator ngoài ý muốn

Nếu Account giữ lock A và gọi collaborator bên ngoài mà collaborator lại gọi ngược Account hoặc lấy lock B, một thread khác có thể giữ B rồi đợi A, tạo vòng chờ deadlock. Đặc biệt nguy hiểm khi gọi **user-supplied callback** hoặc I/O không có thời hạn trong critical section. Cố gắng tạo immutable event snapshot **bên trong** lock rồi gọi callback **sau khi nhả lock** nếu nghiệp vụ cho phép. Khi callback chạy ngoài lock, phải định nghĩa rõ **thứ tự event giữa nhiều thread** nếu consumer phụ thuộc thứ tự.

## 8. Thread-safe collaborator chưa đủ cho mọi invariant

Một collaborator được ghi trong tài liệu là “thread-safe” không có nghĩa toàn bộ chuỗi sử dụng nó đều nguyên tử.

### Ví dụ `ConcurrentHashMap`

```java
if (!cache.containsKey(key)) {
    cache.put(key, createValue());
}
```

Đây là snippet, giả sử `cache` là `ConcurrentHashMap<Key, Value>`. Từng operation `containsKey`, `put` có bảo đảm riêng. Tuy nhiên hai thread vẫn có thể cùng thấy key chưa tồn tại rồi đều `createValue()`; trạng thái cuối map có thể chỉ giữ một value nhưng **side effect tạo dữ liệu đã xảy ra hai lần**.

Có thể dùng `computeIfAbsent(key, mappingFunction)` hoặc `putIfAbsent` nếu semantics của chúng đáp ứng đúng nhu cầu. Mapping function của `ConcurrentHashMap.computeIfAbsent` cần ngắn, rõ ràng và tránh tự sửa map theo đường dẫn dễ gây deadlock/lỗi. Nếu `createValue()` gọi DB hoặc API bên ngoài có side effect, cần xem xét transaction/idempotency và failure/retry, không giả định một lời gọi map giải quyết toàn bộ.

### Ví dụ `Collections.synchronizedList`

`Collections.synchronizedList(list)` bảo vệ các method đơn lẻ của wrapper bằng monitor tương ứng. Nhưng:

```java
List<String> syncList =
        java.util.Collections.synchronizedList(new ArrayList<>());

synchronized (syncList) {
    for (String item : syncList) {
        System.out.println(item);
    }
}
```

Đây là snippet cần import `java.util.List`, `java.util.ArrayList`; nó minh họa pattern theo tài liệu JDK: **khi duyệt collection bằng iterator, caller phải đồng bộ thủ công trên đúng wrapper list** để tránh mutation xen kẽ qua wrapper trong lúc iterate. Nếu ai đó còn giữ **backing list gốc** và sửa trực tiếp ngoài wrapper, vòng khóa này vẫn bị bypass. Tốt nhất là không để backing mutable reference có thể bị dùng ngoài hợp đồng.

### Ví dụ thread-safe operation nhưng mutable value

`ConcurrentHashMap<String, MutableUser>` an toàn ở cấp thao tác map, nhưng không khiến `MutableUser.rename(...)` thread-safe. Lấy reference từ map và sửa object không đồng bộ vẫn có thể race. Concurrent collection chỉ bảo vệ phạm vi mà API cam kết; mọi **value object** và invariant liên quan phải được xem xét riêng.

## 9. Visibility và safe publication không thay thế ownership

Java Memory Model cung cấp các quan hệ *happens-before* (HB). Ví dụ:

- Nhả monitor happens-before lần lấy monitor **tiếp theo trên cùng monitor**.
- Ghi vào `volatile` field happens-before lần đọc sau của chính field đó theo quy tắc JMM.
- Hành động trước `Thread.start()` happens-before hành động trong thread được khởi động.
- Hành động trong worker happens-before caller quan sát thread kết thúc qua `Thread.join()` phù hợp.
- Các tiện ích `java.util.concurrent` có memory-consistency effects theo hợp đồng riêng.

Các cơ chế ấy giúp dữ liệu được công bố và quan sát theo thứ tự đã chỉ định. Nhưng **safe publication chỉ giải quyết việc chuyển giao trạng thái đã xây dựng**, không bảo vệ các đợt mutation về sau nếu nhiều thread còn giữ alias mutable.

Ví dụ:

```java
class Holder {
    volatile List<String> values;
}
```

Gán một reference `ArrayList` vào `volatile values` giúp các thread khác thấy reference mới theo semantics của volatile; **không biến `values.add` hoặc `values.clear` thành thread-safe**, và không bảo đảm iteration đang diễn ra không bị sửa xen ngang. Nếu muốn thay một snapshot bất biến, writer tạo object list immutable mới rồi gán `volatile values = List.copyOf(...)`, còn reader lấy **một reference** và chỉ đọc snapshot đó. Nhưng vẫn phải bảo đảm element immutable hoặc copy đúng mức, và nhiều writer muốn hợp nhất thay đổi có thể cần CAS/lock để không mất cập nhật.

### `final` field đảm bảo gì?

Một properly constructed object với `final` fields có những bảo đảm riêng về initialization safety. Tuy nhiên:

- `final` **không tạo mutual exclusion** cho mọi thao tác sau constructor.
- `final List<T>` không làm mọi object `T` bất biến.
- Nếu `this` escape trong constructor (đăng ký listener hoặc chạy thread quá sớm), các giả định publication có thể bị phá vỡ.
- Nếu constructor nhận mutable collaborator từ thread khác, caller vẫn có thể mutate sau đó; `final` field chỉ khóa reference, không khóa quyền sở hữu object.

**Câu hỏi đúng:** không chỉ “reference được publish thế nào?”, mà còn “ai được phép mutate **toàn bộ graph có thể truy cập từ reference** sau publication?”.

## 10. Các collaborator dễ bị bỏ qua trong review

| Collaborator | Vì sao có thể mutable/nguy hiểm | Cách xử lý thường hợp lý |
| --- | --- | --- |
| `List`/`Map` truyền qua constructor | Caller giữ alias, sửa không theo khóa owner | Copy cấu trúc, xác định quyền sở hữu |
| Phần tử mutable trong immutable list | Cấu trúc cố định, object element vẫn thay đổi | Immutable value/deep copy theo nhu cầu |
| Getter trả map/list nội bộ | Escape reference sau khi getter đã unlock | Trả snapshot hoặc API operation |
| `Collections.unmodifiableList(backing)` | Read-only *view* vẫn đổi khi backing đổi | `List.copyOf` hoặc copy dưới lock để có snapshot |
| `Map.keySet()`, `entrySet()`, `subList()` | View thường liên kết tới backing collection | Trả snapshot riêng nếu cần cách ly |
| `Date`, `Calendar` | Thời điểm/cấu hình có thể thay đổi | Ưu tiên `java.time` immutable types như `Instant`, `LocalDate` |
| `SimpleDateFormat` | Chứa mutable formatting state | `DateTimeFormatter` (immutable, thread-safe theo hợp đồng API) |
| `StringBuilder` | Buffer có thể mutate và không tự thread-safe | Per-task builder hoặc tạo bản String immutable |
| `StringBuffer` | Method có synchronized nhưng chuỗi nhiều bước chưa atomic | Giữ đúng lock quanh cả workflow hoặc confinement |
| `ByteBuffer`/backing array | Slice/duplicate có thể chia sẻ bytes | Copy data khi cần ownership riêng, áp giao thức khóa |
| Listener/callback | Có thể lưu reference và mutate về sau, hoặc reentrant | Truyền immutable event, xác định lock/order/lifecycle |
| Cache có mutable value | Cache thread-safe chỉ bảo vệ map operation | Value immutable hoặc bảo vệ chính value |
| `ThreadLocal<T>` chứa mutable object | Hạn chế chia sẻ giữa thread, nhưng worker pool tái sử dụng thread | Xóa bằng `remove()` đúng vòng đời; không truyền value sang thread khác |
| Một mutable config object | Setter thay đổi cấu hình khi task đang đọc | Immutable configuration snapshot, volatile/atomic publish |
| API client/session mutable | Hợp đồng thread safety có thể bị giới hạn theo method hoặc instance | Đọc docs, mỗi task một client/session nếu cần, giới hạn lifecycle |

**Không mặc định mỗi tên class nói lên thread-safety.** Một thư viện có thể cho phép gọi một số operation đồng thời nhưng không bảo đảm kết quả của một chuỗi liên quan nhiều call, hoặc đòi không mutate input collection trong thời gian operation.

## 11. Phương pháp nhận diện mutable collaborator trong codebase

Thay vì chỉ tìm từ khóa `synchronized`, hãy vẽ một **bản đồ ownership của mutable state**.

### Bước 1: Tìm tất cả mutable state trực tiếp và gián tiếp

Các field không `final`, collection, cache, cấu hình, bộ đệm, listener lists, object có setter và mutable value objects đều là ứng viên. Với mỗi field reference, xem **nội dung object** có thể thay đổi không, bao gồm children ở nhiều tầng.

### Bước 2: Truy ngược ai tạo/giữ reference

Hỏi: tham chiếu đến từ constructor, setter, factory, một singleton static, getter thư viện hay kết quả cache? Caller còn cầm reference sau lúc trao cho component không? Nếu nhận object từ ngoài mà không copy/ownership transfer rõ ràng, phải coi khả năng alias vẫn còn.

### Bước 3: Tìm mọi đường escape

Rà soát return values, callback arguments, listener registrations, getters, iterators/views, lambdas/async tasks, method tham số `Consumer`/`Function`, object được cho vào shared collection, và cả việc trả `this`. Một reference nội bộ thoát khỏi class có thể được sử dụng ở thread khác mà class không thấy.

### Bước 4: Đọc hợp đồng thread-safety của collaborator

Các câu cần biết:

- Thread-safe **toàn bộ instance** hay chỉ một số method?
- Mutating operation có linearizable/atomic không? Những thao tác ghép nào không được bảo đảm?
- Có yêu cầu caller đồng bộ khi iterate không?
- API trả **copy, snapshot, live view hay alias**?
- Có được chia sẻ instance giữa nhiều thread hay chỉ thread confinement?
- Có yêu cầu input không bị mutate trong lúc method chạy?
- Nếu callback được gọi khi giữ lock, có thể reenter component không?

Không có tài liệu, không nên giả định mutable collaborator tự an toàn.

### Bước 5: Liệt kê invariant và ranh giới bảo vệ

Ví dụ “size không bao giờ vượt capacity”, “số dư không âm”, “một key tạo một lần”, “các field thuộc cùng version”. Xác định **toàn bộ read–check–write** nằm trong một operation atomic/critical section hay bị chia thành nhiều lời gọi có thể xen kẽ. Chỉ khóa `add` không đủ nếu `canAdd` được kiểm tra riêng rồi mới gọi `add`.

### Bước 6: Kiểm tra lock identity và happens-before

Cùng một object mutable được truy cập thông qua nhiều wrapper/owner khác nhau? Chúng có dùng **cùng khóa** không? Có đoạn read không khóa, direct access từ caller hoặc đọc qua view? Có volatile/safe publication đảm bảo visibility đúng cách không? Không suy ra thread-safe chỉ từ việc “tôi thấy một lock ở đâu đó”.

### Bước 7: Dựng test ép đường bypass

Test có thể giữ khóa owner ở thread A rồi yêu cầu thread B chỉnh collaborator qua alias. Nếu B vẫn thay đổi được state, khóa owner không kiểm soát tất cả đường sửa. Dùng `CountDownLatch`/`CyclicBarrier` để điều phối, timeout để test không treo, `Future.get` để đưa lỗi worker về test runner. Test không thay thế phân tích Java Memory Model nhưng minh họa chính xác lỗ hổng thiết kế.

### Bước 8: Đánh giá cách sửa và chi phí

Có thể chuyển sang immutable value, defensive copy, interface chỉ đọc, thread confinement, message passing, hoặc một synchronized/atomic operation bao trọn invariant. Xem thêm chi phí copy lớn, memory, GC, throughput, lock contention, deadlock và thứ tự callback. Đừng chỉ sửa một getter rồi quên constructor alias.

## 12. Hai lỗi “sửa một nửa” thường gặp

### 12.1. Chỉ bọc `Collections.unmodifiableList`

```java
List<String> backing = new ArrayList<>(List.of("A"));
List<String> view = java.util.Collections.unmodifiableList(backing);

backing.add("B");
// view.size() bây giờ bằng 2.
```

Đây là snippet, cần import `java.util.List` và `java.util.ArrayList`. Caller không gọi `view.add` được nhưng vẫn có thể gọi `backing.add`. Nếu muốn snapshot, tạo **một cấu trúc giá trị độc lập** từ backing tại thời điểm mong muốn, ví dụ `List.copyOf(backing)` khi nguồn ổn định hoặc được bảo vệ thích hợp.

### 12.2. Chỉ dùng `volatile` trên reference

```java
private volatile List<String> shared = new ArrayList<>();
```

Đây là khai báo field trong một class. `volatile` hữu ích cho **công bố/thay reference**, nhưng không khiến các method nội bộ của `ArrayList` an toàn khi nhiều thread mutate đồng thời. Tăng/giảm visibility không tự tạo mutual exclusion. Nếu muốn copy-on-write thủ công, writer có thể copy trạng thái cũ, sửa bản copy rồi publish immutable snapshot mới; với **nhiều writer**, cần khóa chung hoặc CAS loop để tránh một writer ghi đè snapshot của writer khác.

## 13. Immutable snapshot và publish theo version

Một thiết kế có nhiều reader, ít writer có thể giữ state thành immutable record và công bố toàn bộ bằng một reference volatile:

```java
import java.util.List;

record InventoryView(int version, List<String> items) {
    InventoryView {
        items = List.copyOf(items);
    }
}

class SnapshotInventory {
    private volatile InventoryView current =
            new InventoryView(0, List.of());

    InventoryView read() {
        return current;
    }

    synchronized void add(String item) {
        InventoryView old = current;
        List<String> next = new java.util.ArrayList<>(old.items());
        next.add(item);
        current = new InventoryView(old.version() + 1, next);
    }
}
```

Đây là **snippet có thể biên dịch nếu đặt trong file phù hợp**, nhưng chưa có `main`. Record constructor ép copy cấu trúc list vào một immutable representation (các phần tử ở đây là `String`). Reader chỉ cần gọi `read()` **một lần** để lấy cùng version và contents; writer đồng bộ khi thực hiện read–modify–publish, tránh lost update giữa nhiều writer. Khi ghi `current` volatile, state được công bố theo hợp đồng JMM. Khi snapshot đã được công bố, reader không cần nắm khóa writer để đọc snapshot đó.

Nếu dữ liệu lớn và cập nhật liên tục, copy toàn bộ `List` mỗi lần thêm có thể tốn memory/CPU; cân nhắc persistent data structures, phân vùng ownership hoặc cơ chế đồng bộ khác. Nếu phần tử mutable, copy list vẫn là nông: cần thiết kế immutable element hoặc deep copy theo hợp đồng.

## 14. Gọi callback từ một object thread-safe

Một component có thể sở hữu state an toàn nhưng gọi listener theo cách làm lộ nó:

```java
synchronized void notifyListener(Consumer<List<String>> listener) {
    listener.accept(internalItems);
}
```

Đây là snippet, giả định import `java.util.function.Consumer`, `java.util.List` và có field `internalItems`. Listener do caller cung cấp có thể giữ reference để dùng sau, hoặc ngay trong callback gọi `clear()`. Khóa của method không giới hạn hành động của listener sau khi method trả về; còn callback reentrant hoặc chặn lâu trong lúc owner giữ monitor có thể gây latency và deadlock.

Pattern an toàn hơn khi hợp với nghiệp vụ:

```java
void publish(Consumer<List<String>> listener) {
    List<String> snapshot;
    synchronized (this) {
        snapshot = List.copyOf(internalItems);
    }
    listener.accept(snapshot);
}
```

Đây cũng là snippet, giả định phần tử immutable và list chỉ cần snapshot. Listener có thể giữ reference `snapshot` mà không làm thay đổi state nội bộ; đồng thời owner đã nhả monitor trước khi gọi code bên ngoài. Nếu nhiều thread publish các snapshot khác nhau, **thứ tự callback hoàn thành không mặc nhiên là thứ tự state được cập nhật**; nếu consumer yêu cầu thứ tự, cần queue/sequence number hoặc giao thức serialization rõ ràng.

## 15. Test gì để xác nhận sửa đúng?

**Nhóm kiểm tra ownership (có thể chạy tuần tự):**

1. Tạo input mutable, truyền vào constructor, thay đổi input. State owner có đổi ngoài ý muốn không?
2. Lấy getter/snapshot, thử mutate collection (nếu API nói immutable) và mutate phần tử. State owner có đổi không?
3. Lấy hai snapshot tại hai thời điểm: snapshot cũ có bị thay đổi sau một update mới không?
4. Thử view từ `subList`, `keySet`, `entrySet`, buffer slice, callback reference; đường nào còn trỏ về backing state?
5. Nếu input được clone, thử cấu trúc lồng nhiều tầng; copy nông có phù hợp hợp đồng không?

**Nhóm kiểm tra concurrency:**

1. Dùng hai thread và latch để ép đường sửa ngoài xảy ra khi owner giữ monitor; quan sát invariant. Ví dụ `LeakyInventoryExample` đã kiểm tra đúng loại bypass này.
2. Tạo stress test nhiều writer/reader trên **operation thực** và assert invariant sau khi các worker hoàn thành (có timeout và fail-fast reporting).
3. Đừng dùng `Thread.sleep` để “chắc chắn” gặp race; dùng checkpoint có điều kiện rõ.
4. Với shared map/list, thử compound operation (check–then–act), iteration khi mutation và mutable element, không chỉ thử `add`/`get` riêng.
5. Một test qua nhiều lần không chứng minh không có data race; cần code review theo HB, lock ownership và hợp đồng API.
6. Nếu dùng virtual thread (Java 21+) thay platform thread, các quy tắc về mutable collaborator, publication và atomicity **không thay đổi**.

Cần lưu ý thêm: test orchestration có thể tạo **happens-before mới** và che một số lỗi visibility. Nó rất tốt để chứng minh đường bypass và lỗi logic đã biết, nhưng không đủ để chứng minh tất cả interleaving/JMM outcome. Các vấn đề memory ordering tinh vi có thể cần stress/litmus test chuyên biệt.

## 16. Checklist nhận diện nhanh khi đọc code

Đối với mỗi class tuyên bố “thread-safe”, hãy kiểm tra:

- **Object graph:** class chỉ có primitive/immutable values, hay nắm mutable collaborator?
- **Nguồn tham chiếu:** collaborator được tự tạo độc quyền hay truyền vào từ ngoài và caller còn giữ alias?
- **Khả năng escape:** getter, callback, iterator, live view, element, listener hoặc async task có trả/giữ tham chiếu mutable không?
- **Phạm vi copy:** copy cấu trúc hay copy cả phần tử/child objects? Có cần deep copy không?
- **Quy tắc khóa:** mọi đường đọc/ghi có dùng **đúng cùng lock identity**, hoặc collaborator tự bảo vệ đủ phạm vi operation?
- **Hợp đồng compound operation:** check–then–act, read–modify–write, invariant nhiều field có thể bị xen ngang không?
- **Visibility:** state được công bố bằng HB nào? `final`/`volatile` có đang bị ngộ nhận là mutex không?
- **Thread-safe collection:** bản thân value/element có mutable và phải đồng bộ riêng không?
- **Callback:** có gọi code bên ngoài khi giữ khóa? Có truyền reference live/nhận side effect bất ngờ không?
- **Kiểm thử:** đã sửa cả đường constructor lẫn đường getter chưa? Test có chứng minh snapshot không bị ảnh hưởng khi caller sửa input/element không?

## 17. Những ngộ nhận cần tránh

| Ngộ nhận | Thực tế |
| --- | --- |
| “Tất cả method đều `synchronized`, vậy class an toàn.” | Nếu mutable collaborator bị lộ hoặc được sửa qua alias ngoài monitor, lock không kiểm soát được toàn bộ state. |
| “Field `private final` là bất biến.” | Chỉ reference không được gán lại; object được tham chiếu vẫn có thể mutable. |
| “Getter `synchronized` trả list là thread-safe.” | Khóa chỉ giữ trong getter; caller dùng reference sau khi getter return không được khóa. |
| “`List.copyOf` copy cả element.” | Chỉ tạo cấu trúc unmodifiable; element mutable vẫn được chia sẻ. |
| “`Collections.unmodifiableList` là snapshot.” | Thường là live view của backing list; backing vẫn có thể thay đổi. |
| “`ConcurrentHashMap` bảo vệ luôn giá trị của map.” | Nó không làm các value object mutable trở nên thread-safe. |
| “Collaboration chỉ là method call.” | Truyền và lưu **reference** cũng trao khả năng truy cập mutable state. |
| “Safe publication giải quyết mọi truy cập về sau.” | Nó bảo đảm handoff thích hợp; mutation sau đó vẫn cần giao thức đồng bộ. |
| “Có `volatile List` thì `add/clear` đã an toàn.” | Volatile reference không tạo mutual exclusion cho collection operations. |
| “Lock ở wrapper nào cũng được.” | Các actor phải dùng đúng cùng lock, hoặc API collaborator có bảo đảm riêng đủ mạnh. |
| “Chỉ cần viết test concurrent vài lần.” | Test có thể bỏ sót lịch nguy hiểm; ownership và happens-before vẫn phải được chứng minh. |
| “Một immutable record luôn deep-immutable.” | Record chứa mutable references cần thiết kế defensive copy/immutable children phù hợp. |

## 18. Câu hỏi tự kiểm tra

**1. Vì sao `private final ArrayList<String> list` không bảo đảm thread-safety?** Vì `final` không cấm thay đổi nội dung list. Nếu reference được chia sẻ, nhiều thread vẫn có thể mutate; khóa và ownership vẫn cần rõ ràng.

**2. Constructor dùng `new ArrayList<>(input)`, nhưng element là `MutableUser`. Đã cách ly hoàn toàn chưa?** Chưa. Copy cấu trúc list vẫn chia sẻ reference tới từng `MutableUser`. Cần immutable element, deep copy hoặc cơ chế đồng bộ đối với element.

**3. Một getter đồng bộ trả `List` nội bộ. Caller có cần đồng bộ khi gọi `list.add` không?** Getter đã nhả monitor khi trả về; caller có thể mutate không theo khóa và phá invariant. Nên tránh lộ reference và cung cấp operation/snapshot với contract rõ.

**4. Owner khóa `this`, collaborator tự khóa bằng monitor khác. Có an toàn không?** Chỉ khi contract của collaborator và mọi compound invariant đều được bảo vệ phù hợp. Hai monitor khác nhau tự chúng không tạo mutual exclusion chung đối với một state cần cập nhật nguyên tử.

**5. `List.copyOf` có an toàn khi input bị một thread khác sửa ngay lúc copy không?** Không mặc nhiên. Cần hợp đồng để input không bị concurrent modification hoặc snapshot dưới cơ chế đồng bộ thích hợp.

**6. Nếu `ConcurrentHashMap` thread-safe, `map.get(k).setName(...)` có thread-safe không?** Không thể kết luận. `setName` tác động lên value mutable; phải xét thread-safety riêng của value.

**7. Dùng `volatile` cho collaborator field có sửa được race trên mutable list không?** Không. Volatile đảm bảo publication/reference visibility, không bảo vệ in-place mutation của list.

**8. Vì sao ví dụ `LeakyInventoryExample` có thể chứng minh lỗi dù dùng latch tạo happens-before?** Vì điều cần chứng minh là **main vẫn sửa được state qua alias khi owner đang giữ monitor**. Latch kiểm soát thứ tự, và kết quả cho thấy việc khóa owner không tạo quyền sở hữu độc quyền với tài nguyên bị lộ.

**9. Khi nào snapshot list đủ, khi nào cần deep copy?** Snapshot list đủ khi elements immutable và invariant chỉ phụ thuộc cấu trúc. Nếu elements mutable, phải xem điều kiện sử dụng và tạo immutable value/deep copy cho phần dữ liệu cần cách ly.

**10. Vì sao nên gọi callback bên ngoài lock?** Callback có thể chạy lâu, reentrant, lấy khóa khác hoặc lưu lại reference. Khi khả thi, tạo immutable event dưới lock rồi thông báo ngoài lock; nếu cần thứ tự event, bổ sung cơ chế riêng.

**Nguyên tắc nhớ lâu:** *Thread safety là thuộc tính của toàn bộ giao thức truy cập **cùng trạng thái mutable**, kể cả mọi collaborator và alias có thể chạm vào nó.* Một field `final` hay một method `synchronized` chỉ bảo vệ phần mà chúng thật sự kiểm soát. Xác định ownership, ngăn reference mutable escape, sao chép/công bố immutable values khi phù hợp và bảo vệ compound invariant bằng cùng cơ chế đồng bộ.