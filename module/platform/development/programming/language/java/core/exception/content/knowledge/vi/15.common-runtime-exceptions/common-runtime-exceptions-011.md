# `ConcurrentModificationException` và giới hạn của cơ chế fail-fast trong Java

> **Bối cảnh:** Java Core → Exception → Ngoại lệ runtime. `java.util.ConcurrentModificationException` (CME) thường xuất hiện khi chương trình **thay đổi cấu trúc một collection trong lúc đang duyệt nó** bằng iterator theo cơ chế *fail-fast*. Tên gọi “Concurrent” dễ gây hiểu nhầm: **không cần có hai thread** mới phát sinh exception. Ngược lại, trong chương trình đa luồng, **không có CME cũng không chứng minh code an toàn**. Fail-fast là công cụ phát hiện bug theo nỗ lực tốt nhất (*best effort*), **không phải** cơ chế đồng bộ hóa, khóa, transaction hay cam kết phát hiện mọi thay đổi.

## 1. Hiểu đúng bản chất của `ConcurrentModificationException`

CME là một lớp exception unchecked:

```text
java.lang.Throwable
└── java.lang.Exception
    └── java.lang.RuntimeException
        └── java.util.ConcurrentModificationException
```

Một tình huống phổ biến:

```java
// Mảnh code minh họa, không phải tệp standalone.
List<String> names = new ArrayList<>(
        List.of("An", "Bình", "Chi"));

for (String name : names) {
    if ("Bình".equals(name)) {
        names.remove(name); // Thay đổi collection bên ngoài iterator.
    }
}
```

Mã trên **có thể** ném CME tùy trạng thái duyệt; vì fail-fast là best effort nên **đừng dùng chính đoạn mã đó để khẳng định exception luôn xuất hiện**. Đặc biệt, một thao tác xóa có thể khiến iterator hết phần tử trước lần kiểm tra tiếp theo. Các ví dụ kiểm chứng ở phần sau chủ động chọn dữ liệu và thứ tự để lỗi phát sinh ổn định trong JDK 17.

Ý nghĩa chính:

- **Nguồn bất nhất:** một iterator đang dùng giả định về cấu trúc collection, trong khi code khác thay đổi cấu trúc mà không thông qua cơ chế cho phép của iterator.
- **Phản ứng:** iterator *có thể* phát hiện sự thay đổi và ném CME, thay vì tiếp tục dựa trên trạng thái đã lỗi thời.
- **Không phải bằng chứng chắc chắn:** cơ chế fail-fast không bảo đảm luôn phát hiện và cũng không bảo đảm an toàn thread.
- **Không bắt buộc có concurrency:** một method, một thread, vừa duyệt vừa xóa bằng `list.remove(...)` cũng đủ tạo điều kiện phát sinh CME.
- **Không phải checked exception:** không bắt buộc khai báo `throws ConcurrentModificationException` hay thêm `catch` để code biên dịch.

### 1.1. CME không có nghĩa collection bị hỏng vĩnh viễn

Exception báo rằng một hoạt động duyệt không thể tiếp tục an toàn theo hợp đồng/triển khai fail-fast. Nó không tự nói rằng toàn bộ bộ nhớ hay collection đã hỏng vĩnh viễn. Tuy nhiên **trạng thái nghiệp vụ có thể đã thay đổi một phần trước lỗi**: phần tử có thể đã bị xóa, giá trị có thể đã được cập nhật, hoặc các side effect khác đã xảy ra.

Vì vậy khi xử lý CME, phải phân biệt:

1. **Phát hiện đường logic sai** và sửa ở vị trí tạo ra lỗi.
2. **Đánh giá trạng thái đã thay đổi**; CME không rollback các thao tác trước đó.
3. **Không dùng catch để tiếp tục iterator cũ** rồi hy vọng trạng thái tự phục hồi.

## 2. “Concurrent” nhưng một thread vẫn có thể gây lỗi

Ví dụ một chương trình tuần tự:

```text
Một thread
  ├── tạo ArrayList
  ├── tạo Iterator
  ├── iterator.next() trả phần tử đầu
  ├── list.remove(...) thay đổi cấu trúc trực tiếp
  └── iterator.next() kiểm tra trạng thái → có thể CME
```

Đó là sự *xung đột giữa thao tác duyệt và thay đổi cấu trúc*, không nhất thiết là *data race giữa các thread*.

Một ví dụ khác: callback của `forEach` sửa chính danh sách đang được duyệt. Cả quá trình vẫn có thể chạy trong một thread nhưng vi phạm giả định của iterator.

Ngược lại, có nhiều thread mà **không** CME, ví dụ khi:

- Thực hiện thao tác đồng thời trên một collection có cơ chế iterator *weakly consistent* như `ConcurrentHashMap`.
- Duyệt snapshot của `CopyOnWriteArrayList`.
- Các thread đồng bộ hóa đầy đủ, khiến việc duyệt không chồng lên một thay đổi cấu trúc nguy hiểm.
- Chỉ có các thao tác không ảnh hưởng cấu trúc theo hợp đồng cụ thể.

Vì thế đừng “chữa” CME bằng cách đơn giản tắt đa luồng; hãy xác định **iterator, loại collection, cách sửa và phạm vi ownership**.

## 3. Fail-fast: khái niệm, mục đích và phạm vi

*Fail-fast iterator* cố phát hiện khi cấu trúc collection bị thay đổi ngoài các thao tác được iterator cho phép trong lúc duyệt. Đối với một số collection phổ biến như `ArrayList` và `HashMap`, iterator fail-fast giúp bug xuất hiện sớm thay vì để chương trình tiếp tục với một kết quả khó dự đoán.

Mục đích là **phát hiện vi phạm giao ước**, không phải “cấm sửa collection vĩnh viễn”.

Ví dụ với `ArrayList`:

- Sau khi tạo iterator, việc gọi `list.add(...)` hoặc `list.remove(...)` có thể làm iterator trở nên không hợp lệ.
- `iterator.remove()` sau một lần `next()` hợp lệ có thể xóa phần tử hiện tại **và đồng bộ trạng thái iterator**, nên duyệt có thể tiếp tục.
- `ListIterator.add(...)` và `ListIterator.remove()` cũng là các con đường chỉnh sửa có hợp đồng riêng.
- Không phải mọi phương thức có tên “thay đổi” đều là *structural modification*: `list.set(index, newValue)` thay giá trị tại vị trí đã có mà **không đổi số phần tử** trong `ArrayList`; thông thường không khiến iterator fail-fast chỉ vì thay giá trị.
- Ngược lại, việc sắp xếp hoặc một số thao tác đặc thù của implementation có thể tác động tới dấu hiệu thay đổi dù size không đổi. Đừng biến “size thay đổi” thành định nghĩa tuyệt đối cho mọi class và API.

### 3.1. Fail-fast không đồng nghĩa với synchronized

Một iterator fail-fast **không tự khóa collection**. Nếu hai thread cùng đọc/ghi vào `ArrayList` không được bảo vệ, chúng có thể gặp data race, quan sát kết quả sai, mất cập nhật, CME hoặc lỗi khác. Ngay cả khi thấy CME trong một ca test, nó cũng không cung cấp quan hệ *happens-before* hay sự an toàn truy cập ở ca chạy khác.

Một cách dùng sai:

```java
// Anti-pattern: không dùng exception như đồng hồ báo động đồng bộ.
try {
    for (String x : sharedList) {
        consume(x);
    }
} catch (ConcurrentModificationException e) {
    // Giả sử mọi tình huống unsafe đều đã được phát hiện.
}
```

Đây là mã minh họa chưa định nghĩa `sharedList`/`consume`. Việc bắt CME không sửa tính thiếu đồng bộ. Hãy thiết kế ownership, khóa, snapshot hoặc concurrent collection tùy yêu cầu.

## 4. Cơ chế điển hình: `modCount` và `expectedModCount`

Trong nhiều implementation collection của JDK, cơ chế fail-fast dựa vào hai giá trị:

- **`modCount`:** bộ đếm sửa đổi của cấu trúc collection, thường được cập nhật khi có thay đổi cấu trúc.
- **`expectedModCount`:** giá trị mà iterator ghi nhận tại thời điểm tạo hoặc sau thao tác sửa hợp lệ thông qua chính iterator.
- Khi iterator thực hiện thao tác có kiểm tra và thấy hai giá trị **khác nhau**, nó có thể ném `ConcurrentModificationException`.

Sơ đồ:

```text
ArrayList: modCount = 5
Iterator mới: expectedModCount = 5

iterator.next()
  expected = 5, actual = 5 → tiếp tục

list.remove(0) trực tiếp
  modCount = 6

iterator.next()
  expected = 5, actual = 6 → fail-fast (CME)
```

**Lưu ý về tính chính xác:** các tên `modCount` và `expectedModCount` là chi tiết triển khai của các collection/iterator cụ thể, không phải một API `Iterator` công khai để mọi collection đều phải sử dụng. Những container khác có thể phát hiện thay đổi theo cách khác, hoặc không theo fail-fast. Không viết logic ứng dụng phụ thuộc giá trị bộ đếm nội bộ.

### 4.1. Vì sao `Iterator.remove()` có thể hợp lệ?

Khi xóa đúng cách qua iterator:

```java
Iterator<String> it = list.iterator();
while (it.hasNext()) {
    String value = it.next();
    if (shouldRemove(value)) {
        it.remove();
    }
}
```

đây là **mã minh họa** cần biến `list` và `shouldRemove` thích hợp. Iterator tự thực hiện thao tác sửa và cập nhật thông tin nội bộ cần thiết để tiếp tục duyệt trong trạng thái nhất quán với chính nó.

Ngược lại, `list.remove(value)` tác động trực tiếp lên container trong khi iterator đang sống, nên trạng thái quan sát của iterator có thể không còn khớp.

**Không thể kết luận mọi iterator hỗ trợ `remove()`:** phương thức `Iterator.remove()` là optional operation; nhiều iterator từ collection bất biến, snapshot hoặc read-only không hỗ trợ và có thể ném `UnsupportedOperationException`. Phải đọc hợp đồng loại iterator đang dùng.

### 4.2. Việc kiểm tra diễn ra lúc nào?

Một số iterator kiểm tra tại `next()`, `remove()` hoặc các thao tác khác. Với `ArrayList`, `hasNext()` thông thường so vị trí với kích thước mà không bắt buộc kiểm tra `modCount` ngay trong chính phương thức đó. Do vậy có thể xảy ra tình huống thay đổi cấu trúc **không được phát hiện** trước khi vòng lặp kết thúc.

Đừng khẳng định “mọi lần `hasNext()` đều kiểm tra concurrent modification” hoặc “một khi list bị sửa, chắc chắn lần tiếp theo sẽ ném CME”. Đây chính là một giới hạn của cơ chế.

## 5. Java 17 — ví dụ 1: cố tình kích hoạt CME trong một thread

Tạo tệp **`SingleThreadCmeDemo.java`**:

```java
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;

public class SingleThreadCmeDemo {
    public static void main(String[] args) {
        List<String> names =
                new ArrayList<>(List.of("An", "Bình", "Chi", "Dũng"));

        Iterator<String> iterator = names.iterator();
        System.out.println("First: " + iterator.next());

        names.add("Em"); // Thay đổi cấu trúc qua list, không qua iterator.

        try {
            System.out.println("Second: " + iterator.next());
        } catch (ConcurrentModificationException e) {
            System.out.println("Caught: "
                    + e.getClass().getSimpleName());
        }

        System.out.println("Size after add: " + names.size());
    }
}
```

Biên dịch/chạy bằng JDK 17:

```bash
javac -encoding UTF-8 SingleThreadCmeDemo.java
java SingleThreadCmeDemo
```

Stdout khi chạy trên `ArrayList` của JDK 17:

```text
First: An
Caught: ConcurrentModificationException
Size after add: 5
```

Phân tích:

1. `iterator` được tạo khi `names` chứa bốn phần tử.
2. `iterator.next()` đầu tiên đọc `"An"`.
3. `names.add("Em")` thay đổi cấu trúc container sau khi iterator được tạo.
4. `iterator.next()` thứ hai phát hiện sự không khớp và ném CME theo cơ chế fail-fast của `ArrayList`.
5. Chương trình chỉ có **một thread** và vẫn ném CME.
6. Phần tử `"Em"` **đã được thêm** trước khi lỗi xuất hiện; catch không rollback thay đổi.

Ví dụ sử dụng lời gọi `next()` rõ ràng sau thay đổi để quan sát failure của JDK 17. Nó không biến quy tắc **best effort** thành hợp đồng phải ném CME ở mọi implementation và mọi lịch thực thi.

## 6. Enhanced for và Iterator: cú pháp ngắn vẫn có quy tắc duyệt

Với một `Iterable`, vòng lặp:

```java
for (String value : list) {
    consume(value);
}
```

thường được biên dịch theo cấu trúc sử dụng `Iterator` tương đương về ý tưởng:

```java
Iterator<String> it = list.iterator();
while (it.hasNext()) {
    String value = it.next();
    consume(value);
}
```

Hai đoạn đều là ví dụ minh họa, cần biến/method phù hợp. Vì thế, việc gọi `list.remove(...)` hoặc `list.add(...)` ngay trong vòng `for-each` của chính list đó có thể vi phạm hợp đồng iterator.

**Phân biệt:** enhanced for trên **mảng** có cơ chế duyệt riêng bằng chỉ số và không tạo iterator collection fail-fast; không thể suy mọi vòng `for (x : something)` đều sử dụng `modCount`.

### 6.1. Ví dụ anti-pattern

```java
List<Integer> numbers =
        new ArrayList<>(List.of(1, 2, 3, 4));

for (Integer value : numbers) {
    if (value == 2) {
        numbers.remove(value);
    }
}
```

Đây là mảnh code minh họa không được dựa vào để bảo đảm ném CME trong mọi trường hợp. Nếu code này chạy mà **không ném lỗi**, nó vẫn là cách sửa dễ sai khi duyệt và không nên được coi là đã đúng.

Cách diễn đạt chính xác là: thay cấu trúc list bằng phương thức của chính list trong khi một iterator fail-fast đang duyệt **có thể** dẫn tới CME; phải dùng API sửa tương thích với iterator hoặc chuyển sang chiến lược khác.

## 7. Java 17 — ví dụ 2: xóa đúng bằng `Iterator.remove()`

Tạo tệp **`IteratorRemoveDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

public class IteratorRemoveDemo {
    public static void main(String[] args) {
        List<Integer> numbers =
                new ArrayList<>(List.of(1, 2, 3, 4, 5));

        Iterator<Integer> it = numbers.iterator();
        while (it.hasNext()) {
            int value = it.next();
            if (value % 2 == 0) {
                it.remove();
            }
        }

        System.out.println("Remaining: " + numbers);
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 IteratorRemoveDemo.java
java IteratorRemoveDemo
```

Stdout:

```text
Remaining: [1, 3, 5]
```

Giải thích:

- `it.next()` cung cấp phần tử hiện tại; `it.remove()` xóa **phần tử vừa được iterator trả về**.
- Iterator biết rõ thao tác xóa và có thể tiếp tục duyệt.
- Phần tử chẵn `2` và `4` được loại bỏ, còn thứ tự các phần tử lẻ giữ nguyên.
- Không cần gọi `numbers.remove(value)` trực tiếp trong vòng lặp.
- `Iterator.remove()` không hỗ trợ truyền một phần tử bất kỳ làm tham số; nó chỉ xóa đối tượng tương ứng lần `next()`/`previous()` hợp lệ gần nhất (đối với `ListIterator`).

### 7.1. `remove()` có giao ước về trạng thái

Một iterator `remove()` chỉ được phép sau một lời gọi `next()` thành công và thông thường tối đa **một lần** cho mỗi phần tử được trả về trước thao tác tiếp theo. Nếu gọi `remove()` trước `next()`, hoặc gọi hai lần liên tục mà không có `next()` khác, `ArrayList` iterator có thể ném `IllegalStateException`.

`UnsupportedOperationException` lại mang nghĩa khác: iterator **không hỗ trợ** xóa (ví dụ iterator trên list bất biến).

CME, `IllegalStateException` và `UnsupportedOperationException` là **ba điều kiện khác nhau**, không thể chữa bằng cùng một catch bỏ qua.

## 8. Java 17 — ví dụ 3: `ListIterator` thêm/sửa/xóa hợp lệ

`ListIterator<E>` mở rộng `Iterator<E>` để cho phép duyệt hai chiều, chèn phần tử và thay phần tử hiện tại khi danh sách hỗ trợ.

Tạo tệp **`ListIteratorEditDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.ListIterator;

public class ListIteratorEditDemo {
    public static void main(String[] args) {
        List<String> tasks =
                new ArrayList<>(List.of("A", "B", "C"));

        ListIterator<String> it = tasks.listIterator();
        while (it.hasNext()) {
            String task = it.next();
            if ("B".equals(task)) {
                it.set("B-done");
                it.add("B-extra");
            }
        }

        System.out.println("Tasks: " + tasks);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ListIteratorEditDemo.java
java ListIteratorEditDemo
```

Stdout:

```text
Tasks: [A, B-done, B-extra, C]
```

Với `ArrayList`:

1. `it.set("B-done")` thay giá trị của phần tử vừa được `next()` trả về.
2. `it.add("B-extra")` thêm phần tử tại vị trí hiện tại của iterator theo hợp đồng.
3. Iterator quản lý state và vị trí của chính nó, nên vòng duyệt tiếp tục mà không mắc lỗi do chính các thao tác này.
4. Thao tác `add` của `ListIterator` là optional với một số implementation; phải chọn list mutable hỗ trợ.
5. Sau `it.add(...)`, quy tắc cho lần gọi `remove()/set()` tiếp theo thay đổi theo trạng thái của `ListIterator`; không được giả định gọi `set` ngay sau `add` luôn hợp lệ.

**Không nên nhầm:** có một `ListIterator` không có nghĩa code khác được phép sửa chính list bằng `list.add(...)` mà iterator sẽ luôn thích ứng. Việc cập nhật hợp lệ ở đây được thực hiện **qua cùng iterator**.

## 9. Cách xử lý đơn giản: `removeIf`

Với collection hỗ trợ xóa, API `removeIf(Predicate<? super E>)` thường giúp diễn đạt mục tiêu “xóa các phần tử thỏa điều kiện” rõ ràng hơn việc tự điều khiển iterator.

```java
List<Integer> numbers =
        new ArrayList<>(List.of(1, 2, 3, 4, 5));

numbers.removeIf(n -> n % 2 == 0);
System.out.println(numbers);
```

Mảnh code trong method có đầu ra:

```text
[1, 3, 5]
```

### 9.1. Java 17 — ví dụ `removeIf` có đầu ra xác định

Tạo **`RemoveIfDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class RemoveIfDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>(
                List.of("An", "Bình", "Chi", "Dũng"));

        boolean changed =
                names.removeIf(s -> s.length() <= 2);

        System.out.println("Changed: " + changed);
        System.out.println("Names: " + names);

        boolean changedAgain =
                names.removeIf(s -> s.startsWith("X"));
        System.out.println("Changed again: " + changedAgain);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 RemoveIfDemo.java
java RemoveIfDemo
```

Stdout:

```text
Changed: true
Names: [Bình, Chi, Dũng]
Changed again: false
```

**Giải thích:**

- `removeIf` gọi predicate cho các phần tử và loại những phần tử phù hợp.
- Ở ví dụ, `"An"` và `"Chi"` có số UTF-16 code units lần lượt là 2 và 3; điều kiện `length() <= 2` **chỉ xóa `"An"`**, không xóa `"Chi"`.
- Giá trị `changed` bằng `true` vì có phần tử được xóa.
- Lần hai không có tên bắt đầu bằng `X` nên `changedAgain` là `false`.
- API ngắn hơn vòng lặp thủ công và có cơ chế xóa phù hợp với implementation khi được dùng đúng hợp đồng.

**Chú ý:** kết quả `Names` ở ví dụ này được xác định theo phép kiểm tra ký tự; hãy dùng kết quả thật từ điều kiện, không suy tên tiếng Việt có hai/chỉ ba “chữ” theo trực giác. Nếu mục tiêu xóa các tên ngắn hơn bốn code units, predicate cần là `s.length() < 4`, và kết quả sẽ khác.

> Lưu ý khi học: `removeIf` **không có nghĩa predicate được phép sửa cấu trúc collection bằng cách khác**. Nếu bên trong predicate lại gọi `names.add(...)` hoặc `names.remove(...)`, code vẫn có thể gặp CME hoặc kết quả không xác định theo hợp đồng. Predicate nên thuần theo phần tử khi có thể.

## 10. “Không đổi size” có đảm bảo không CME?

**Không có quy tắc phổ quát cho mọi collection** rằng “hễ kích thước không đổi thì không thể CME”. Cần xem loại sửa đổi được implementation coi là structural hoặc invalidating iteration.

### 10.1. Với `ArrayList`: `set` chỉ thay giá trị

`ArrayList.set(index, element)` thay giá trị ở vị trí đã tồn tại mà không thay số phần tử. Trong `ArrayList` thông thường, việc gọi `set` không tăng dấu hiệu structural modification nên iterator không tự fail-fast **chỉ do `set`**.

Ví dụ:

```java
List<String> values =
        new ArrayList<>(List.of("A", "B", "C"));
Iterator<String> it = values.iterator();

values.set(1, "B2");
while (it.hasNext()) {
    System.out.println(it.next());
}
```

Đây là mảnh code minh họa. Với `ArrayList` của Java 17, có thể in `A`, `B2`, `C` mà không có CME.

Tuy nhiên:

- Việc nhìn thấy giá trị thay đổi giữa lúc duyệt không có nghĩa thao tác đa luồng đã an toàn.
- Những collection khác có hành vi iterator/metadata riêng.
- Thay đổi thứ tự phần tử bằng `sort` hoặc thay đổi cấu trúc có thể bị phát hiện khác với `set`, kể cả size không đổi.

### 10.2. Với `HashMap`: thay value cho key đã có khác với thêm/xóa key

Khi duyệt `HashMap.entrySet()`, thêm một **key mới** hoặc xóa một entry có thể làm iterator fail-fast. Nhưng `map.put(existingKey, newValue)` chỉ thay giá trị của một entry đã có, thông thường **không phải structural modification**.

Đây là phân biệt giữa *thay thế value* và *thêm/xóa mapping*, không phải lời hứa đồng bộ hóa trong môi trường nhiều thread.

## 11. Java 17 — ví dụ 5: `HashMap` cũng có iterator fail-fast

Tạo tệp **`HashMapCmeDemo.java`**:

```java
import java.util.ConcurrentModificationException;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;

public class HashMapCmeDemo {
    public static void main(String[] args) {
        Map<String, Integer> scores = new HashMap<>();
        scores.put("A", 10);
        scores.put("B", 20);

        Iterator<String> it = scores.keySet().iterator();
        System.out.println("Has first: " + it.hasNext());

        scores.put("C", 30); // Thêm key: sửa cấu trúc.

        try {
            it.next();
        } catch (ConcurrentModificationException e) {
            System.out.println("HashMap: "
                    + e.getClass().getSimpleName());
        }

        System.out.println("Size: " + scores.size());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 HashMapCmeDemo.java
java HashMapCmeDemo
```

Stdout trên `HashMap` JDK 17:

```text
Has first: true
HashMap: ConcurrentModificationException
Size: 3
```

**Tại sao ví dụ không in thứ tự key?** `HashMap` không bảo đảm thứ tự lặp key; nếu in chuỗi key theo iteration order, stdout có thể khác khi implementation hoặc dữ liệu thay đổi. Ở đây mục tiêu là kiểm tra CME sau thao tác `put` thêm key, không phụ thuộc thứ tự bucket.

### 11.1. Muốn xóa entry khi duyệt Map?

Có thể dùng iterator của `entrySet()` và `iterator.remove()` khi implementation hỗ trợ, hoặc dùng `map.entrySet().removeIf(predicate)` theo hợp đồng.

```java
Map<String, Integer> scores = new HashMap<>();
scores.put("A", 10);
scores.put("B", 20);

scores.entrySet().removeIf(e -> e.getValue() < 15);
System.out.println(scores.size()); // 1
```

Đây là mảnh code trong method. Đừng gọi `scores.remove(e.getKey())` trực tiếp trong enhanced-for của `scores.entrySet()` và mong iterator thích nghi.

## 12. Giới hạn lớn nhất: fail-fast là **best effort**

Tài liệu về các iterator fail-fast của collection chuẩn nhấn mạnh một ý quan trọng: **không thể bảo đảm phát hiện đồng thời không được đồng bộ hóa một cách chắc chắn**. Cơ chế fail-fast phải được dùng để **phát hiện bug**, không dùng để xây dựng logic chính xác của chương trình.

### 12.1. Những tình huống CME có thể không xuất hiện

1. Thao tác sửa diễn ra **trước khi iterator được tạo**: iterator mới thấy trạng thái đã sửa.
2. Thao tác không được coi là structural/invalidation với iterator cụ thể.
3. Iterator **không thực hiện thêm phép kiểm tra** sau khi sửa, ví dụ vòng lặp đã kết thúc hoặc `hasNext()` quyết định không còn phần tử.
4. Có thao tác sửa xen kẽ giữa các thread không có đồng bộ hóa đúng; kết quả nhìn thấy và việc kiểm tra không có bảo đảm phát hiện.
5. Collection sử dụng iterator snapshot/weakly consistent, không được thiết kế để ném CME vì các sửa đổi thường lệ.
6. Một API có cơ chế traversal hoặc spliterator khác với iterator mà bạn đang hình dung.

**Kết luận:** “không ném CME” không đồng nghĩa “code hợp lệ” hoặc “không có concurrent modification”. Những lần chạy khác nhau có thể cho kết quả khác nhau nếu chương trình có data race.

### 12.2. Không dùng CME như tín hiệu chính xác để retry

Anti-pattern:

```java
while (true) {
    try {
        traverse(sharedMutableList);
        break;
    } catch (ConcurrentModificationException ignored) {
        // Retry vô hạn với hy vọng cuối cùng không lỗi.
    }
}
```

Đây là mã minh họa, `traverse` và `sharedMutableList` chưa định nghĩa. Cách này có thể:

- Lặp vô hạn nếu collection liên tục bị sửa.
- Không phát hiện một số thay đổi bất đồng bộ vì CME chỉ best effort.
- Chạy lại thao tác có side effect, dẫn đến trùng lặp.
- Tạo CPU spin và làm system khó ổn định.
- Không tạo quan hệ memory visibility hoặc atomicity.

Nếu yêu cầu traversal nhất quán, dùng thiết kế có **khóa đúng**, **snapshot**, **immutable state**, hoặc collection/algorithm cung cấp semantics phù hợp.

## 13. Một tình huống tinh vi: xóa mà không thấy CME

`ArrayList` iterator trên JDK 17 thường kiểm tra thay đổi khi `next()`. `hasNext()` có thể chỉ so sánh cursor và size. Vì vậy đoạn dưới đôi khi **không ném CME**, dù sửa list trực tiếp trong vòng enhanced-for là cách làm sai.

Xem ví dụ có hai phần tử:

```java
List<String> names =
        new ArrayList<>(List.of("A", "B"));

for (String name : names) {
    if ("A".equals(name)) {
        names.remove("A");
    }
}
```

Đây là **mảnh code chỉ để phân tích**, không bảo đảm cùng hành vi trên mọi List. Sau khi xóa `A`, size giảm còn 1; iterator đã đi qua một phần tử nên cursor cũng bằng 1. Lời gọi `hasNext()` tiếp theo có thể trả `false` và vòng lặp kết thúc **mà không gọi thêm `next()` để kiểm tra modCount**.

Điều quan trọng:

- Việc không thấy exception **không làm đoạn code đúng**.
- Cơ chế có thể khác theo implementation và phiên bản.
- Nhiều bug tương tự tồn tại âm thầm cho đến khi dữ liệu hoặc thứ tự thay đổi.
- Đây là bằng chứng minh họa giới hạn *best effort*, không phải mẹo để tránh CME.

### 13.1. Java 17 — chương trình minh họa giới hạn kiểm tra

Tạo **`FailFastNotGuaranteedDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

public class FailFastNotGuaranteedDemo {
    public static void main(String[] args) {
        List<String> values =
                new ArrayList<>(List.of("A", "B"));

        Iterator<String> it = values.iterator();
        System.out.println("First: " + it.next());

        values.remove("A");

        System.out.println("Has next: " + it.hasNext());
        System.out.println("Contents: " + values);
    }
}
```

Chạy JDK 17:

```bash
javac -encoding UTF-8 FailFastNotGuaranteedDemo.java
java FailFastNotGuaranteedDemo
```

Stdout theo hành vi `ArrayList.Itr.hasNext` trên JDK 17:

```text
First: A
Has next: false
Contents: [B]
```

**Diễn giải:** `it` được tạo trước khi list sửa đổi, nhưng sau khi xóa A, `hasNext` thấy cursor bằng size và trả false. Code không gọi tiếp `next()`, nên không xuất hiện phép kiểm tra tiếp theo có thể báo CME. Nó chứng minh fail-fast **không bảo đảm phát hiện mọi sự thay đổi**, ngay khi chỉ có một thread.

Không chuyển hành vi riêng của JDK 17 thành một điều kiện để điều khiển nghiệp vụ. Nếu logic cần biết một list có bị sửa hay không, hãy sở hữu/truyền dữ liệu theo một hợp đồng nhất quán thay vì quan sát có/không có CME.

## 14. Duyệt snapshot: `CopyOnWriteArrayList`

`java.util.concurrent.CopyOnWriteArrayList` dùng cơ chế sao chép mảng nội bộ khi thực hiện các thao tác sửa đổi cấu trúc phù hợp. Iterator của nó làm việc với một **snapshot tại thời điểm tạo iterator**, không bị ảnh hưởng bởi các cập nhật sau đó và **không ném CME do các sửa đổi thường lệ** của list.

Điểm mạnh:

- Phù hợp với trường hợp **đọc rất nhiều, cập nhật ít**, ví dụ một danh sách listener tương đối nhỏ.
- Duyệt có view ổn định theo snapshot của iterator.
- Thao tác đọc/traversal không phải tranh cùng khóa với mọi lượt sửa theo cách synchronized list truyền thống.

Đổi lại:

- Việc cập nhật thường phải sao chép mảng, chi phí lớn với list to/cập nhật liên tục.
- Iterator snapshot **không phản ánh** cập nhật mới sau lúc iterator được tạo.
- `Iterator.remove()`, `set()` và `add()` không được hỗ trợ trên snapshot iterator, nên có thể ném `UnsupportedOperationException`.
- Iterator snapshot không phải một transaction toàn hệ thống; chỉ là view cụ thể của collection.

### 14.1. Java 17 — ví dụ snapshot iterator

Tạo **`CopyOnWriteSnapshotDemo.java`**:

```java
import java.util.Iterator;
import java.util.concurrent.CopyOnWriteArrayList;

public class CopyOnWriteSnapshotDemo {
    public static void main(String[] args) {
        CopyOnWriteArrayList<String> names =
                new CopyOnWriteArrayList<>();

        names.add("A");
        names.add("B");

        Iterator<String> snapshot = names.iterator();
        names.add("C");

        System.out.print("Snapshot:");
        while (snapshot.hasNext()) {
            System.out.print(" " + snapshot.next());
        }
        System.out.println();

        System.out.println("Current: " + names);

        try {
            snapshot.remove();
        } catch (UnsupportedOperationException e) {
            System.out.println("Iterator remove unsupported");
        }
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 CopyOnWriteSnapshotDemo.java
java CopyOnWriteSnapshotDemo
```

Stdout:

```text
Snapshot: A B
Current: [A, B, C]
Iterator remove unsupported
```

Dù `C` được thêm trước khi duyệt snapshot, iterator đã được **tạo trước đó**, nên chỉ nhìn thấy A và B. Đây là semantics có chủ đích của snapshot, không phải một failure bị lặng lẽ bỏ qua.

**Khi chọn:** tránh dùng CopyOnWriteArrayList cho workload ghi thường xuyên hoặc list lớn nếu chi phí copy đáng kể; đo đạc và kiểm tra use case. Cũng đừng nhầm “iterator không CME” với “mọi phép phối hợp nhiều thao tác giữa các thread đều atomic”.

## 15. Weakly consistent iterator: `ConcurrentHashMap`

`java.util.concurrent.ConcurrentHashMap` là map được thiết kế cho truy cập đồng thời. Iterator trên các view như `keySet()`, `values()`, `entrySet()` có semantics **weakly consistent**:

- Có thể duyệt trong khi map bị cập nhật.
- Không ném CME do các cập nhật đồng thời thông thường.
- **Không phải snapshot cố định**: iterator có thể nhìn thấy một số cập nhật trong quá trình duyệt.
- Không cam kết thấy **mọi** thay đổi xảy ra trong lúc duyệt.
- Không cung cấp một ảnh chụp giao dịch nhất quán của toàn map trong trường hợp có cập nhật song song.

Sự khác biệt với CopyOnWriteArrayList:

| Đặc điểm | `CopyOnWriteArrayList` iterator | `ConcurrentHashMap` iterator |
| --- | --- | --- |
| Kiểu consistency | Snapshot tại thời điểm tạo | Weakly consistent |
| Thấy phần tử mới được thêm sau khi tạo iterator? | Không | Có thể, không bảo đảm |
| CME do sửa collection thường lệ? | Không theo cơ chế snapshot | Không theo cơ chế weakly consistent |
| Chi phí update điển hình | Sao chép backing array | Cấu trúc concurrent map, chi phí khác |
| Có thể coi traversal là transaction toàn bộ dữ liệu? | Không | Không |
| Phù hợp nhất | Rất nhiều lượt đọc, ít sửa | Map nhiều thread cùng truy cập/cập nhật |

### 15.1. Java 17 — ví dụ không phụ thuộc thứ tự Map

Tạo **`ConcurrentHashMapIteratorDemo.java`**:

```java
import java.util.Iterator;
import java.util.concurrent.ConcurrentHashMap;

public class ConcurrentHashMapIteratorDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, Integer> counts =
                new ConcurrentHashMap<>();
        counts.put("A", 1);
        counts.put("B", 2);

        Iterator<String> it = counts.keySet().iterator();
        counts.put("C", 3);

        int seen = 0;
        while (it.hasNext()) {
            it.next();
            seen++;
        }

        System.out.println("Map size: " + counts.size());
        System.out.println("Seen between 0 and 3: "
                + (seen >= 0 && seen <= 3));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ConcurrentHashMapIteratorDemo.java
java ConcurrentHashMapIteratorDemo
```

Stdout:

```text
Map size: 3
Seen between 0 and 3: true
```

Chương trình không in một thứ tự key hoặc số entry bắt gặp cụ thể, vì điều quan trọng là API **không đảm bảo tập thay đổi mới xuất hiện đầy đủ trong traversal**. Dù ví dụ chỉ có một thread, nó đủ minh họa việc iterator CHM vẫn có thể duyệt sau khi map được cập nhật mà không được thiết kế để phát CME.

Không nên viết assert rằng `seen` phải bằng 3 sau khi thêm C **sau lúc tạo iterator**. Đó không phải điều contract weakly consistent hứa.

## 16. `Collections.synchronizedList`: iterator vẫn cần đồng bộ ngoài

`Collections.synchronizedList(...)` trả wrapper đồng bộ hóa nhiều thao tác riêng lẻ của list. Nhưng khi **duyệt bằng iterator** trong khi có những thao tác khác, tài liệu yêu cầu người dùng **tự đồng bộ hóa toàn bộ quãng iteration trên chính wrapper** nếu muốn loại trừ thay đổi chồng lấn.

Mẫu thường gặp:

```java
List<String> sync =
        Collections.synchronizedList(new ArrayList<>());

synchronized (sync) {
    Iterator<String> it = sync.iterator();
    while (it.hasNext()) {
        System.out.println(it.next());
    }
}
```

Đây là đoạn minh họa cần import `List`, `Collections`, `ArrayList` và `Iterator`. Quan trọng:

1. Bọc list bằng synchronized wrapper **không biến iterator thành snapshot**.
2. Các thao tác thêm/xóa khác phải **thực sự dùng cùng wrapper/khóa**, không truy cập backing list riêng bỏ qua wrapper.
3. Giữ khóa trong suốt việc tạo iterator và duyệt.
4. Nếu trong lúc giữ khóa chính thread đó tự sửa cấu trúc list bằng `sync.remove(...)` thay vì dùng iterator, vẫn có thể phát CME vì synchronized không “chữa” quy tắc iterator.
5. Lock ngăn thread khác sửa trong vùng được bảo vệ **khi tất cả bên tham gia tôn trọng cùng cơ chế**.

### 16.1. Java 17 — ví dụ an toàn theo cùng khóa

Tạo **`SynchronizedListTraversalDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;

public class SynchronizedListTraversalDemo {
    public static void main(String[] args) {
        List<Integer> sync = Collections.synchronizedList(
                new ArrayList<>(List.of(10, 20, 30)));

        synchronized (sync) {
            Iterator<Integer> it = sync.iterator();
            int sum = 0;
            while (it.hasNext()) {
                sum += it.next();
            }
            System.out.println("Sum: " + sum);
        }

        sync.add(40);
        synchronized (sync) {
            System.out.println("Size: " + sync.size());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 SynchronizedListTraversalDemo.java
java SynchronizedListTraversalDemo
```

Stdout:

```text
Sum: 60
Size: 4
```

Đây là demo một thread để nội dung chạy xác định; trong code đa thread, cả bên thêm/xóa và bên duyệt cần thống nhất khóa/ownership. Không nên mở lock rộng rồi gọi code bên ngoài không kiểm soát, bởi có thể tăng contention hoặc dẫn đến deadlock theo thiết kế tổng thể.

### 16.2. Vì sao không chỉ khóa từng lần `hasNext`/`next`?

Nếu mỗi thao tác có một vùng khóa riêng và giữa chúng thread khác được phép sửa list, iterator vẫn có thể bị invalidated. Để có một traversal không bị thay đổi cấu trúc xen vào, giữ cùng khóa trong **toàn bộ** quãng duyệt hoặc chụp một snapshot rồi lặp trên snapshot.

## 17. Cách dùng snapshot bất biến khi chỉ cần đọc nhất quán

Nếu dữ liệu không quá lớn và yêu cầu nhất quán theo một thời điểm cụ thể, có thể chụp danh sách:

```java
List<String> snapshot = List.copyOf(source);
for (String value : snapshot) {
    process(value);
}
```

Mảnh code minh họa này cần `source` và `process`, giả định không có phần tử `null` vì `List.copyOf` từ chối `null`. Sau khi snapshot tạo xong, thay đổi cấu trúc ở `source` không thay đổi danh sách snapshot. Nếu phần tử bên trong là object mutable thì `List.copyOf` **không deep-copy chúng**.

**Ranh giới quan trọng:** tạo snapshot từ một list đang bị thread khác sửa **không đồng bộ** vẫn là một vấn đề consistency/concurrency. Cần có giao thức đọc/chụp phù hợp: cùng khóa, publication an toàn hoặc nguồn concurrent với semantics chấp nhận được. `List.copyOf` không tự biến một thao tác đọc trên backing data-race thành ảnh chụp atomic hoàn hảo.

### 17.1. Snapshot vs locking vs concurrent collections

- **Snapshot:** phù hợp khi có thể chấp nhận dữ liệu tĩnh trong suốt một lần xử lý, muốn hạn chế lock ở giai đoạn duyệt.
- **Locking:** phù hợp khi cần một view nhất quán với các thao tác cập nhật dùng cùng cơ chế và có thể khóa toàn bộ quãng duyệt.
- **Concurrent collections:** phù hợp khi muốn đọc/ghi đồng thời theo các contract yếu hoặc mạnh khác nhau; cần đọc semantics cho từng operation.
- **Immutable/persistent data:** phù hợp khi thiết kế có thể trao bản dữ liệu không thay đổi giữa các thread, giúp loại bỏ một lớp bug về iterator.

Không có lựa chọn “an toàn nhất cho mọi ứng dụng”; consistency, tần suất cập nhật, kích thước dữ liệu và độ trễ đều ảnh hưởng.

## 18. `subList`: view và thay đổi backing list

`List.subList(from, to)` thường tạo một **view** dựa trên một list nguồn, không phải bản sao độc lập. Khi backing list bị sửa cấu trúc **ngoài phạm vi view hoặc không thông qua view theo đúng hợp đồng**, trạng thái sublist có thể trở nên không hợp lệ. Một số implementation phát CME khi phát hiện thay đổi này.

Ví dụ minh họa:

```java
List<String> original =
        new ArrayList<>(List.of("A", "B", "C", "D"));
List<String> view = original.subList(1, 3);

original.add("E"); // Thay đổi backing list không qua view.

// Các thao tác tiếp theo trên view có thể thất bại hoặc
// có hành vi ngoài hợp đồng subList; không tiếp tục sử dụng như bình thường.
```

Đây là mảnh code trong method. Đừng xem CME khi dùng `subList` là “trùng hợp đa luồng”. Ngay trong một thread, backing list thay đổi sau lúc view được tạo đã đủ tạo điều kiện vi phạm.

### 18.1. Muốn list độc lập hãy tạo bản sao

```java
List<String> snapshot =
        new ArrayList<>(original.subList(1, 3));
```

Đây là bản sao cấu trúc danh sách tại thời điểm tạo, khác với view gắn với backing list. Với object mutable, những phần tử vẫn có thể là tham chiếu chung, nên không có nghĩa deep copy.

**Lưu ý chính xác về hợp đồng:** Tài liệu `List.subList` nói semantics của list trả về có thể **không được xác định** nếu backing list bị sửa cấu trúc theo cách không qua sublist. CME là một kết quả có thể thấy trên một implementation cụ thể, không phải ngoại lệ được bảo đảm trong mọi tình huống.

## 19. Stream, spliterator và callback sửa nguồn

Một Stream có thể được tạo từ collection:

```java
List<Integer> values = new ArrayList<>(List.of(1, 2, 3, 4));

values.stream().forEach(v -> {
    if (v == 2) {
        values.add(5);
    }
});
```

Đây là **anti-pattern**, không phải code được khuyến nghị. Callback sửa chính nguồn dữ liệu khi pipeline đang duyệt có thể vi phạm quy tắc **non-interference** của Stream. Tùy pipeline và implementation, có thể xuất hiện CME, phần tử bị bỏ sót/lặp, hoặc kết quả khó dự đoán; không xem một kiểu lỗi duy nhất là bảo đảm.

### 19.1. Stream có luôn fail-fast không?

Không. Stream dùng cơ chế spliterator và pipeline, các đặc tính thực tế phụ thuộc nguồn và loại operation:

- Nguồn có tính `IMMUTABLE` hoặc `CONCURRENT` có contract khác với `ArrayList`.
- Một số spliterator có đặc tính late-binding hoặc kiểm tra tại những thời điểm khác nhau.
- Với stream song song, thời điểm các worker quan sát thay đổi càng khó đoán.
- Không thể suy “mọi stream sửa nguồn sẽ ném CME” hoặc “nếu không ném CME thì kết quả đúng”.

**Giải pháp thường tốt:** xây một danh sách kết quả mới bằng `filter`/`map` rồi sử dụng kết quả đó, hoặc hoàn tất traversal trước khi sửa collection gốc. Với collection mutable, `removeIf` thường thích hợp hơn để xóa theo predicate.

### 19.2. Mẫu tạo kết quả mới không sửa nguồn

```java
List<Integer> source = List.of(1, 2, 3, 4);
List<Integer> odds = source.stream()
        .filter(v -> v % 2 != 0)
        .toList();

System.out.println(odds); // [1, 3]
```

Đây là đoạn trong method, dùng Java 16+ `Stream.toList()` (có ở Java 17). Danh sách kết quả của `toList()` là unmodifiable theo hợp đồng; không nên mặc định có thể `add` vào nó.

### 19.3. Mutating predicate cũng có rủi ro

`list.removeIf(x -> { list.add(...); return ...; })` cũng là cách vừa duyệt vừa sửa nguồn ngoài cơ chế mà implementation `removeIf` quản lý. Predicate được thiết kế để **quyết định xóa** phần tử, không để sửa cấu trúc list trên đường chạy của predicate. Nếu cần side effect phức tạp, tách các pha rõ ràng để dễ kiểm thử.

## 20. `HashMap`, `HashSet` và `LinkedHashMap`: không chỉ List

Trong `java.util`, nhiều collection truyền thống cung cấp iterator fail-fast, ví dụ `ArrayList`, `HashMap`, `HashSet` và `LinkedHashMap`. Nhưng luôn đọc contract của implementation cụ thể.

- `HashSet` thường được backing bởi cấu trúc hash; thêm/xóa phần tử có thể làm iterator cũ không còn hợp lệ.
- `HashMap` có key/value/entry views; thay đổi mapping cấu trúc của map tác động lên iterator của các view này.
- `LinkedHashMap` có thứ tự duyệt và có mode access-order; trong cấu hình access-order, một số thao tác truy cập có thể thay đổi thứ tự cấu trúc, khiến iterator bị invalidated theo hợp đồng.
- Đừng dùng “không thay đổi số phần tử” làm tiêu chuẩn duy nhất để suy một iterator an toàn với mọi collection.

### 20.1. Access-order `LinkedHashMap` là trường hợp đáng chú ý

Nếu cấu hình `LinkedHashMap` kiểu **access-order** để làm LRU, thao tác `get(key)` có thể làm đổi thứ tự iteration. Trong implementation này, một thao tác “chỉ đọc value” có thể kéo theo thay đổi cấu trúc theo nghĩa ảnh hưởng iteration.

Vì vậy ngay cả khi không gọi `add/remove`, cần đọc contract về iteration order và structural modification. Không được khái quát từ `ArrayList.set` sang `LinkedHashMap.get` trong access-order mode.

### 20.2. Một số phương thức sửa đổi hợp lệ khác nhau giữa Map và Iterator

`Map.replace(key, value)` hoặc `entry.setValue(...)` có thể thay value của entry mà không sửa tập key; điều đó khác với `put` thêm key mới. Nhưng nếu có cấu trúc access-order, mutable view hoặc tùy implementation, tác động lên iteration có thể khác. Muốn code portable, dựa trên API contract của collection thay vì suy từ tên method.

## 21. CME không phải công cụ khóa hay cơ chế kiểm soát tính đúng

Một code review tốt nên đặt câu hỏi:

1. Có bao nhiêu **thread** có thể truy cập collection?
2. Ai **sở hữu** collection? Có chia sẻ tham chiếu mutable không?
3. Iterator được tạo ở đâu và còn sống đến khi nào?
4. Ai có quyền thêm/xóa/sắp xếp trong khi iterator đang duyệt?
5. Có yêu cầu **snapshot nhất quán** hay chỉ cần quan sát gần thời gian thực?
6. Có cần **atomicity** qua nhiều thao tác, ví dụ kiểm tra rồi cập nhật?
7. Sửa collection có side effect ngoài container không?
8. Có thể tách pha **duyệt/tính toán** và **thực hiện thay đổi** được không?
9. Nếu chuyển sang concurrent collection, contract về iteration consistency có chấp nhận được không?
10. Test nào chứng minh hành vi có ý nghĩa, không chỉ chứng minh “không thấy CME”?

Cách tiếp cận hướng contract tốt hơn một “try/catch CME” chung cho mọi collection.

## 22. Những lỗi thường gặp và cách sửa

| Nhầm lẫn | Vấn đề | Cách làm hợp lý |
| --- | --- | --- |
| “CME chỉ có khi hai thread cùng chạy.” | Một thread cũng có thể sửa list ngoài iterator. | Kiểm tra logic lặp và cách sửa. |
| “CME là checked exception.” | Nó kế thừa `RuntimeException`. | Không cần khai báo bắt buộc; sửa bug ở nguồn. |
| “Không có CME nên thread-safe.” | Fail-fast chỉ best effort; một số iterator không fail-fast. | Khóa, ownership, snapshot, concurrent contract. |
| “Mọi collection đều có `modCount`.” | Đó là chi tiết triển khai của một số class. | Đọc hợp đồng iterator cụ thể. |
| “Mọi `hasNext()` đều kiểm tra sửa đổi.” | Không được bảo đảm; ArrayList có thể bỏ qua. | Không dựa vào CME để phát hiện mọi thay đổi. |
| “Sửa size bằng 0 thì iterator chắc an toàn.” | Thứ tự hay trạng thái nội bộ cũng có thể bị invalidated. | Xét structural modification theo class/API. |
| “Dùng `list.remove(...)` trong for-each là ổn nếu chạy thử không lỗi.” | Có thể chỉ tình cờ thoát trước lần kiểm tra tiếp. | Dùng `Iterator.remove()` hoặc `removeIf`. |
| “`Iterator.remove` được gọi bất kỳ lúc nào.” | Có state machine và optional operation. | Gọi sau `next`, một lần mỗi lượt phù hợp. |
| “`removeIf` cho phép predicate tự thêm/xóa list.” | Có thể vi phạm semantics của traversal. | Giữ predicate đơn giản và không sửa nguồn. |
| “`Collections.synchronizedList` làm iterator tự an toàn.” | Iteration cần khóa ngoài xuyên suốt quãng duyệt. | `synchronized(list) { ... iterator ... }`. |
| “Chỉ khóa `next()` từng lượt là đủ.” | Thread khác sửa giữa các lượt. | Khóa cả traversal hoặc dùng snapshot. |
| “CopyOnWrite iterator thấy cập nhật mới.” | Nó duyệt snapshot lúc tạo. | Chọn semantics snapshot có chủ đích. |
| “CopyOnWrite iterator hỗ trợ `remove`.” | Iterator snapshot không hỗ trợ sửa trực tiếp. | Sửa qua list hoặc chiến lược phù hợp. |
| “ConcurrentHashMap iterator có ảnh chụp đúng một thời điểm.” | Nó weakly consistent, không transactional snapshot. | Chọn algorithm tương ứng. |
| “Đổi ArrayList sang concurrent collection luôn chữa được logic.” | Semantics về ordering, consistency, cost khác nhau. | Định nghĩa yêu cầu rồi chọn collection. |
| “Nếu Stream không CME thì side effects đúng.” | Non-interference có thể bị vi phạm. | Tách source và result, dùng filter/removeIf đúng chỗ. |
| “`subList` là bản sao độc lập.” | Nó thường là view của backing list. | Copy nếu cần độc lập. |
| “CME tự rollback thao tác đã xảy ra.” | Exception không hoàn tác. | Thiết kế transaction/compensation nếu cần. |
| “Có thể catch rồi retry vô hạn.” | Có thể spin, lặp side effect, vẫn không bảo đảm consistency. | Thiết kế đồng bộ hoặc snapshot đúng. |
| “`List.set` luôn gây CME như `add`.” | ArrayList.set không đổi cấu trúc và thường không làm invalidation. | Phân biệt mutation nội dung vs structural. |
| “`HashMap.put` luôn structural.” | Thay value cho key đã có khác thêm mapping. | Xét có thêm/xóa key hay không. |

## 23. Kỹ năng debug khi gặp `ConcurrentModificationException`

Khi stack trace báo CME:

1. **Tìm chính xác collection** đang được duyệt, không chỉ xem tên class ở đầu trace.
2. Xác định kiểu traversal: enhanced for, `Iterator`, `ListIterator`, `forEach`, stream/spliterator hay view từ `subList`.
3. Tìm **thao tác sửa cấu trúc** có thể diễn ra giữa lúc tạo iterator và lúc kiểm tra: `add`, `remove`, `clear`, `sort`, method gọi gián tiếp, callback hay thread khác.
4. Xem các thao tác sửa có đi qua **chính iterator** hay không.
5. Nếu có nhiều thread, xác minh **cùng một khóa** hay concurrent collection phù hợp; không chỉ bọc catch.
6. Nếu dùng `subList`, xác định backing list có bị sửa cấu trúc trực tiếp không.
7. Nếu dùng access-order `LinkedHashMap`, xem liệu `get` có thay iteration order không.
8. Kiểm tra quyền sở hữu, lifecycle và alias: cùng list có thể được truyền qua nhiều method/tầng.
9. Tạo test đơn thread có thể tái hiện đường sửa sai nếu bug thuần logic; với concurrency dùng test/stress test phù hợp nhưng **không** dựa vào một lần “không CME” để kết luận an toàn.
10. Sửa invariant, chọn API xóa đúng, snapshot hoặc synchronization; kiểm tra trạng thái/side effect sau lỗi.

### 23.1. Vì sao stack trace thường chỉ vào `next()`?

CME có thể được ném **tại chỗ phát hiện**, không phải đúng dòng đầu tiên làm thay đổi collection. Stack trace có thể chỉ vào `ArrayList$Itr.next`, trong khi thao tác sai `list.add/remove` đã xảy ra ở dòng khác trước đó.

Vì vậy cần truy ngược đường sửa cấu trúc, không kết luận `next()` là “hàm sai” hoặc JDK bị lỗi. Nếu thay đổi đến từ callback sâu hay thread khác, quan sát ownership và log ngữ cảnh có thể quan trọng hơn xem một dòng stack đơn lẻ.

### 23.2. Logging nên ghi gì?

Có thể ghi tên thao tác, loại collection, kích thước tại vị trí an toàn, ID tác vụ/correlation id và exception, nhưng không cần dump toàn bộ collection chứa dữ liệu nhạy cảm. Với lỗi concurrency, log thứ tự sự kiện có ngữ cảnh giúp tái hiện hơn là chỉ message của CME (thường không chứa nhiều chi tiết).

## 24. Kiểm thử và chứng minh hành vi

Một số hướng test:

- **Iterator invalidation đơn thread:** tạo `ArrayList` iterator, gọi `next()`, sửa cấu trúc, rồi gọi `next()`; trên JDK 17 kỳ vọng CME ở demo có kiểm soát.
- **Iterator.remove:** xác minh đúng tập phần tử sau khi xóa và không cần catch.
- **ListIterator:** xác minh thêm/sửa qua iterator với list mutable.
- **removeIf:** xác minh predicate lọc đúng, không có side effect ngoài dự kiến.
- **CopyOnWriteArrayList:** tạo iterator, thêm mới rồi kiểm tra snapshot không thấy phần tử mới.
- **ConcurrentHashMap:** kiểm tra các phép đồng thời hợp lệ theo API, **không assert thứ tự hoặc việc iterator phải thấy toàn bộ cập nhật xen giữa**.
- **synchronizedList:** dùng test thiết kế cùng khóa, không coi việc không có CME trong stress test là bằng chứng duy nhất.
- **Stream:** kiểm thử kết quả lọc/tính toán, tránh các callback sửa source.

### 24.1. Ví dụ JUnit 5 minh họa

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;
import org.junit.jupiter.api.Test;

class FailFastContractTest {
    @Test
    void iteratorDetectsDirectStructuralChangeOnArrayListJdk17() {
        List<String> values =
                new ArrayList<>(List.of("A", "B", "C"));
        Iterator<String> it = values.iterator();
        assertEquals("A", it.next());
        values.add("D");

        assertThrows(ConcurrentModificationException.class, it::next);
    }

    @Test
    void iteratorRemoveIsLegal() {
        List<Integer> values =
                new ArrayList<>(List.of(1, 2, 3, 4));
        Iterator<Integer> it = values.iterator();

        while (it.hasNext()) {
            if (it.next() % 2 == 0) {
                it.remove();
            }
        }

        assertEquals(List.of(1, 3), values);
    }
}
```

Đây là **file test dành cho JUnit Jupiter**, không phải chương trình `javac` chạy độc lập chỉ với JDK. Test thứ nhất cố tình kiểm chứng hành vi `ArrayList` JDK 17 trong hoàn cảnh cụ thể; **không có nghĩa mọi collection fail-fast trên mọi JVM buộc phải ném CME trong mọi lịch thực thi**.

### 24.2. Test concurrency không giống xác minh hợp đồng concurrency

Một stress test chạy thành công nhiều lần vẫn không đủ chứng minh code có data race là đúng. Phải đối chiếu với **Java Memory Model**, bảo đảm đồng bộ và hợp đồng collection. Nếu cần tính chính xác cao, thiết kế bằng invariant, ownership, atomic operations hoặc cấu trúc concurrent phù hợp trước, rồi dùng test để phát hiện sai sót.

## 25. Các câu hỏi thường gặp

**1. Vì sao một thread vẫn gây CME?** Vì code có thể sửa cấu trúc `ArrayList` bên ngoài iterator đang duyệt ngay trong một thread. “Concurrent” trong tên không yêu cầu có hai thread.

**2. Thêm `synchronized` có luôn chữa CME?** Không. Khóa đúng cách giúp các thread phối hợp, nhưng cùng thread gọi `list.remove(...)` trong lúc duyệt bằng iterator vẫn có thể phá hợp đồng; khi được hỗ trợ, dùng `Iterator.remove()`.

**3. Vì sao đôi lúc có CME, đôi lúc không?** Phát hiện fail-fast chỉ mang tính **best effort**; vị trí cursor, lượt kiểm tra và tình huống đồng thời ảnh hưởng việc phát hiện. Không dùng exception làm test tính đúng duy nhất.

**4. Có thể catch CME rồi khởi tạo iterator mới và retry?** Chỉ nếu đã xác định tính nhất quán dữ liệu, side effect và khả năng retry; đó không phải giải pháp mặc định thay cho ownership hoặc đồng bộ hóa.

**5. `ArrayList.set` có luôn invalidated iterator?** Không. Trên `ArrayList`, thay phần tử đã có thường không phải sửa cấu trúc; điều này **không** tạo bảo đảm thread-safe.

**6. `removeIf` có áp dụng cho mọi collection?** Không. Collection không hỗ trợ xóa có thể ném `UnsupportedOperationException`; predicate cũng không nên tự sửa nguồn đang duyệt.

**7. Snapshot và weakly consistent có giống nhau?** Không. `CopyOnWriteArrayList` iterator dùng snapshot tại lúc tạo, còn iterator của `ConcurrentHashMap` có thể quan sát một phần cập nhật xen kẽ. “Fail-safe” không phải tên hợp đồng chính thức của hai kiểu iterator đó.

**8. Fail-fast có phát hiện đầy đủ data race?** Không. Việc có hay không có CME không thay thế các quy tắc Java Memory Model, khóa và publication đúng.

**9. Dùng `Collections.synchronizedList` hay `CopyOnWriteArrayList`?** Chọn theo tần suất đọc/ghi, chi phí copy và tính nhất quán cần có; với synchronized list vẫn cần khóa **suốt thời gian traversal** bằng iterator.

**10. Vì sao `subList` liên quan CME?** `subList` thường là view của backing list; sửa cấu trúc backing list ngoài cơ chế được hỗ trợ có thể làm view/iterator không còn hợp lệ.

**11. `filter` và `removeIf` khác nhau?** `filter` mô tả chọn phần tử để tạo pipeline/kết quả, trong khi `removeIf` sửa nguồn khi collection hỗ trợ thao tác; không can thiệp cấu trúc nguồn từ callback Stream.

**12. CME có tự rollback thao tác trước đó không?** Không. Kiểm tra state đã thay đổi; ví dụ thao tác `add` có thể hoàn tất trước khi lần kiểm tra iterator tiếp theo ném CME.

Các câu trả lời tóm tắt ở đây cần được hiểu cùng mô hình iterator, độ nhất quán và ví dụ đã phân tích ở những mục trước; không dùng chúng thay cho kiểm thử hợp đồng của collection cụ thể.

## 26. Bài tập tự luyện

### Bài 1 — Một thread có CME

Chạy `SingleThreadCmeDemo` và vẽ thứ tự tạo iterator → next → add → next. Vì sao việc có một thread không tránh CME? **Gợi ý:** iterator đã ghi nhận cấu trúc cũ và bị sửa ngoài cơ chế của nó.

### Bài 2 — Sửa đúng bằng iterator

Chuyển đoạn for-each xóa tên khỏi list sang `Iterator.remove()`. Test danh sách có 0, 1, 2 và nhiều phần tử. Kiểm tra trường hợp xóa phần tử đầu, giữa và cuối.

### Bài 3 — Dùng `ListIterator`

Mở rộng `ListIteratorEditDemo`: thay `A` thành `A-done`, chèn thêm `B-extra` sau B, rồi xóa C bằng `it.remove()` sau khi `next()` trả C. Dự đoán danh sách cuối và chạy xác minh.

### Bài 4 — `removeIf` không phụ thuộc text fail-fast

Dùng `List.of("An","Bình","Chi","Dũng")` làm đầu vào, tạo mutable copy rồi xóa những chuỗi có `length() <= 2`. Dự đoán chính xác tập còn lại theo `String.length()`, không đếm ký tự trực quan.

### Bài 5 — Tìm bug “không CME”

Chạy `FailFastNotGuaranteedDemo`. Giải thích vì sao `hasNext()` có thể trả false sau khi xóa phần tử đầu tiên và vì sao đây là bằng chứng **không được phụ thuộc vào fail-fast để validate cấu trúc**.

### Bài 6 — Snapshot iterator

Chạy `CopyOnWriteSnapshotDemo`. Thêm D sau khi tạo iterator và trước khi duyệt. Snapshot có thấy D không? Còn list hiện tại có không? Thử `snapshot.remove()` và dự đoán loại exception.

### Bài 7 — Weak consistency

Dùng `ConcurrentHashMap`, tạo iterator rồi thêm key. Viết test chỉ kiểm tra các bảo đảm API thật sự có, **không assert số key mới phải được quan sát** trong traversal diễn ra cùng lúc cập nhật.

### Bài 8 — Lock đủ phạm vi

Cho một `Collections.synchronizedList`, hai thread: một duyệt, một sửa. Viết ví dụ mà cả hai tuân `synchronized(syncList)`. Vì sao khóa từng lệnh `next()` tách biệt không tương đương khóa toàn bộ traversal?

### Bài 9 — `HashMap` value vs structural

Tạo `HashMap` với hai key, tạo iterator, sau đó `put` lại key có sẵn với value mới và quan sát. So sánh với việc thêm key mới. Giải thích dựa trên structural modification của Map, không dựa vào “put luôn nguy hiểm”.

### Bài 10 — Stream và non-interference

Viết một pipeline `source.stream().filter(...).toList()` để tạo danh sách chỉ có số lẻ. So sánh với callback `forEach` cố sửa chính `source` trong lúc duyệt. Tại sao chỉ một trong hai là lựa chọn phù hợp khi muốn giữ source không thay đổi?

### Bài 11 — Concurrency và consistency

Một dịch vụ có danh sách listener cập nhật rất hiếm nhưng được duyệt hàng nghìn lần mỗi giây. So sánh `CopyOnWriteArrayList` với synchronized list: chi phí mỗi update, consistency của iterator và cách quản lý lock.

### Bài 12 — Bug từ view

Tạo `subList` từ một `ArrayList`, sau đó thay đổi backing list trực tiếp và thử đọc view. Giải thích vì sao code không được xem hành vi hoặc CME cụ thể là hợp đồng portable; đề xuất snapshot khi cần view độc lập.

## 27. Checklist trước khi kết luận một đoạn code an toàn

- [ ] Tôi đã phân biệt CME là unchecked runtime exception, không bắt buộc `throws` chưa?
- [ ] Tôi biết một thread cũng có thể phát CME khi sửa collection ngoài iterator chưa?
- [ ] Tôi hiểu fail-fast dùng phát hiện bug **best effort**, không phải bảo đảm 100% chưa?
- [ ] Tôi có biết iterator/collection hiện tại thuộc loại fail-fast, snapshot hay weakly consistent không?
- [ ] Tôi đã xác định đúng structural modification cho implementation đó chưa?
- [ ] Tôi không gọi `list.add/remove` trực tiếp trong enhanced-for của cùng list chứ?
- [ ] Nếu phải xóa khi duyệt, tôi dùng `Iterator.remove` khi được hỗ trợ và đúng trạng thái chưa?
- [ ] Nếu chèn/sửa trong khi duyệt list, tôi cân nhắc `ListIterator` phù hợp chưa?
- [ ] Nếu mục tiêu là xóa theo điều kiện, `removeIf` có hợp đồng phù hợp với mutable list không?
- [ ] Tôi không dùng CME để điều khiển retry vô hạn, đo data race hay chứng minh thread safety chứ?
- [ ] Tôi nhớ `modCount/expectedModCount` là chi tiết triển khai, không phải public contract chung chưa?
- [ ] Tôi đã xét đường `hasNext()` kết thúc trước kiểm tra thay đổi tiếp theo chưa?
- [ ] Nếu dùng `CopyOnWriteArrayList`, tôi chấp nhận snapshot cũ và chi phí copy khi sửa chứ?
- [ ] Nếu dùng `ConcurrentHashMap`, tôi không giả iterator luôn thấy mọi update xen giữa chưa?
- [ ] Nếu dùng `Collections.synchronizedList`, tôi giữ khóa xuyên suốt quãng duyệt và mọi writer cùng tuân khóa chưa?
- [ ] Nếu chụp snapshot, tôi bảo đảm tạo snapshot từ nguồn có trạng thái nhất quán chưa?
- [ ] Tôi không sửa backing list ngoài hợp đồng khi còn dùng `subList` chưa?
- [ ] Với Stream, callback của tôi không can thiệp sửa cấu trúc của source trong lúc pipeline xử lý chứ?
- [ ] Khi CME phát sinh, tôi kiểm tra side effect và không giả dữ liệu tự rollback chứ?
- [ ] Tôi đã test contract/hành vi cần thiết thay vì chỉ test “không ném CME” chưa?

**Kết luận:** `ConcurrentModificationException` là **một tín hiệu phát hiện bất nhất trong một số cơ chế duyệt**, không phải bằng chứng có hai thread và cũng không phải hệ thống đảm bảo phát hiện mọi sửa đổi. Fail-fast hoạt động theo *best effort*. Hãy chọn đúng công cụ: `Iterator.remove()`, `ListIterator` hoặc `removeIf` để chỉnh sửa hợp lệ; `CopyOnWriteArrayList` cho snapshot khi nhiều đọc ít ghi; `ConcurrentHashMap` cho traversal weakly consistent; đồng bộ toàn bộ iteration khi dùng `Collections.synchronizedList`. Quan trọng nhất là thiết kế **ownership, tính nhất quán và hợp đồng concurrency**, không bao giờ dùng việc có hoặc không có CME làm thước đo duy nhất cho correctness.