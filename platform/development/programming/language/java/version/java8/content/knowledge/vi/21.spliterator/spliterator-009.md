# Late-binding, fail-fast và nguồn đồng thời trong Spliterator (Java 8)

> **Phạm vi:** `java.util.Spliterator`, thời điểm liên kết với nguồn (*binding*), phát hiện thay đổi cấu trúc (*fail-fast*) và cách duyệt các nguồn được thiết kế cho truy cập đồng thời (*concurrent sources*). Các khái niệm và API sau đây xuất hiện từ Java 8 và **vẫn còn áp dụng trên JDK hiện đại**. Cần đọc theo đúng hợp đồng của từng loại nguồn; không dựa vào kết quả “chạy thử thấy đúng” của một tình huống đua dữ liệu.

## 1. Mục tiêu của bài

Sau bài này, bạn có thể:

1. Giải thích vì sao `Spliterator` có hai nhiệm vụ: **traversal** (duyệt) và **partitioning** (chia nguồn) phục vụ Stream/parallel Stream.
2. Phân biệt **late-binding** với early-binding, nêu đúng các hành động có thể khiến Spliterator bắt đầu gắn với nguồn.
3. Hiểu đúng **fail-fast là cơ chế phát hiện lỗi theo best-effort**, không phải một hợp đồng đồng bộ hóa hay bảo đảm ném exception.
4. So sánh `ArrayList`, `CopyOnWriteArrayList` và `ConcurrentHashMap` về thời điểm chụp dữ liệu, khả năng thay đổi nguồn, tính nhất quán và các characteristic.
5. Chọn được cách duyệt an toàn theo yêu cầu: dữ liệu **ổn định và có thứ tự**, **snapshot**, hoặc **được phép thay đổi đồng thời**.
6. Viết kiểm thử không phụ thuộc thứ tự/số lượng phần tử được quan sát khi concurrent update đang diễn ra.

## 2. Spliterator là gì, khác Iterator ở điểm nào?

`Spliterator<T>` là giao diện duyệt phần tử được thiết kế thêm khả năng **chia việc**. Tên của nó ghép từ *split* và *iterator*. Java Stream có thể dùng Spliterator của nguồn để chia công việc thành các phần cho nhiều worker.

Ba phương thức cơ bản:

```java
boolean tryAdvance(Consumer<? super T> action);

void forEachRemaining(Consumer<? super T> action);

Spliterator<T> trySplit();
```

- `tryAdvance(action)` cố gắng chuyển **một** phần tử còn lại cho action, trả `true` khi có phần tử, `false` khi hết.
- `forEachRemaining(action)` duyệt các phần tử còn lại; có thể tận dụng cách duyệt nhanh hơn kiểm tra từng bước một.
- `trySplit()` cố tách một phần nguồn thành Spliterator mới để xử lý độc lập; có thể trả `null` nếu không thể/không nên chia.

Ví dụ minh họa:

```java
List<Integer> input = Arrays.asList(10, 20, 30, 40);
Spliterator<Integer> remainder = input.spliterator();
Spliterator<Integer> prefix = remainder.trySplit();

List<Integer> result = new ArrayList<>();
if (prefix != null) {
    prefix.forEachRemaining(result::add);
}
remainder.forEachRemaining(result::add);
// Khi nguồn ORDERED, split trả một strict prefix nếu split thành công.
// result chứa đủ 4 phần tử đúng encounter order trong ví dụ này.
```

Không phải Spliterator nào cũng chia được đều; `trySplit()` được phép trả `null`. Một Spliterator thường chỉ được dùng cho **một phép duyệt/tính toán**: đừng mong gọi lại sau khi đã tiêu thụ mà nhận lại dữ liệu ban đầu.

**Quan trọng:** Spliterator nhìn chung **không được bảo đảm thread-safe với chính đối tượng Spliterator đó**. Một chương trình song song nên giao mỗi phần được tách cho một worker tại một thời điểm; không cho hai thread đồng thời gọi `tryAdvance`/`trySplit` trên cùng một instance nếu không có hợp đồng riêng.

## 3. Binding: Spliterator gắn với nguồn vào lúc nào?

**Binding** là thời điểm Spliterator xác định phạm vi/phần tử của nguồn mà nó sẽ duyệt (theo chính sách của implementation). Không đồng nghĩa với sao chép toàn bộ dữ liệu.

### 3.1. Late-binding

Một Spliterator **late-binding** trì hoãn việc gắn với nguồn đến **một trong các thời điểm**:

- bắt đầu duyệt, ví dụ `tryAdvance` hoặc `forEachRemaining`;
- lần đầu tách bằng `trySplit`;
- lần đầu truy vấn **ước lượng số phần tử**, ví dụ `estimateSize()` hoặc phương thức có thể dựa trên ước lượng đó.

Trước khi binding, những thay đổi hợp lệ ở nguồn có thể được phản ánh trong phép duyệt tiếp theo. Sau khi đã binding, thay đổi cấu trúc đối với nguồn không-concurrent thường trở thành **structural interference**, có thể dẫn tới `ConcurrentModificationException` hoặc kết quả không được bảo đảm.

Ví dụ đặc trưng: **`ArrayList.spliterator()` là late-binding và fail-fast** theo JavaDoc.

```java
List<String> values = new ArrayList<>(Arrays.asList("A", "B"));

Spliterator<String> spliterator = values.spliterator();
values.add("C"); // Sửa nguồn TRƯỚC lần duyệt/split/ước lượng size.

List<String> seen = new ArrayList<>();
spliterator.forEachRemaining(seen::add);

// Với ArrayList: seen = [A, B, C].
```

Sửa nguồn **trước khi bắt đầu binding** ở ví dụ trên là lý do `C` được thấy. Không được lấy kết quả này để suy ra có thể sửa `ArrayList` **trong khi** đang duyệt.

### 3.2. Khi nào việc tưởng là “chưa duyệt” đã có thể bind?

`estimateSize()` không chỉ là phép xem metadata vô hại cho mọi Spliterator late-binding. Tài liệu `Spliterator` quy định **truy vấn ước lượng kích thước đầu tiên** có thể chính là thời điểm binding.

```java
List<String> values = new ArrayList<>(Arrays.asList("A", "B"));
Spliterator<String> spliterator = values.spliterator();

long size = spliterator.estimateSize(); // Có thể chốt thời điểm binding.
// Đừng thêm/bớt phần tử rồi mong spliterator phản ánh danh sách mới.
```

Với `ArrayList`, câu lệnh `estimateSize` lấy fence/kích thước cần thiết; nếu sau đó `values.add("C")` rồi duyệt tiếp, đó là thay đổi cấu trúc sau binding. **Không viết test kỳ vọng duyệt đủ 3 phần tử** trong trường hợp này.

Không nên định nghĩa một danh sách phương thức binding duy nhất cho mọi Spliterator: những implementation không late-binding có chính sách khác; hãy đọc JavaDoc của **nguồn cụ thể**.

### 3.3. Early-binding / không late-binding

Spliterator **không late-binding** liên kết nguồn khi được tạo hoặc trong lần gọi phương thức đầu tiên, tùy hợp đồng. Nó có thể không phản ánh các thay đổi được thực hiện giữa lúc tạo Spliterator và lúc bắt đầu duyệt.

Hai ví dụ khác nhau cần phân biệt:

- `CopyOnWriteArrayList.spliterator()` cung cấp **snapshot tại lúc tạo Spliterator**. Đây không phải live view của các cập nhật sau đó.
- Các factory trong `Spliterators` nhận **Iterator đã tạo trước**, chẳng hạn `Spliterators.spliterator(iterator, size, flags)`, được mô tả là **không late-binding**. Iterator có thể tự mang chính sách fail-fast riêng.

**Không đánh đồng early-binding với fail-fast**: hai khái niệm độc lập. Early-binding nói về **lúc xác lập nguồn**, còn fail-fast nói về **khả năng phát hiện thay đổi cấu trúc**.

## 4. Fail-fast: phát hiện lỗi chứ không bảo vệ dữ liệu

Một Spliterator **fail-fast** cố gắng nhận biết nguồn đã bị **structurally modified** sau thời điểm binding và ném `ConcurrentModificationException`.

Với `ArrayList`, thay đổi cấu trúc thường là `add`, `remove`, các thao tác thay kích thước/cấu trúc. Việc `set(index, value)` thông thường không phải thay đổi cấu trúc, nhưng vẫn không nên cho các thread đua nhau sửa nội dung phần tử mà không có đồng bộ hóa.

### 4.1. Vì sao gọi là *best-effort*?

- Cơ chế phát hiện phụ thuộc implementation và không thể biến mọi cuộc đua dữ liệu không đồng bộ thành exception xác định.
- `forEachRemaining` có thể kiểm tra thay đổi cấu trúc **sau khi đã gọi action trên nhiều phần tử** thay vì kiểm tra sau từng phần tử.
- Có thể quan sát exception, không có exception, hoặc những kết quả không mong muốn khi chương trình vi phạm quy tắc không can thiệp nguồn.
- `ConcurrentModificationException` **không thay thế lock, snapshot, dữ liệu concurrent hoặc các hàng rào bộ nhớ cần thiết**.

Bởi vậy, câu sau là **sai**: “Nếu chạy `stream().forEach(...)` mà không thấy `ConcurrentModificationException` thì chắc chắn không có lỗi đồng thời.”

### 4.2. Thử nghiệm minh họa có chủ đích gây interference

Đoạn sau **chỉ dùng để quan sát trong môi trường thử nghiệm**, không phải mẫu xử lý nguồn trong ứng dụng:

```java
List<String> values = new ArrayList<>(Arrays.asList("A", "B"));
Spliterator<String> sp = values.spliterator();

sp.estimateSize(); // Bắt đầu binding với ArrayList.
values.add("C");   // Sửa cấu trúc sau binding: KHÔNG HỢP LỆ để dựa vào kết quả.

try {
    sp.forEachRemaining(s -> {
        // Chỉ quan sát; không thực hiện side effect nghiệp vụ.
    });
    System.out.println("Không quan sát thấy CME lần này");
} catch (ConcurrentModificationException ex) {
    System.out.println("Quan sát thấy CME lần này");
}
```

**Không có stdout bắt buộc** cho ví dụ này. Với `ArrayList` của một JDK cụ thể có thể thấy `CME`, nhưng **không được lấy điều đó làm đảm bảo chung**. Không dùng cách “thử bắt CME rồi tiếp tục sử dụng dữ liệu vừa đọc” để bảo đảm tính toàn vẹn.

### 4.3. Non-interference trong Stream

Theo hợp đồng Stream, các lambda chạy trên nguồn không-concurrent phải **không can thiệp** vào collection nguồn, kể cả pipeline tuần tự:

```java
List<Integer> numbers = new ArrayList<>(Arrays.asList(1, 2, 3));

// SAI: sửa collection đang làm nguồn của chính stream.
numbers.parallelStream().forEach(numbers::remove);
```

Ngoài rủi ro data race, đoạn minh họa còn phụ thuộc overload của `remove` và là thiết kế sai. Cách đúng là tạo kết quả mới hoặc thay đổi collection **sau khi** terminal operation đã hoàn thành:

```java
List<Integer> filtered = numbers.stream()
        .filter(n -> n != 2)
        .collect(Collectors.toList());
// numbers vẫn là [1, 2, 3]; filtered là [1, 3].
```

Nếu cần xóa phần tử khỏi danh sách đang dùng, dùng API collection phù hợp **ngoài quá trình duyệt stream** (ví dụ `removeIf` khi đã kiểm soát quyền truy cập), không sửa dữ liệu nguồn từ lambda của chính pipeline.

## 5. Characteristic giúp hiểu khả năng của nguồn

`Spliterator.characteristics()` là bit set chứa các thuộc tính, có thể kiểm tra bằng `hasCharacteristics(flags)`.

```java
Spliterator<String> sp = list.spliterator();

boolean ordered = sp.hasCharacteristics(Spliterator.ORDERED);
boolean sized = sp.hasCharacteristics(Spliterator.SIZED);
boolean concurrent = sp.hasCharacteristics(Spliterator.CONCURRENT);
boolean immutable = sp.hasCharacteristics(Spliterator.IMMUTABLE);
```

| Flag | Ý nghĩa thực tế |
| --- | --- |
| `ORDERED` | Có thứ tự gặp phần tử xác định; `trySplit` (nếu thành công) trả strict prefix |
| `DISTINCT` | Các phần tử đã gặp không trùng nhau theo `equals` |
| `SORTED` | Phần tử theo thứ tự so sánh tương ứng, khi có comparator hợp lệ |
| `SIZED` | `estimateSize` biểu thị kích thước chính xác trong các điều kiện mà hợp đồng quy định |
| `SUBSIZED` | Các phần tách tiếp cũng thỏa `SIZED` |
| `NONNULL` | Nguồn không cung cấp phần tử `null` |
| `IMMUTABLE` | Nguồn của traversal không thể bị sửa cấu trúc trong suốt phép duyệt |
| `CONCURRENT` | Nguồn có thể được sửa an toàn bởi nhiều thread mà không cần đồng bộ hóa ngoài, theo chính sách của nguồn |

**Không có flag chuẩn tên `LATE_BINDING` hay `FAIL_FAST`.** Cần tra JavaDoc của implementation để biết thời điểm binding và cách phát hiện interference; không thể suy ra đầy đủ chỉ từ `characteristics()`.

**Đặc biệt quan trọng:**

- `CONCURRENT` nói về **nguồn** được phép thay đổi đồng thời; **không** có nghĩa cùng một instance `Spliterator` trở nên an toàn để nhiều thread gọi traversal method cùng lúc.
- `IMMUTABLE` của Spliterator không nhất thiết đồng nghĩa đối tượng Collection công khai bị cấm gọi `add`; với `CopyOnWriteArrayList`, snapshot mà Spliterator duyệt không đổi, trong khi collection vẫn hỗ trợ `add` tạo phiên bản mảng mới.
- `IMMUTABLE` là về **cấu trúc phần tử trong nguồn traversal**, không phải các object được tham chiếu hoàn toàn deep-immutable. Nếu phần tử là object mutable, giá trị các field của nó có thể thay đổi theo cơ chế đồng thời khác.
- Một top-level Spliterator không nên đồng thời báo `CONCURRENT` với `IMMUTABLE` hoặc `CONCURRENT` với `SIZED`; đó là các kết hợp không nhất quán theo đặc tả chung. Một số sub-spliterator có ngoại lệ được mô tả trong JavaDoc.

## 6. So sánh ba nguồn phổ biến

| Nguồn | Chính sách cơ bản | Characteristic liên quan | Cập nhật trong lúc duyệt |
| --- | --- | --- | --- |
| `ArrayList` | **Late-binding, fail-fast best-effort** | `ORDERED`, `SIZED`, `SUBSIZED` | Không được tự ý sửa cấu trúc khi traversal; không dựa vào CME để giữ đúng |
| `CopyOnWriteArrayList` | **Snapshot lúc tạo Spliterator** | `IMMUTABLE`, `ORDERED`, `SIZED`, `SUBSIZED` | Có thể cập nhật collection; Spliterator cũ thấy snapshot, không thấy các thay đổi mới |
| `ConcurrentHashMap.keySet()` | **Weakly consistent** | `CONCURRENT`, `DISTINCT`, `NONNULL` | Cho phép cập nhật đồng thời; traversal có thể thấy một phần cập nhật, không đảm bảo snapshot nhất quán |

### 6.1. ArrayList: kết quả ổn định khi không có writer đồng thời

Với dữ liệu không bị chỉnh sửa trong khi Stream thực thi, hoàn toàn có thể dùng:

```java
List<Integer> numbers = new ArrayList<>(Arrays.asList(1, 2, 3, 4));

int total = numbers.parallelStream()
        .mapToInt(Integer::intValue)
        .sum();
// total == 10; nguồn không thay đổi trong lúc xử lý.
```

**Parallel stream không có nghĩa rằng ArrayList phải là concurrent collection.** Điều kiện là không để bên khác sửa nguồn trong khoảng terminal operation đang chạy, và các hàm xử lý phải stateless/non-interfering.

### 6.2. CopyOnWriteArrayList: snapshot view

`CopyOnWriteArrayList` dùng kỹ thuật sao chép mảng khi thay đổi cấu trúc. Spliterator/iterator của nó nhìn thấy snapshot đã tồn tại tại thời điểm được tạo:

```java
CopyOnWriteArrayList<String> names = new CopyOnWriteArrayList<>(
        Arrays.asList("A", "B"));

Spliterator<String> snapshot = names.spliterator();
names.add("C");

List<String> seen = new ArrayList<>();
snapshot.forEachRemaining(seen::add);

// seen = [A, B].
// names hiện tại = [A, B, C].
```

Snapshot thích hợp cho dữ liệu được đọc nhiều, cập nhật ít hoặc yêu cầu một khung nhìn ổn định tại thời điểm tạo Spliterator. Nhưng **mỗi lần ghi có thể tốn chi phí sao chép**, nên không phải thay thế tối ưu cho mọi danh sách bị ghi liên tục.

**Lưu ý:** Snapshot là một **bản chụp của mảng tham chiếu**, không tự sao chép sâu các object; nếu object bên trong mutable, vẫn cần thiết kế thread-safety riêng cho trạng thái của object.

### 6.3. ConcurrentHashMap: weak consistency

`ConcurrentHashMap` cho phép thao tác `put`, `remove` và truy vấn từ nhiều thread theo hợp đồng concurrent của nó. Spliterator lấy từ `keySet()` có `CONCURRENT`, `DISTINCT`, `NONNULL` và là **weakly consistent**.

```java
ConcurrentHashMap<String, Integer> counters =
        new ConcurrentHashMap<>();
counters.put("A", 1);
counters.put("B", 2);

Spliterator<String> keys = counters.keySet().spliterator();

boolean concurrent = keys.hasCharacteristics(Spliterator.CONCURRENT);
// true
```

Giả sử thread khác gọi `put("C", 3)` hoặc `remove("A")` **trong lúc traversal**:

- Spliterator có thể tiếp tục duyệt mà không ném `ConcurrentModificationException`.
- Kết quả **có thể thấy hoặc không thấy** một số cập nhật đồng thời.
- Không được hiểu kết quả duyệt là ảnh chụp nguyên tử của **toàn bộ Map tại đúng một thời điểm**.
- Một phép tổng/đếm từ stream có thể phản ánh một trạng thái hỗn hợp nếu các giá trị thay đổi song song.

Đây là sự khác biệt quan trọng giữa **thread-safe traversal** và **transactional snapshot**. Một phép báo cáo cần số liệu nhất quán toàn cục phải dùng phương án nhất quán phù hợp (quiescence/khóa/snapshot dưới phối hợp, đồng bộ version, hoặc cơ chế transaction của hệ thống lưu trữ) thay vì coi `ConcurrentHashMap.parallelStream()` tự bảo đảm snapshot.

**Cảnh báo tên gọi:** Trong tài liệu không nên dùng từ “fail-safe iterator” như một đặc tính chuẩn của API. Hai cách mô tả rõ ràng hơn là **snapshot traversal** (`CopyOnWriteArrayList`) và **weakly consistent traversal** (`ConcurrentHashMap`); đây là hai mô hình khác nhau.

## 7. Chương trình đầy đủ, biên dịch và chạy được

Ví dụ này minh họa ba cơ chế **không cần tạo race thực sự** để có stdout cố định:

1. `ArrayList`: tạo Spliterator, thêm phần tử **trước binding**, rồi duyệt thấy phần tử mới.
2. `CopyOnWriteArrayList`: tạo Spliterator snapshot, cập nhật collection rồi duyệt **ảnh chụp cũ**.
3. `ConcurrentHashMap`: kiểm tra đặc tính `CONCURRENT`, duyệt keys khi **không có writer**, và so sánh phép tổng song song.

Để đầu ra xác định, khóa Map được sắp bằng `Collections.sort` **sau khi** duyệt; điều này không có nghĩa `ConcurrentHashMap` tự bảo đảm thứ tự duyệt keys.

**Tạo tệp `SpliteratorSourcesDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Spliterator;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;

public class SpliteratorSourcesDemo {
    public static void main(String[] args) {
        ArrayList<String> arrayList = new ArrayList<>(
                Arrays.asList("A", "B"));

        // Late-binding: chưa traversal, split hay hỏi estimateSize.
        Spliterator<String> late = arrayList.spliterator();
        arrayList.add("C"); // Thay đổi hợp lệ trước khi Spliterator bind.

        List<String> lateSeen = new ArrayList<>();
        late.forEachRemaining(lateSeen::add);

        CopyOnWriteArrayList<String> cow = new CopyOnWriteArrayList<>(
                Arrays.asList("A", "B"));

        // Snapshot được chụp khi tạo Spliterator.
        Spliterator<String> snapshot = cow.spliterator();
        cow.add("C");

        List<String> snapshotSeen = new ArrayList<>();
        snapshot.forEachRemaining(snapshotSeen::add);

        ConcurrentHashMap<String, Integer> map =
                new ConcurrentHashMap<>();
        map.put("A", 1);
        map.put("B", 2);

        Spliterator<String> concurrent = map.keySet().spliterator();
        List<String> keysSeen = new ArrayList<>();
        concurrent.forEachRemaining(keysSeen::add);

        // Chỉ sắp xếp để đầu ra dễ so sánh.
        Collections.sort(keysSeen);

        boolean arrayListOrdered = arrayList.spliterator()
                .hasCharacteristics(Spliterator.ORDERED);
        boolean snapshotImmutable = cow.spliterator()
                .hasCharacteristics(Spliterator.IMMUTABLE);
        boolean mapConcurrent = map.keySet().spliterator()
                .hasCharacteristics(Spliterator.CONCURRENT);

        // Không có writer đồng thời ở ví dụ này nên phép tổng ổn định.
        int parallelSum = map.values().parallelStream()
                .mapToInt(Integer::intValue)
                .sum();

        System.out.println("ArrayList before binding: " + lateSeen);
        System.out.println("CopyOnWrite snapshot: " + snapshotSeen);
        System.out.println("CopyOnWrite current: " + cow);
        System.out.println("ConcurrentMap keys: " + keysSeen);
        System.out.println("ArrayList ORDERED: " + arrayListOrdered);
        System.out.println("CopyOnWrite IMMUTABLE: " + snapshotImmutable);
        System.out.println("ConcurrentMap CONCURRENT: " + mapConcurrent);
        System.out.println("ConcurrentMap sum (no writers): " + parallelSum);

        if (!lateSeen.equals(Arrays.asList("A", "B", "C"))
                || !snapshotSeen.equals(Arrays.asList("A", "B"))
                || !cow.equals(Arrays.asList("A", "B", "C"))
                || !keysSeen.equals(Arrays.asList("A", "B"))
                || !arrayListOrdered || !snapshotImmutable
                || !mapConcurrent || parallelSum != 3) {
            throw new AssertionError("Incorrect Spliterator result");
        }
        System.out.println("Checks passed.");
    }
}
```

Chạy trên JDK 17+; `--release 8` bảo đảm mã không dùng cú pháp/API chỉ mới xuất hiện từ Java 9 trở đi:

```bash
javac --release 8 SpliteratorSourcesDemo.java
java SpliteratorSourcesDemo
```

**Stdout (đã kiểm tra bằng OpenJDK 24):**

```text
ArrayList before binding: [A, B, C]
CopyOnWrite snapshot: [A, B]
CopyOnWrite current: [A, B, C]
ConcurrentMap keys: [A, B]
ArrayList ORDERED: true
CopyOnWrite IMMUTABLE: true
ConcurrentMap CONCURRENT: true
ConcurrentMap sum (no writers): 3
Checks passed.
```

**Tại sao ví dụ không chủ động sửa ConcurrentHashMap khi đang duyệt?** Vì điều đó khiến danh sách keys quan sát được không xác định; không có một stdout cố định đúng cho mọi lịch trình thread. Bài dùng `hasCharacteristics` để kiểm tra chính sách nguồn và duyệt không cạnh tranh để minh họa tính chất, còn tình huống có writer được giải thích ở phần trước.

## 8. Ba trạng thái dữ liệu dễ nhầm lẫn

### 8.1. Sửa trước khi terminal stream bắt đầu

Với Stream tạo từ `ArrayList` tiêu chuẩn (nguồn well-behaved, late-binding), việc sửa danh sách **trước** terminal operation thường được phản ánh khi stream bắt đầu xử lý:

```java
List<String> values = new ArrayList<>(Arrays.asList("A", "B"));
Stream<String> pipeline = values.stream().map(String::toLowerCase);

values.add("C"); // Trước terminal operation.
List<String> result = pipeline.collect(Collectors.toList());
// result = [a, b, c]
```

Điều này không xung đột với nguyên tắc non-interference: sửa nguồn diễn ra **trước khi** stream bắt đầu tính toán terminal. Với **custom Spliterator** có chính sách binding khác hoặc khi đã gọi `spliterator()` trên chính stream, cần xét lại hợp đồng cụ thể.

### 8.2. Sửa sau khi bắt đầu duyệt nguồn không-concurrent

```java
List<String> values = new ArrayList<>(Arrays.asList("A", "B"));

values.parallelStream().forEach(value -> {
    // Không sửa chính values tại đây.
});
```

Nếu có writer khác hoặc action sửa `values` giữa lúc terminal đang chạy, bạn đã tạo structural interference. Không được tin vào kết quả, dù cuối cùng không quan sát thấy CME.

### 8.3. Sửa trong khi đang duyệt nguồn concurrent

```java
ConcurrentHashMap<String, Integer> map = new ConcurrentHashMap<>();
map.put("A", 1);

// Nguồn cho phép traversal đồng thời với các thao tác update hợp lệ.
// Nhưng kết quả aggregate trong lúc update không phải snapshot nguyên tử.
int observed = map.values().parallelStream()
        .mapToInt(Integer::intValue)
        .sum();
```

Bản thân việc duyệt từ `ConcurrentHashMap` trong sự hiện diện của writer là được thiết kế để an toàn theo chính sách nguồn; **độ nhất quán nghiệp vụ của phép tổng** vẫn do yêu cầu ứng dụng quyết định. Hãy phân biệt “không corrupt cấu trúc collection” với “tổng phản ánh một thời điểm duy nhất”.

## 9. Thiết kế ứng dụng: chọn nguồn phù hợp

| Yêu cầu | Cách thiết kế nên cân nhắc | Điều không được giả định |
| --- | --- | --- |
| Duyệt `ArrayList` một lần, không có writer trong khoảng tính toán | Dùng `stream()`/`parallelStream()`; không sửa nguồn trong terminal | “Parallel” tự động bảo vệ nguồn |
| Muốn snapshot nhỏ/độc lập trước khi duyệt | Tạo bản sao dưới cơ chế phối hợp thích hợp, rồi duyệt bản sao | `new ArrayList<>(sharedList)` luôn an toàn khi writer không đồng bộ |
| Nhiều lượt đọc, ít lượt ghi; muốn snapshot traversal | `CopyOnWriteArrayList` khi hợp workload | Snapshot tự động cập nhật sau khi đã tạo |
| Nhiều cập nhật Map đồng thời, chỉ cần quan sát gần hiện tại | `ConcurrentHashMap` và weakly consistent traversal | Toàn bộ kết quả là một bản chụp nguyên tử |
| Báo cáo tài chính/kiểm kê cần một ảnh chụp nhất quán | Dùng snapshot/transaction/khóa/version có thiết kế rõ ràng | `ConcurrentHashMap` hoặc `parallelStream` đủ để đảm bảo chính xác |
| Nguồn custom dùng Stream | Cung cấp Spliterator có chính sách binding/interference rõ ràng; hoặc Supplier tạo Spliterator khi terminal bắt đầu | Mọi custom Spliterator đều late-binding/fail-fast |

**Gợi ý thực tế:** Với phần lớn công việc thuần đọc, dễ kiểm soát nhất là tạo/ổn định nguồn trước khi mở terminal, chỉ sử dụng lambda stateless và thu thập kết quả mới thay vì mutating source. Chỉ cần chuyển sang concurrent collection khi **có nhu cầu cập nhật đồng thời thật sự**, không phải vì nhìn thấy `parallelStream()`.

### 9.1. Tại sao “unmodifiable view” chưa chắc là snapshot?

`Collections.unmodifiableList(backing)` chặn sửa đổi qua **view**, nhưng không nhất thiết chặn một đối tượng khác đang giữ `backing` khỏi gọi `add`/`remove`. Vì vậy view không tự đảm bảo nguồn không thay đổi trong lúc duyệt.

```java
List<String> backing = new ArrayList<>(Arrays.asList("A", "B"));
List<String> view = Collections.unmodifiableList(backing);

backing.add("C");
// view cũng phản ánh "C", vì nó bao quanh backing chứ không sao chép.
```

Nếu cần bản sao độc lập, phải thiết kế thời điểm chụp nguồn và đồng bộ với writer cho đúng; “chỉ dùng API read-only” không thay thế sự ổn định cấu trúc dữ liệu.

### 9.2. Có thể xử lý concurrent source bằng parallel Stream không?

**Có**, nhưng điều kiện cần đồng thời bao gồm:

- Nguồn/iterator/spliterator hỗ trợ đúng chính sách cập nhật đồng thời.
- Lambda trong pipeline phải stateless và an toàn với trạng thái chia sẻ mà nó thật sự sử dụng.
- Phép reduction/collector cần thỏa quy tắc của nó (associativity/identity và tính thread-safety nếu collector concurrent).
- Chấp nhận mức nhất quán mà nguồn cung cấp. Nếu nghiệp vụ yêu cầu một “điểm ảnh chụp” toàn cục, không dùng kết quả weakly consistent làm số liệu quyết toán.

**CONCURRENT Spliterator không đồng nghĩa CONCURRENT Collector.** Hai khái niệm khác nhau: một thuộc **nguồn** (cho phép nguồn thay đổi khi duyệt), một thuộc **cơ chế gộp kết quả** (các worker có thể cộng dồn vào result container theo hợp đồng collector). Không đánh đồng chúng.

## 10. Khi tự triển khai Spliterator

Hầu hết mã ứng dụng nên dùng `collection.spliterator()`, `Arrays.spliterator(...)`, Stream từ collection hoặc các API thư viện đã có. Chỉ triển khai trực tiếp Spliterator nếu đang xây dựng **một nguồn dữ liệu/cấu trúc tùy chỉnh**.

Những việc quan trọng:

1. Xác định rành mạch **binding policy**: snapshot/early-binding, late-binding hay concurrent source.
2. Mô tả và xử lý **structural interference** nếu không báo `IMMUTABLE` hay `CONCURRENT`.
3. Chỉ báo flag mà thực sự đáp ứng: không gắn `SIZED` khi không thể hứa số phần tử theo hợp đồng.
4. Bảo đảm `trySplit()` không để hai Spliterator con duyệt trùng một phần tử nếu loại nguồn không cho phép.
5. Nếu `ORDERED`, phần tách phải đại diện cho **strict prefix**.
6. Không cho hai thread cùng thao tác một instance Spliterator trừ khi implementation có đồng bộ hóa rõ ràng.
7. Kiểm thử các điều kiện rỗng, phần tử đơn, nhiều phần tử, split không cân đối, exception từ action và mutation theo chính sách đã ghi.

Với factory của `Spliterators`:

- `Spliterators.spliterator(collection, characteristics)` là helper **late-binding** dựa trên collection.
- `Spliterators.spliterator(iterator, size, characteristics)` dùng một Iterator **đã tồn tại**, là helper **không late-binding** và kế thừa fail-fast nếu Iterator có.
- `Spliterators.spliteratorUnknownSize(iterator, characteristics)` không có size estimate xác định; không nên tự gắn `SIZED` vô căn cứ.

Những điều trên giải thích vì sao không thể đọc flag rồi mặc định “mọi Spliterator lấy từ Iterator đều late-binding”. Factory và loại đối số quan trọng.

**Với `StreamSupport.stream(...)`:** Khi Spliterator tự triển khai không có `IMMUTABLE`, `CONCURRENT` hoặc late-binding, cân nhắc overload nhận **`Supplier<? extends Spliterator<T>>`**, để nguồn được tạo gần thời điểm terminal operation bắt đầu. Cần truyền `characteristics` đúng với Spliterator mà supplier tạo; không khai báo sai đặc tính để “tăng tốc”.

## 11. Lỗi phổ biến cần tránh

| Nhận định/việc làm | Vì sao sai? | Thay bằng |
| --- | --- | --- |
| “Tạo Spliterator xong là chốt dữ liệu” | Late-binding có thể chưa gắn với nguồn | Kiểm tra thời điểm binding từng implementation |
| “Gọi `estimateSize()` trước duyệt không ảnh hưởng” | Có thể kích hoạt binding | Không truy vấn size nếu muốn còn thời gian sửa nguồn trước binding |
| “Fail-fast luôn ném CME khi có race” | Chỉ phát hiện best-effort | Dùng đồng bộ hóa hoặc nguồn concurrent/snapshot |
| “Không thấy CME tức là an toàn” | Không có bằng chứng về memory visibility hoặc kết quả | Xác định chính sách non-interference và data-race freedom |
| “CME ngắt ngay trước mọi side effect” | `forEachRemaining` có thể kiểm tra sau khi action đã chạy | Không đặt giao dịch/side effect không thể hoàn tác dựa vào CME |
| “ConcurrentMap traversal là ảnh chụp toàn Map” | Weak consistency có thể thấy tập cập nhật khác nhau | Snapshot/transaction/coordination nếu cần nhất quán |
| “CopyOnWriteArrayList là collection immutable” | Collection vẫn cho phép thêm/xóa; Spliterator cũ giữ snapshot | Phân biệt immutable traversal và mutable container |
| “CONCURRENT cho phép hai thread dùng chung Spliterator” | Flag mô tả nguồn, không mô tả thread-safety instance | Chia Spliterator rồi giao cho từng worker |
| “ArrayList.parallelStream() luôn không an toàn” | Không có writer thì parallel traversal hợp lệ | Giữ nguồn ổn định trong suốt terminal |
| “Chỉ gọi `unmodifiableList` là chống race” | View có thể phản ánh backing list bị sửa ở nơi khác | Chụp bản sao có phối hợp hoặc khóa |
| “Dùng `forEach(list::add)` lên chính list nguồn” | Structural interference và có thể đua dữ liệu | Tạo collection kết quả bằng collector |
| “Concurrent collection đồng nghĩa phép cộng song song chính xác tại một thời điểm” | Nguồn không cung cấp atomic snapshot | Thiết kế tiêu chí nhất quán riêng |

## 12. Kiểm thử thế nào mới đúng?

### 12.1. Kiểm thử hành vi xác định

Với `ArrayList`, kiểm tra thay đổi **trước binding** được phản ánh và không mutate sau khi duyệt bắt đầu.

Với `CopyOnWriteArrayList`, kiểm tra Spliterator tạo trước update vẫn thấy snapshot cũ, còn collection hiện tại chứa dữ liệu mới.

Với `ConcurrentHashMap`, kiểm tra `CONCURRENT` characteristic và các tính chất hợp đồng (ví dụ keys không `null`). Nếu **không có writer đồng thời**, việc xác nhận giá trị kết quả ổn định vẫn phù hợp.

### 12.2. Kiểm thử trong lúc concurrent update

Nếu cố ý có nhiều writer và reader trong test, **không assert một danh sách cụ thể được quan sát** hoặc số phần tử bằng đúng một mốc đang thay đổi; đó không phải điều weak consistency cam kết. Thay vào đó:

- Kiểm tra không có structural corruption và các invariant mà nguồn có cam kết.
- Kiểm tra các thao tác đọc/ghi concurrent theo contract của collection.
- Nếu cần kết quả chính xác tại một mốc, cho các writer dừng hoặc lấy snapshot bằng cơ chế phối hợp đã thiết kế rồi kiểm tra snapshot.
- Dùng stress test để tìm race, nhưng **không** lấy “chạy 1000 lần không lỗi” làm chứng minh thread-safety.

**Đừng viết unit test yêu cầu `ConcurrentModificationException` xuất hiện sau mọi lần thay đổi cấu trúc.** Fail-fast là best-effort; chức năng đúng của ứng dụng không được dựa vào việc một exception có xuất hiện trong điều kiện đua dữ liệu hay không.

## 13. Câu hỏi tự luyện

1. `ArrayList.spliterator()` có được gắn với nguồn ngay lúc gọi `spliterator()` không? — **Không nhất thiết**; đây là Spliterator late-binding.
2. Ba tác nhân thường khiến một Spliterator late-binding bắt đầu bind là gì? — **Duyệt, split hoặc truy vấn ước lượng size đầu tiên**.
3. Có thể dùng `ArrayList.parallelStream()` khi không thread nào sửa nguồn trong khi terminal operation chạy không? — **Có**, nếu các lambda không can thiệp nguồn và các phần state chia sẻ khác cũng an toàn.
4. Nếu sau `estimateSize()` ta gọi `list.add(...)` rồi duyệt, vì sao không được khẳng định mọi phần tử mới sẽ được thấy? — Vì truy vấn size có thể **đã bind** nguồn và việc sửa sau đó thành structural interference.
5. Vì sao `ConcurrentModificationException` không phải công cụ đồng bộ? — Vì fail-fast **best-effort**, không bảo đảm thời điểm phát hiện và không thiết lập chính sách nhất quán dữ liệu.
6. `CopyOnWriteArrayList` được thêm `C` sau khi Spliterator đã tạo; Spliterator cũ có thấy `C` không? — **Không**, nó duyệt snapshot tại lúc tạo.
7. `ConcurrentHashMap.keySet().spliterator()` có characteristic nào nói rằng có thể duyệt trong sự hiện diện của writer? — **`CONCURRENT`**.
8. `CONCURRENT` có cho phép hai thread gọi `tryAdvance` trên cùng một instance không? — **Không**; không mặc nhiên đảm bảo thread-safety của instance Spliterator.
9. Vì sao tổng các giá trị của `ConcurrentHashMap` trong lúc writer đang thay đổi dữ liệu có thể không là tổng tại một thời điểm nhất quán? — Vì traversal **weakly consistent**, không phải snapshot nguyên tử.
10. Khi nào nên chọn snapshot thay vì weakly consistent traversal? — Khi yêu cầu nghiệp vụ đòi **một tập dữ liệu ổn định** cho toàn bộ phép tính.

## Tài liệu chuẩn (vẫn còn áp dụng)

- [Oracle Java SE 25 — `Spliterator`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Spliterator.html): binding, structural interference, fail-fast best-effort, các characteristic và thread confinement.
- [Oracle Java SE 25 — `ArrayList`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayList.html): `spliterator()` late-binding/fail-fast và giới hạn sửa nguồn.
- [Oracle Java SE 25 — `CopyOnWriteArrayList`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html): snapshot và `IMMUTABLE`.
- [Oracle Java SE 25 — `ConcurrentHashMap`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): weakly consistent spliterator của keySet/values/entrySet và `CONCURRENT`.
- [Oracle Java SE 25 — `java.util.stream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html): non-interference, terminal operations, parallel stream và nguồn concurrent.
- [Oracle Java SE 25 — `Spliterators`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Spliterators.html): phân biệt factory từ Collection và từ Iterator về binding.

**Kết luận:** **Late-binding** cho phép trì hoãn phạm vi nguồn đến lúc cần duyệt; **fail-fast** chỉ phát hiện interference **theo best-effort**; **concurrent source** cho phép cập nhật đồng thời theo một mô hình nhất quán cụ thể; và **snapshot** giữ một ảnh chụp ổn định. Muốn một chương trình Stream/Spliterator đúng, cần xác định **thời điểm binding, mức nhất quán dữ liệu và quyền thay đổi nguồn** trước khi nghĩ đến song song hóa hay tối ưu hiệu năng.
