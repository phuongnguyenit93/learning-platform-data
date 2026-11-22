# Collections.synchronizedList, synchronizedSet và synchronizedMap

## 1. Lớp bao đồng bộ giải quyết việc truy cập collection như thế nào?

Khi nhiều luồng thực thi cùng sử dụng một collection thông thường, việc một luồng thêm hoặc xóa trong lúc luồng khác truy cập có thể làm chương trình không còn đáp ứng hợp đồng của cấu trúc đó. Một cách tổ chức là đặt các thao tác truy cập sau cùng một cơ chế khóa.

Ba phương thức của `Collections` tạo lớp bao cho mục đích này:

| Phương thức | Nhận cấu trúc nền | Trả về |
| --- | --- | --- |
| `synchronizedList(list)` | Một `List<E>` | `List<E>` có các thao tác truy cập trực tiếp được đồng bộ |
| `synchronizedSet(set)` | Một `Set<E>` | `Set<E>` có các thao tác truy cập trực tiếp được đồng bộ |
| `synchronizedMap(map)` | Một `Map<K,V>` | `Map<K,V>` có các thao tác truy cập trực tiếp được đồng bộ |

Lớp bao vẫn dùng cấu trúc nền đã truyền vào. Nó không chuyển mọi phần tử sang một collection độc lập và không làm các đối tượng phần tử tự trở thành an toàn đồng thời.

Mô hình cần hiểu là:

```text
Các bên sử dụng
      ↓
Một lớp bao đồng bộ được chia sẻ
      ↓
Cùng cơ chế khóa cho các thao tác phù hợp
      ↓
Collection nền
```

Những thao tác trực tiếp như `list.add`, `set.add` hoặc `map.put` đi qua lớp bao. Nhưng một thuật toán gồm nhiều lời gọi, hoặc một quá trình duyệt qua iterator, không tự trở thành một khối thao tác nguyên vẹn chỉ vì collection đã được bao.

Vì thế có ba cấp cần phân biệt:

1. **Một thao tác truy cập trực tiếp được đồng bộ.**
2. **Một chuỗi thao tác nghiệp vụ cần cùng nằm trong một vùng khóa.**
3. **Một lần duyệt cần được bảo vệ suốt thời gian sử dụng bộ duyệt.**

Bài này lần lượt kiểm chứng ba cấp đó cho List, Set và Map. Các chương trình dùng Java 17, có tên tệp, lệnh biên dịch và stdout để chạy lại độc lập.

## 2. Tạo một lớp bao và thống nhất đường truy cập

Cách khởi tạo minh họa, đặt trong phương thức có các `import` tương ứng:

```java
List<String> names = Collections.synchronizedList(new ArrayList<>());
Set<String> codes = Collections.synchronizedSet(new HashSet<>());
Map<String, Integer> counts = Collections.synchronizedMap(new HashMap<>());
```

Cấu trúc nền được tạo trực tiếp bên trong lời gọi để giảm việc giữ lại tham chiếu khác có thể bỏ qua lớp bao.

Hợp đồng của các phương thức nhấn mạnh rằng mọi truy cập tới cấu trúc nền phải đi qua lớp bao được trả về. Nếu vẫn sửa một `ArrayList` nền qua tham chiếu cũ trong khi bên khác dùng lớp bao, không còn cùng một chính sách bảo vệ. [Javadoc synchronizedList, synchronizedSet và synchronizedMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html)

### Lớp bao không thay đổi mọi tính chất của cấu trúc nền

Ví dụ:

- `synchronizedList(new ArrayList<>())` vẫn có ý nghĩa danh sách, giữ phần tử trùng và thứ tự chỉ số.
- `synchronizedSet(new HashSet<>())` vẫn có quy tắc phần tử duy nhất của tập băm và không được bảo đảm thứ tự duyệt.
- `synchronizedMap(new HashMap<>())` vẫn dùng quy tắc khóa của map băm.
- Khả năng chứa `null` hoặc hỗ trợ một thao tác sửa cụ thể còn phụ thuộc cấu trúc nền.
- Bao một danh sách vốn không cho sửa không tự làm `add` trở thành thao tác được hỗ trợ.

“Được đồng bộ” và “cho phép sửa” là hai tính chất khác nhau.

### Đừng tạo hai lớp bao độc lập trên cùng một cấu trúc nền

Đoạn dưới minh họa một thiết kế không đáp ứng yêu cầu dùng chung khóa; không phải chương trình mẫu để sử dụng:

```java
List<String> raw = new ArrayList<>();
List<String> first = Collections.synchronizedList(raw);
List<String> second = Collections.synchronizedList(raw);
```

`first` và `second` là hai lớp bao độc lập. Các thao tác đi qua hai đối tượng đó không được bảo vệ bởi cùng monitor chỉ vì cùng tham chiếu tới `raw`.

Tương tự, khóa trên `raw` không thay thế cho khóa mà các thao tác qua lớp bao đang sử dụng. Cần một đường truy cập và một chính sách khóa nhất quán, thay vì mỗi bên tự bao hoặc tự chọn đối tượng khóa.

Nếu muốn tiếp nhận dữ liệu ban đầu rồi sở hữu cấu trúc riêng, có thể tạo bản sao nền trước khi bao. Bản sao đó vẫn phải được tạo tại thời điểm việc đọc dữ liệu đầu vào hợp lệ; lớp bao không sửa được một quá trình sao chép vốn đang bị can thiệp.

## 3. Thí nghiệm các thao tác trực tiếp trên ba lớp bao

Lưu vào `SynchronizedWrappersDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class SynchronizedWrappersDemo {
    public static void main(String[] args) throws InterruptedException {
        List<Integer> list = Collections.synchronizedList(new ArrayList<>());
        Set<Integer> set = Collections.synchronizedSet(new HashSet<>());
        Map<Integer, Integer> map = Collections.synchronizedMap(new HashMap<>());

        Runnable write = () -> {
            for (int i = 0; i < 200; i++) {
                list.add(i);
                set.add(i);
                map.put(i, i * 2);
            }
        };
        Thread first = new Thread(write);
        Thread second = new Thread(write);
        first.start();
        second.start();
        first.join();
        second.join();

        int listSum;
        synchronized (list) {
            listSum = list.stream().mapToInt(Integer::intValue).sum();
        }
        TreeSet<Integer> sortedSet;
        synchronized (set) {
            sortedSet = new TreeSet<>(set);
        }

        System.out.println("listSize=" + list.size());
        System.out.println("listSum=" + listSum);
        System.out.println("setSize=" + set.size());
        System.out.println("setFirstForDisplay=" + sortedSet.first());
        System.out.println("setLastForDisplay=" + sortedSet.last());
        System.out.println("mapSize=" + map.size());
        System.out.println("mapValue199=" + map.get(199));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SynchronizedWrappersDemo.java
java SynchronizedWrappersDemo
```

Stdout:

```text
listSize=400
listSum=39800
setSize=200
setFirstForDisplay=0
setLastForDisplay=199
mapSize=200
mapValue199=398
```

Hai luồng thực thi đều đưa các số từ 0 đến 199 vào ba cấu trúc:

- List nhận hai lần mỗi số, nên có 400 phần tử; tổng là `2 × (0 + ... + 199) = 39800`.
- Set chỉ giữ một lần mỗi số, nên có 200 phần tử.
- Map có 200 khóa; hai bên ghi cùng giá trị `i * 2` cho mỗi khóa nên khóa 199 có giá trị 398.

Chương trình không dự đoán thứ tự hai luồng xen kẽ khi thêm vào List. Nó cũng không dự đoán thứ tự duyệt của `HashSet`. Hai giá trị đầu và cuối được in từ một `TreeSet` bản sao tạo riêng để hiển thị có thứ tự.

Việc tạo bản sao tập được đặt trong `synchronized (set)`, vì quá trình đọc các phần tử để sao chép là một lần duyệt. Phép tính tổng stream cũng nằm trọn trong `synchronized (list)`.

Các lời gọi `join()` chờ hai luồng ghi kết thúc trước khi in kết quả tổng hợp. Nhờ vậy stdout không mô tả một trạng thái nửa chừng khi bên ghi vẫn còn chạy.

### Ba cấu trúc không tự trở thành một giao dịch chung

Mỗi lớp bao có cơ chế khóa của nó. Ba câu lệnh thêm vào List, Set và Map trong thân vòng lặp không phải một giao dịch bao trùm cả ba cấu trúc.

Ví dụ, khi các luồng còn đang chạy, một bên quan sát có thể thấy thao tác với List đã xong nhưng thao tác với Map tương ứng chưa xảy ra. Nếu nghiệp vụ yêu cầu một bất biến liên hệ nhiều cấu trúc, cần thiết kế một vùng bảo vệ ở lớp sở hữu dữ liệu và thống nhất mọi đường truy cập liên quan.

Không suy từ kết quả đúng sau `join` rằng mọi trạng thái trung gian cũng đáp ứng bất biến liên cấu trúc.

## 4. Một chuỗi kiểm tra rồi hành động cần cùng vùng khóa

Xét yêu cầu: chỉ thêm mã `X` vào danh sách nếu chưa có.

Đoạn minh họa sau chưa đủ, dù `names` là một synchronized list:

```java
if (!names.contains("X")) {
    names.add("X");
}
```

`contains` và `add` là hai thao tác riêng. Sau khi kiểm tra xong và trước khi thêm, một bên khác có thể thực hiện cùng kiểm tra rồi thêm.

Một lịch xen kẽ hợp lệ là:

```text
Luồng A: contains(X) → false
Luồng B: contains(X) → false
Luồng A: add(X)
Luồng B: add(X)
Kết quả: [X, X]
```

Không có yêu cầu hai luồng phải đồng thời đi vào chính phương thức `add`. Từng thao tác được bảo vệ nhưng toàn bộ quyết định vẫn sai mục tiêu “chỉ có một X”.

### Thí nghiệm tạo lịch xen kẽ có kiểm soát

Lưu vào `SynchronizedCheckThenActDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public class SynchronizedCheckThenActDemo {
    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        List<String> broken = Collections.synchronizedList(new ArrayList<>());
        CountDownLatch bothChecked = new CountDownLatch(2);
        Runnable splitOperation = () -> {
            boolean absent = !broken.contains("X");
            bothChecked.countDown();
            await(bothChecked);
            if (absent) {
                broken.add("X");
            }
        };
        Thread first = new Thread(splitOperation);
        Thread second = new Thread(splitOperation);
        first.start();
        second.start();
        first.join();
        second.join();
        System.out.println("separateCalls=" + broken);
        System.out.println("separateSize=" + broken.size());

        List<String> guarded = Collections.synchronizedList(new ArrayList<>());
        CountDownLatch start = new CountDownLatch(1);
        Runnable combinedOperation = () -> {
            await(start);
            synchronized (guarded) {
                if (!guarded.contains("X")) {
                    guarded.add("X");
                }
            }
        };
        Thread third = new Thread(combinedOperation);
        Thread fourth = new Thread(combinedOperation);
        third.start();
        fourth.start();
        start.countDown();
        third.join();
        fourth.join();
        System.out.println("oneCriticalSection=" + guarded);
        System.out.println("guardedSize=" + guarded.size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SynchronizedCheckThenActDemo.java
java SynchronizedCheckThenActDemo
```

Stdout:

```text
separateCalls=[X, X]
separateSize=2
oneCriticalSection=[X]
guardedSize=1
```

Phần `separateCalls` dùng `CountDownLatch(2)` để buộc cả hai luồng hoàn tất kiểm tra trước khi một trong hai được đi tiếp tới `add`. Cả hai đều đã thấy chưa có `X`, nên kết quả có hai `X`.

Đây là cách kiểm chứng một lịch xen kẽ có thể xảy ra. Không cần dựa vào `Thread.sleep` hoặc hy vọng chạy nhiều lần rồi tình cờ bắt được lỗi. Latch chỉ sắp xếp mốc của thí nghiệm; nó không tự gộp hai thao tác thành một thao tác nguyên tử. [Javadoc CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)

Phần `oneCriticalSection` đặt cả kiểm tra và thêm trong `synchronized (guarded)`. Khi một luồng đang ở vùng này, các thao tác đi qua cùng lớp bao từ bên khác phải phối hợp qua cùng khóa. Sau khi luồng đầu thêm `X`, luồng sau kiểm tra sẽ thấy nó đã có.

Không đặt một hàng rào chờ hai luồng cùng vào bên trong vùng khóa loại trừ nhau. Trong chương trình, tín hiệu bắt đầu của phần đúng được chờ trước khi lấy khóa.

### Vì sao khóa trên chính lớp bao?

Với lớp bao gốc được trả về từ các hàm trong bài, chính đối tượng lớp bao là monitor dùng để phối hợp với các thao tác trực tiếp. Khóa trên một `new Object()` riêng sẽ không tự chặn bên khác đang chỉ gọi `guarded.add`.

Một luồng đang giữ monitor có thể đi vào lại các thao tác cần cùng monitor đó; cơ chế này gọi là khóa có thể vào lại. Vì thế việc gọi `contains` và `add` bên trong `synchronized (guarded)` là mô hình phù hợp. [Java Language Specification về đồng bộ hóa](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.1)

Nếu yêu cầu dữ liệu thực sự là một tập giá trị duy nhất, `Set.add` vốn đã gộp kiểm tra thành viên và thêm vào một thao tác tập. Không cần dùng List chỉ để tự dựng lại mọi quy tắc của Set. Nhưng với một bất biến gồm nhiều điều kiện hoặc nhiều thao tác, vẫn phải xác định đúng phạm vi vùng khóa.

## 5. synchronizedMap không tự gộp get rồi put thành tăng bộ đếm

Một lỗi tương tự xảy ra với phép tăng giá trị:

```java
// Đoạn minh họa chưa đủ bảo vệ; counts là synchronized map.
int previous = counts.get("hits");
counts.put("hits", previous + 1);
```

Mỗi `get` hoặc `put` riêng được đồng bộ. Tuy nhiên, hai bên có thể cùng đọc 0, cùng tính 1 và lần lượt ghi 1. Kết quả tăng hai lần nhưng giá trị cuối chỉ là 1.

Muốn biểu diễn một phép tăng theo hai lời gọi này, cần khóa cả bước đọc lẫn bước ghi trên cùng lớp bao.

Lưu vào `SynchronizedMapCounterDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public class SynchronizedMapCounterDemo {
    public static void main(String[] args) throws InterruptedException {
        Map<String, Integer> counts =
                Collections.synchronizedMap(new HashMap<>());
        counts.put("hits", 0);

        List<Thread> threads = new ArrayList<>();
        for (int t = 0; t < 4; t++) {
            Thread thread = new Thread(() -> {
                for (int i = 0; i < 1000; i++) {
                    synchronized (counts) {
                        int previous = counts.get("hits");
                        counts.put("hits", previous + 1);
                    }
                }
            });
            threads.add(thread);
            thread.start();
        }
        for (Thread thread : threads) {
            thread.join();
        }

        Map<String, Integer> snapshot;
        synchronized (counts) {
            snapshot = new TreeMap<>(counts);
        }
        System.out.println("expected=4000");
        System.out.println("actual=" + counts.get("hits"));
        System.out.println("snapshot=" + snapshot);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SynchronizedMapCounterDemo.java
java SynchronizedMapCounterDemo
```

Stdout:

```text
expected=4000
actual=4000
snapshot={hits=4000}
```

Bốn luồng thực thi, mỗi luồng tăng 1000 lần. Mỗi lần tăng đặt `get` và `put` trong cùng `synchronized (counts)`, nên kết quả là 4000.

Việc đọc map để tạo `TreeMap` bản sao cũng được bảo vệ bằng khóa `counts`. Sau đó bản sao được dùng để hiển thị mà không tiếp tục giữ khóa của map dùng chung.

Ví dụ không nói rằng mọi thuật toán với Map đều phải viết tay bằng `get` rồi `put`. Một API gộp thao tác có thể diễn đạt mục tiêu tốt hơn trong tình huống phù hợp. Điều cần kiểm tra là hợp đồng của đúng phương thức và đúng loại Map, không suy ra chuỗi lời gọi riêng tự nguyên tử chỉ từ tên “synchronized”.

### Đọc nhiều lần cũng có thể là một thao tác ghép

Không chỉ cập nhật mới cần xem xét. Với List, đoạn kiểm tra không rỗng rồi lấy phần tử đầu có thể bị một bên khác xóa dữ liệu giữa hai lời gọi:

```java
// Đoạn minh họa phạm vi bảo vệ; list là synchronized list.
synchronized (list) {
    if (!list.isEmpty()) {
        String first = list.get(0);
        // Dùng first theo phạm vi cần bảo vệ.
    }
}
```

Nếu chỉ cần lấy một tham chiếu phần tử, sau khi đã lấy có thể xử lý tiếp ngoài khóa khi hợp đồng cho phép. Nếu cần đọc nhiều trạng thái liên quan của phần tử, phải xem cả chính sách bảo vệ trạng thái đó.

Giữ một biến tham chiếu collection là `final` cũng không tự gộp các lời gọi. `final` và tính nguyên tử của một thuật toán là hai vấn đề khác nhau.

## 6. Duyệt cần khóa suốt lần duyệt, không chỉ lúc lấy iterator

Lớp bao không giữ khóa thay cho người dùng trong toàn bộ thời gian sử dụng một `Iterator`, `Spliterator` hoặc `Stream`.

Với List hoặc Set gốc, mô hình duyệt là:

```java
// Đoạn minh họa; names là synchronized List<String>.
synchronized (names) {
    Iterator<String> iterator = names.iterator();
    while (iterator.hasNext()) {
        String value = iterator.next();
        // Xử lý ngắn, không can thiệp cấu trúc đang duyệt.
    }
}
```

Khởi tạo iterator bên trong vùng khóa rồi tiếp tục giữ khóa tới khi duyệt xong. Vòng lặp `for (String value : names)` cũng dùng cơ chế iterator; cú pháp ngắn hơn không tự có khóa bảo vệ.

Đối với Stream, cần bảo vệ cả quá trình thực thi thao tác kết thúc:

```java
// Đoạn minh họa; values là synchronized List<Integer>.
int total;
synchronized (values) {
    total = values.stream().mapToInt(Integer::intValue).sum();
}
```

Chỉ khóa lúc gọi `values.stream()` rồi thực hiện `sum()` sau khi đã ra khỏi khối khóa không bảo vệ được giai đoạn đọc phần tử.

### Khung nhìn của Map dùng khóa của Map gốc

Với `synchronizedMap`, các khung nhìn `keySet()`, `values()` và `entrySet()` vẫn gắn với Map. Khi duyệt chúng, khóa trên Map lớp bao được trả về, không khóa trên chính đối tượng khung nhìn. [Javadoc synchronizedMap về duyệt khung nhìn](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map))

Ví dụ `Set<K> keys = map.keySet()` không làm `keys` trở thành một tập bản sao. Thêm hoặc xóa ánh xạ trong Map có thể làm nội dung nhìn thấy qua `keys` thay đổi.

Lưu vào `SynchronizedMapViewsDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.StringJoiner;
import java.util.TreeMap;

public class SynchronizedMapViewsDemo {
    public static void main(String[] args) {
        Map<String, Integer> map =
                Collections.synchronizedMap(new LinkedHashMap<>());
        map.put("A", 1);
        map.put("B", 2);
        map.put("C", 3);
        Set<String> keys = map.keySet();

        StringJoiner entries = new StringJoiner(",");
        int sum = 0;
        boolean holdsMapLock;
        Map<String, Integer> afterRemoval;
        synchronized (map) {
            holdsMapLock = Thread.holdsLock(map);
            for (Map.Entry<String, Integer> entry : map.entrySet()) {
                entries.add(entry.getKey() + "=" + entry.getValue());
                sum += entry.getValue();
            }
            Iterator<String> iterator = keys.iterator();
            while (iterator.hasNext()) {
                if (iterator.next().equals("B")) {
                    iterator.remove();
                }
            }
            afterRemoval = new TreeMap<>(map);
        }

        map.put("D", 4);
        List<String> keySnapshot;
        synchronized (map) {
            keySnapshot = new ArrayList<>(keys);
        }
        System.out.println("holdsMapLock=" + holdsMapLock);
        System.out.println("entriesBeforeRemoval=" + entries);
        System.out.println("sumBeforeRemoval=" + sum);
        System.out.println("afterRemoval=" + afterRemoval);
        System.out.println("keysAfterLaterPut=" + keySnapshot);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SynchronizedMapViewsDemo.java
java SynchronizedMapViewsDemo
```

Stdout:

```text
holdsMapLock=true
entriesBeforeRemoval=A=1,B=2,C=3
sumBeforeRemoval=6
afterRemoval={A=1, C=3}
keysAfterLaterPut=[A, C, D]
```

Chương trình dùng `LinkedHashMap` nền để thứ tự chèn `A`, `B`, `C` được xác định cho phần hiển thị.

Trong `synchronized (map)`:

1. Duyệt `entrySet` và tính tổng 6.
2. Tạo iterator từ `keys`.
3. Xóa khóa `B` bằng chính `iterator.remove()`.
4. Tạo Map bản sao sau khi xóa.

Dòng `holdsMapLock=true` xác nhận monitor của Map đang được giữ ở vùng duyệt. Khóa dùng là `map`, không phải `keys` hoặc `map.entrySet()`.

Sau đó `map.put("D", 4)` thêm một ánh xạ. Khi đọc lại `keys` dưới khóa Map, khung nhìn có `[A, C, D]`. Nó phản ánh nguồn hiện tại chứ không giữ ảnh chụp từ lần lấy `keySet` ban đầu.

### Vì sao khóa trên khung nhìn không đủ?

Đối tượng được viết trong `synchronized (x)` xác định monitor được giữ. Khóa trên `keys` và khóa trên `map` là hai việc khác nhau.

Các thao tác cập nhật thông thường qua lớp bao Map phối hợp với monitor của Map. Một vùng `synchronized (keys)` không tự ngăn chúng chạy chỉ vì `keys` là khung nhìn của Map.

Nguyên tắc thực hành là giữ lại tham chiếu đến lớp bao gốc để dùng đúng monitor khi cần duyệt. Không chuyền một khung nhìn sang nơi khác rồi bỏ mất thông tin về chính sách khóa của nguồn.

### Khóa không hợp pháp hóa mọi thay đổi trong khi duyệt

Khóa ngăn bên khác truy cập qua cùng chính sách, nhưng không tự cho phép một iterator thông thường chịu mọi thay đổi cấu trúc từ chính luồng đang giữ khóa.

Chẳng hạn, vừa duyệt bằng iterator vừa gọi `map.remove` qua đường khác vẫn có thể vi phạm hợp đồng của iterator. Khi cần loại bỏ phần tử trong quá trình duyệt và iterator hỗ trợ thao tác đó, dùng `iterator.remove()` như chương trình.

Không dựa vào việc có hay không có `ConcurrentModificationException` để kết luận thuật toán đúng. Cơ chế phát hiện thay đổi là hỗ trợ tìm lỗi, không thay thế chính sách khóa và hợp đồng duyệt.

Cũng không giữ một `Map.Entry` lấy từ khung nhìn rồi xem nó như bản ghi bất biến có thể tùy ý sử dụng ngoài mọi khóa. Entry có thể gắn với cấu trúc nguồn; nếu cần dữ liệu để xử lý sau, sao chép khóa và giá trị theo chính sách phù hợp.

## 7. Chụp dữ liệu dưới khóa rồi xử lý bên ngoài

Một lần duyệt dài làm các bên cần cùng khóa phải chờ lâu hơn. Nếu công việc tiếp theo không cần nhìn thấy những cập nhật mới nhất, có thể tách thành hai giai đoạn:

1. Giữ khóa để lấy một trạng thái dữ liệu hợp lệ.
2. Nhả khóa rồi xử lý bản sao hoặc dữ liệu đầu ra đã tạo.

Với List, bản sao cấu trúc có thể là `new ArrayList<>(list)` trong khối `synchronized (list)`. Với Map, có thể sao chép ánh xạ dưới `synchronized (map)`. Nếu giá trị là đối tượng thay đổi được, vẫn cần xem mức độ độc lập của bản sao.

Lưu vào `SynchronizedSnapshotDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class SynchronizedSnapshotDemo {
    static final class Document {
        private String title;

        Document(String title) {
            this.title = title;
        }
    }

    record DocumentView(String title) {}

    public static void main(String[] args) throws InterruptedException {
        Document first = new Document("draft");
        List<Document> documents = Collections.synchronizedList(
                new ArrayList<>(List.of(first)));

        List<Document> structuralSnapshot;
        List<DocumentView> projectedSnapshot;
        synchronized (documents) {
            structuralSnapshot = new ArrayList<>(documents);
            projectedSnapshot = documents.stream()
                    .map(document -> new DocumentView(document.title))
                    .toList();
        }

        Thread writer = new Thread(() -> {
            synchronized (documents) {
                first.title = "updated";
                documents.add(new Document("later"));
            }
        });
        writer.start();
        writer.join();

        System.out.println("sourceSize=" + documents.size());
        System.out.println("structuralSnapshotSize=" + structuralSnapshot.size());
        System.out.println("sharedDocumentTitle=" + structuralSnapshot.get(0).title);
        System.out.println("projectedTitle=" + projectedSnapshot.get(0).title());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SynchronizedSnapshotDemo.java
java SynchronizedSnapshotDemo
```

Stdout:

```text
sourceSize=2
structuralSnapshotSize=1
sharedDocumentTitle=updated
projectedTitle=draft
```

Chương trình chụp hai loại dữ liệu trước khi bắt đầu luồng ghi:

- `structuralSnapshot` sao chép cấu trúc danh sách nhưng vẫn tham chiếu tới cùng đối tượng `Document`.
- `projectedSnapshot` tạo các `DocumentView` có trường `String` chứa tiêu đề lúc chụp.

Sau khi luồng ghi đổi tiêu đề và thêm phần tử:

- Nguồn có hai phần tử.
- Bản sao cấu trúc vẫn có một phần tử.
- Tiêu đề của đối tượng dùng chung đọc qua bản sao đã là `updated`.
- Tiêu đề trong dữ liệu biểu diễn đầu ra vẫn là `draft`.

### Bảo vệ collection và bảo vệ trạng thái phần tử khác nhau

Lớp bao đồng bộ bảo vệ những thao tác truy cập qua nó. Một lời gọi sửa trường của đối tượng đã lấy ra không tự đi lại qua cơ chế khóa của collection.

Nếu chọn dùng khóa collection để bảo vệ cả trường tiêu đề, mọi bên đọc hoặc ghi trường đó khi có cạnh tranh cũng phải tuân thủ cùng chính sách. Chỉ một bên dùng `synchronized (documents)` còn bên khác tùy ý sửa trực tiếp thì không đủ.

Trong chương trình, luồng chính gọi `writer.join()` trước khi đọc tiêu đề đã sửa. Nó chờ bên ghi kết thúc; ví dụ không đưa ra một phép đọc không được phối hợp trong lúc trường đang bị ghi. Quan hệ hoàn tất giữa các luồng giúp kết quả quan sát có ý nghĩa; không thay `join` bằng một thời gian ngủ ước lượng. [Java Language Specification về quan hệ happens-before](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5)

Các trường của `DocumentView` trong ví dụ dùng `String` bất biến nên dữ liệu tiêu đề đã tách khỏi trường sửa được của `Document`. Nếu đối tượng đầu ra chứa tham chiếu đến cấu trúc thay đổi được khác, vẫn cần thiết kế cách sao chép hoặc bảo vệ phần đó.

### Tránh giữ khóa cho công việc không cần nguồn dùng chung

Việc gọi I/O, chờ tác vụ khác hoặc thực hiện tính toán dài trong vùng khóa có thể giữ các bên khác chờ theo. Nếu có thể xử lý một bản chụp, hãy chỉ giữ khóa cho giai đoạn lấy dữ liệu và duy trì bất biến cần thiết.

Khi xử lý song song, các luồng thực thi khác không tự sở hữu monitor mà luồng gọi đang giữ. Không giữ khóa nguồn rồi cho tác vụ con cần lại chính khóa đó trong khi luồng gọi chờ kết quả. Một bản chụp dữ liệu phù hợp thường giúp tách việc đọc nguồn dùng chung khỏi giai đoạn tính toán.

## 8. Phạm vi bảo đảm và chi phí của lớp bao đồng bộ

### Đồng bộ còn liên quan đến việc nhìn thấy dữ liệu

Sử dụng cùng monitor không chỉ ngăn hai vùng được bảo vệ chạy cùng lúc. Việc nhả monitor có quan hệ xảy ra trước được bảo đảm với lần lấy cùng monitor phía sau, qua đó cung cấp quy tắc nhìn thấy các ghi trước đó.

Tuy nhiên, quy tắc này cần một chính sách nhất quán. Một bên ghi ngoài khóa và một bên đọc trong khóa không tự tạo thành cặp phối hợp đúng chỉ vì bên đọc có từ khóa `synchronized`.

Các chương trình tạo dữ liệu trước khi bắt đầu luồng, dùng lớp bao hoặc vùng khóa cho phần truy cập cạnh tranh, và chờ `join` trước khi đánh giá kết quả cuối. Đây là những mốc phối hợp có ý nghĩa trong hợp đồng Java, không phải thời gian chờ phỏng đoán.

### Một monitor chung có thể trở thành điểm tranh chấp

Các thao tác trực tiếp trên một lớp bao gốc phối hợp qua cùng monitor, nên những bên truy cập phải chờ nhau theo phạm vi khóa đó. Cách tổ chức này dễ hiểu và cho phép gộp một bất biến gồm nhiều thao tác bằng khóa bên ngoài.

Đổi lại, nhiều bên cùng truy cập một cấu trúc có thể tranh chấp cùng khóa, kể cả khi đang xử lý những phần tử hoặc khóa nghiệp vụ khác nhau. Lớp bao không phải cam kết làm chương trình chạy song song nhanh hơn và không hứa lịch cấp khóa công bằng theo thứ tự yêu cầu.

Không rút ngắn vùng khóa tới mức bỏ mất một phần bất biến. Cũng không kéo dài nó tới những xử lý không còn cần nguồn dùng chung. Phạm vi đúng phải được xác định theo yêu cầu dữ liệu.

### Không thay bằng concurrent collection rồi giữ nguyên mọi giả định về khóa

`ConcurrentHashMap` được thiết kế cho việc đọc và cập nhật đồng thời theo chính sách riêng; các thao tác của nó không dùng monitor của đối tượng theo cùng hợp đồng lớp bao `synchronizedMap`. Vì vậy, một khối `synchronized (map)` không tự chặn mọi cập nhật thông thường của một `ConcurrentHashMap`. [Javadoc ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

Nếu cần các thao tác độc lập theo khóa có khả năng mở rộng tốt hơn, có thể xem xét API concurrent thích hợp. Nếu cần một trạng thái chung nhất quán gồm nhiều bước, phải thiết kế lại bất biến theo đúng loại cấu trúc và thao tác được chọn.

Tương tự, `CopyOnWriteArrayList` cung cấp cách duyệt ảnh chụp, nhưng các lần sửa có chi phí tạo mảng mới. Nó phù hợp với những tình huống có đặc điểm đọc và ghi tương ứng, không phải tên thay thế cho mọi synchronized list. [Javadoc CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html)

Mục tiêu là chọn một mô hình truy cập rõ ràng: lớp bao với monitor chung, nguồn duyệt ảnh chụp hoặc cấu trúc concurrent với các thao tác phù hợp. Không trộn các giả định về chúng chỉ vì đều được gọi là an toàn đa luồng.

## 9. Thiết kế cách sử dụng và nhận ra lỗi phổ biến

Một lớp sở hữu dữ liệu nên giữ riêng tham chiếu lớp bao và cung cấp những thao tác có ý nghĩa. Nếu đưa collection ra để mọi bên tự sửa, rất khó giữ các bất biến ghép của lớp sở hữu.

Ví dụ, thay vì để nơi gọi tùy ý thực hiện `contains` rồi `add`, lớp sở hữu có thể cung cấp phương thức “thêm nếu chưa có” với vùng khóa đúng. Thay vì trả khung nhìn Map mà không nói cách khóa, có thể trả bản chụp dữ liệu khi đó là điều bên nhận cần.

Phạm vi bảo vệ nên thể hiện được trong mô tả và mã:

| Tình huống | Cách tổ chức |
| --- | --- |
| Một lời gọi `add`, `contains`, `get`, `put` trực tiếp | Gọi qua lớp bao được chia sẻ |
| Kiểm tra rồi cập nhật cùng cấu trúc | Giữ monitor của lớp bao cho toàn bộ quyết định |
| Lấy nhiều giá trị cần nhất quán với nhau | Đọc trong một vùng khóa đúng phạm vi |
| Duyệt List hoặc Set bằng iterator | Giữ khóa lớp bao gốc từ lúc tạo iterator tới khi duyệt xong |
| Duyệt khung nhìn của synchronized Map | Giữ khóa Map lớp bao gốc |
| Thực thi stream đọc dữ liệu dùng chung | Giữ khóa cho toàn bộ giai đoạn duyệt, hoặc xử lý bản chụp |
| Cần tính toán dài không đòi trạng thái mới nhất | Chụp dữ liệu hợp lệ dưới khóa rồi tính bên ngoài |
| Phần tử là đối tượng có thể sửa | Xác định thêm chính sách cho trạng thái đối tượng |
| Bất biến liên quan nhiều cấu trúc | Thiết kế vùng sở hữu và chính sách khóa bao trùm; không coi mỗi lớp bao riêng là giao dịch chung |

Những lỗi thường gặp:

| Cách viết hoặc cách hiểu | Vấn đề |
| --- | --- |
| Giữ `raw` và cập nhật nó ngoài lớp bao | Bỏ qua cơ chế bảo vệ đã chọn |
| Tạo hai lớp bao độc lập trên cùng `raw` | Hai monitor không tự phối hợp |
| Khóa trên collection nền thay vì lớp bao gốc | Không cùng monitor với những thao tác thông thường qua lớp bao |
| Cho rằng hai lời gọi riêng tự thành nguyên tử | Có thể có thao tác khác xen giữa |
| Khóa lúc tạo iterator rồi nhả trước vòng lặp | Phần duyệt thật không còn được bảo vệ |
| Dùng vòng `for-each` và quên nó dùng iterator | Cú pháp không tự thêm vùng khóa |
| Duyệt `map.keySet()` dưới `synchronized (keys)` | Phải khóa trên Map lớp bao gốc |
| Tạo stream dưới khóa rồi thực thi sau khi nhả | Không bảo vệ thời gian pipeline đọc nguồn |
| Giữ khóa rồi sửa cấu trúc qua đường không phù hợp với iterator | Khóa không thay thế hợp đồng của iterator |
| Xem không có ngoại lệ là bằng chứng an toàn | Lỗi phối hợp không phải lúc nào cũng được phát hiện bằng ngoại lệ |
| Trả một đối tượng phần tử rồi coi mọi setter của nó được bảo vệ | Lời gọi setter không tự lấy khóa collection |
| Chuyển sang ConcurrentHashMap nhưng vẫn dựa vào khóa monitor của wrapper | Hai loại cấu trúc có hợp đồng phối hợp khác nhau |
| Đọc nhiều collection sau từng lời gọi rồi xem là một trạng thái chung | Những lớp bao riêng không tạo giao dịch liên cấu trúc |
| Dùng `sleep` để đợi bên ghi thay vì phối hợp hoàn tất | Thời gian trôi qua không thay thế tín hiệu hoặc `join` |

Khi sửa một lỗi đa luồng, câu hỏi có ích là: trạng thái nào cần được bảo vệ, mọi bên đang dùng monitor nào và phạm vi thao tác nào phải được coi là một đơn vị? Chỉ thêm một lớp bao mà chưa trả lời ba câu hỏi đó thường mới giải quyết được một phần vấn đề.

## 10. Thực hành kiểm chứng đúng phạm vi khóa

### Bài 1: vì sao vẫn có hai X?

Một synchronized list được dùng bằng hai lời gọi `contains` rồi `add`. Mỗi phương thức đều đi qua lớp bao, nhưng kết quả vẫn có hai phần tử `X`. Có phải lớp bao đã hỏng tính an toàn bên trong không?

**Đối chiếu:**

Không. Lỗi là thuật toán gồm hai lời gọi chưa được gộp vào một vùng khóa. Hai luồng có thể cùng quan sát chưa có `X` rồi lần lượt thêm. `SynchronizedCheckThenActDemo` dùng latch để kiểm chứng đúng lịch này.

Đặt toàn bộ kiểm tra và thêm trong `synchronized (list)` nếu đó là bất biến cần giữ.

### Bài 2: Set và hành động đi kèm

Trong một synchronized set chỉ có các bên thêm, không có bên xóa, muốn biết chính lời gọi này có thêm một mã mới hay không. Có cần tự gọi `contains` rồi `add` không?

**Đối chiếu:**

Không cần. Dùng giá trị boolean trả về của `set.add(code)`: `true` cho biết lời gọi đã thêm phần tử chưa có, `false` cho biết phần tử đã có theo quy tắc của Set.

Nếu còn nhiều cập nhật khác phải diễn ra cùng việc thêm như một bất biến, cần thiết kế phạm vi bảo vệ chung cho chúng. Giá trị trả về của một lời gọi không tự gộp mọi hành động về sau thành một giao dịch.

### Bài 3: tăng bộ đếm trong Map

Hai luồng cùng đọc `hits=0` từ synchronized Map rồi mỗi luồng ghi giá trị đọc cộng 1. Giá trị cuối có thể là 1 không? Việc một lần `put` chờ lần `put` kia hoàn tất có giải quyết được không?

**Đối chiếu:**

Giá trị cuối có thể là 1. Cả hai đã tính từ cùng giá trị cũ trước khi ghi. Xếp lần lượt hai phép ghi không làm xuất hiện lại lần tăng đã mất.

Với cách dùng `get` rồi `put`, giữ monitor của Map lớp bao cho cả lần đọc, tính và ghi như chương trình bộ đếm.

### Bài 4: chọn đối tượng khóa khi duyệt Map

Có `Map<String,Integer> map = Collections.synchronizedMap(...)` và `Set<String> keys = map.keySet()`. Khi dùng iterator từ `keys`, nên khóa trên `keys` hay `map`?

**Đối chiếu:**

Khóa trên `map`, tức lớp bao gốc. Tạo iterator và giữ khóa tới khi duyệt xong. Khóa trên khung nhìn không cùng monitor với những thao tác thông thường của lớp bao Map.

### Bài 5: khối khóa đã kết thúc trước vòng lặp

Chương trình tạo iterator trong `synchronized (list)`, gán iterator ra biến ngoài rồi duyệt sau khi đã rời khối. Cách đó đã đáp ứng yêu cầu chưa?

**Đối chiếu:**

Chưa. Việc cần bảo vệ là toàn bộ quá trình duyệt, không chỉ bước tạo bộ duyệt. Giữ khóa trong vòng lặp, hoặc tạo bản chụp dữ liệu dưới khóa rồi duyệt bản chụp theo chính sách của nó.

### Bài 6: lớp bao thứ hai có cứu lớp bao thứ nhất không?

Một bên dùng `first = synchronizedList(raw)`, bên khác tự tạo `second = synchronizedList(raw)`. Cả hai đều không dùng trực tiếp `raw`. Điều kiện “đều có synchronized” đã đủ chưa?

**Đối chiếu:**

Chưa. Hai lớp bao độc lập không tự có cùng monitor. Cần chia sẻ cùng một lớp bao hoặc thiết kế một chính sách truy cập chung thật sự, không để mỗi bên tự chọn khóa riêng quanh cùng dữ liệu.

### Bài 7: bản sao đã chụp dưới khóa có đóng băng phần tử không?

Một `List<Document>` được sao chép bằng `new ArrayList<>(documents)` dưới đúng khóa. Sau đó một bên sửa tiêu đề của một `Document` dùng chung. Bản sao có bắt buộc giữ tiêu đề cũ không?

**Đối chiếu:**

Không. Nó độc lập về cấu trúc nhưng vẫn chứa tham chiếu tới đối tượng đó. Nếu cần giữ giá trị tiêu đề ở thời điểm chụp, tạo dữ liệu đầu ra phù hợp dưới chính sách bảo vệ, như `DocumentView` trong ví dụ.

Khi kiểm chứng việc đọc sau ghi ở những luồng khác nhau, dùng mốc phối hợp đúng; không suy ra tính nhìn thấy dữ liệu từ một thời gian ngủ.

### Bài 8: thay loại Map và giữ nguyên synchronized

Đổi một biến từ synchronized Map sang `ConcurrentHashMap`, nhưng vẫn dùng `synchronized (map)` để mong chặn mọi `put` từ các bên khác. Có thể giữ nguyên giả định đó không?

**Đối chiếu:**

Không. Quy tắc monitor trong bài gắn với lớp bao đồng bộ. Các thao tác thông thường của `ConcurrentHashMap` không phối hợp theo cùng giả định đó. Cần chọn thao tác và thiết kế bất biến theo hợp đồng của loại Map mới.

Một lời giải đúng phải giải thích được vì sao mọi bên truy cập trạng thái liên quan đều được cùng một chính sách bảo vệ, thay vì chỉ chỉ ra rằng trong mã có từ khóa `synchronized`.
