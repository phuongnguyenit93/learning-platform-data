# ConcurrentSkipListMap và ConcurrentSkipListSet

## 1. Khi cần vừa có thứ tự vừa dùng chung giữa nhiều luồng

Một chỉ mục dùng chung có thể cần hai khả năng cùng lúc:

- Nhiều luồng thêm, xóa và tra cứu mà cấu trúc vẫn đúng.
- Dữ liệu có thứ tự để tìm mốc gần nhất, truy vấn khoảng hoặc lấy một đầu.

`ConcurrentSkipListMap<K, V>` là ánh xạ đồng thời có thứ tự khóa, triển khai `ConcurrentNavigableMap<K, V>`. `ConcurrentSkipListSet<E>` là tập đồng thời có thứ tự, triển khai `NavigableSet<E>` và được xây dựng dựa trên map cùng họ.

| Cấu trúc | Lưu gì? | Phù hợp khi |
| --- | --- | --- |
| ConcurrentSkipListMap | Khóa và giá trị đi kèm | Cần chỉ mục có thứ tự cho dữ liệu dùng chung |
| ConcurrentSkipListSet | Các phần tử duy nhất | Chỉ cần giữ/tìm các phần tử có thứ tự |
| ConcurrentHashMap | Khóa và giá trị, không cung cấp thứ tự khóa để điều hướng | Chủ yếu cần tra cứu đúng khóa đồng thời |
| TreeMap/TreeSet | Ánh xạ/tập có thứ tự thông thường | Truy cập một luồng hoặc có cơ chế phối hợp bên ngoài |

Chọn skip list đồng thời vì yêu cầu **thứ tự và điều hướng**, không chỉ vì tên có chữ Concurrent. Các ví dụ trong bài dùng API hiện hành và chạy bằng Java 17 trở lên.

## 2. Skip list đóng vai trò gì?

Có thể hình dung skip list như một chuỗi dữ liệu đã sắp thứ tự, có thêm nhiều tầng liên kết giúp bỏ qua các đoạn dài khi tìm kiếm:

```text
Tầng thưa:    10 ----------------------> 70
Tầng giữa:   10 ------> 30 ------------> 70
Tầng dữ liệu:10 -> 20 -> 30 -> 40 -> 50 -> 70
```

Đây chỉ là sơ đồ khái niệm, không phải bố trí nút chính xác của JDK. Tìm kiếm đi qua các liên kết thưa rồi hạ tầng khi cần, thay vì phải đọc mọi phần tử.

Các lớp này cung cấp chi phí **kỳ vọng trung bình O(log n)** cho các thao tác cơ bản theo khóa/phần tử. Không biến chữ “kỳ vọng” thành lời hứa thời gian xấu nhất luôn giống cây cân bằng. Cách tổ chức và thuật toán đồng thời bên trong thuộc về cách cài đặt JDK; ứng dụng nên dựa vào hợp đồng công khai.

Thứ tự dùng thứ tự tự nhiên hoặc comparator. Với map, chỉ K tham gia sắp xếp; V không cần so sánh được. Với set, chính E là phần tử được so sánh. Đặc điểm này được mô tả trong [ConcurrentSkipListMap API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html) và [ConcurrentSkipListSet API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentSkipListSet.html).

## 3. Những khả năng vẫn giống cấu trúc điều hướng

### 3.1. Map điều hướng theo khóa

Khai báo thường dùng:

```java
// Đoạn minh họa.
ConcurrentNavigableMap<Integer, String> index =
        new ConcurrentSkipListMap<>();
```

Ngoài `get`, `put`, `remove`, map có:

- `lowerKey`/`lowerEntry`: ứng viên sát phía trước, không nhận bằng.
- `floorKey`/`floorEntry`: ứng viên sát phía trước, nhận bằng.
- `ceilingKey`/`ceilingEntry`: ứng viên sát phía sau, nhận bằng.
- `higherKey`/`higherEntry`: ứng viên sát phía sau, không nhận bằng.
- `firstEntry`, `lastEntry` để xem hai đầu.
- `pollFirstEntry`, `pollLastEntry` để lấy và xóa một đầu.

Mốc không cần có sẵn trong map. Không có ứng viên thì các truy vấn điều hướng dạng Key/Entry trả null. Các quan hệ trước/sau theo comparator, không nhất thiết theo số tăng dần.

### 3.2. Set giữ phần tử duy nhất và tìm hàng xóm

```java
// Đoạn minh họa.
ConcurrentSkipListSet<Integer> ids = new ConcurrentSkipListSet<>();
```

Set hỗ trợ `add`, `remove`, `contains`, cùng `lower`, `floor`, `ceiling`, `higher`, `pollFirst`, `pollLast` và các góc nhìn khoảng/đảo.

`add(id)` trả true nếu lần gọi đó thêm được phần tử, false nếu đã có phần tử tương đương. Có thể dùng ngay kết quả này để xác định ai thực hiện lần thêm, thay vì viết chuỗi `contains` rồi `add`.

Cả map lẫn set xác định vị trí trùng theo phép so sánh. Comparator nên nhất quán với equals để tuân thủ hợp đồng chung của Map/Set. Các khóa hoặc trường sắp xếp cần ổn định trong thời gian nằm trong cấu trúc; tính đồng thời không sửa được comparator sai hoặc khóa mutable bị đổi tùy ý.

### 3.3. Không nhận null

`ConcurrentSkipListMap` không nhận khóa null hoặc value null; `ConcurrentSkipListSet` không nhận phần tử null, kể cả khi comparator tự viết có thể so sánh null.

Vì vậy null trả về từ `get` hoặc truy vấn điều hướng không bị nhập nhằng với một ánh xạ có value null.

Không tổng quát chính sách null của TreeMap sang map đồng thời này. Khả năng điều hướng giống nhau không có nghĩa mọi chính sách dữ liệu giống nhau.

## 4. Thao tác nguyên tử không làm mọi chuỗi thao tác nguyên tử

### 4.1. Tránh “kiểm tra rồi ghi” bằng hai lời gọi

Mẫu sau sai về ý định “chỉ tạo nếu chưa có” khi nhiều luồng cùng chạy:

```java
// Mẫu minh họa lỗi; index là ConcurrentNavigableMap<Integer, String>.
if (!index.containsKey(10)) {
    index.put(10, "new");
}
```

Hai luồng có thể cùng thấy chưa có khóa rồi cùng ghi. Từng thao tác trên cấu trúc là an toàn không có nghĩa cả nhánh if là một đơn vị.

Dùng `putIfAbsent` để diễn đạt thao tác kết hợp:

```java
// Đoạn minh họa.
String previous = index.putIfAbsent(10, "new");
boolean inserted = previous == null;
```

Do map không cho value null, previous null nghĩa là lần gọi đã đặt giá trị mới; khác null là đã có giá trị tại thời điểm thao tác đó.

Các thao tác có điều kiện được cung cấp bởi [ConcurrentMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentMap.html), trong đó có:

| Thao tác | Ý nghĩa |
| --- | --- |
| `putIfAbsent(k, v)` | Ghi khi chưa có khóa |
| `replace(k, expected, next)` | Chỉ thay nếu value hiện tại bằng expected |
| `remove(k, expected)` | Chỉ xóa nếu value hiện tại bằng expected |
| `replace(k, next)` | Thay khi khóa vẫn có ánh xạ |

Chúng giải quyết các điều kiện trên một khóa. Chuyển tiền giữa hai khóa, giữ một bất biến trên nhiều khóa hoặc phối hợp map với một đối tượng ngoài vẫn cần thiết kế khác.

### 4.2. Cập nhật bộ đếm bằng merge

Không dùng `get` rồi `put(old + 1)` khi nhiều luồng tăng cùng bộ đếm: hai luồng có thể đọc cùng giá trị cũ và ghi đè kết quả của nhau.

Trong chương trình:

```java
// Đoạn minh họa.
counts.merge(key, 1, Integer::sum);
```

Nếu chưa có khóa, đặt 1; nếu đã có, tính giá trị mới từ giá trị hiện tại theo cơ chế cập nhật của map. Hàm cộng không có tác dụng phụ bên ngoài, nên phù hợp với quá trình có thể phải thử lại.

Không suy ra hàm truyền vào `compute`, `computeIfAbsent`, `computeIfPresent` hoặc `merge` của ConcurrentSkipListMap luôn chỉ được gọi đúng một lần. API của lớp không bảo đảm việc gọi hàm tính toán chỉ diễn ra một lần nguyên tử. Tránh gửi thông báo, ghi nhật ký nghiệp vụ cần đúng một lần hoặc thực hiện tác động bên ngoài trong các hàm này. Cập nhật ánh xạ và số lần hàm tính được chạy là hai hợp đồng khác nhau.

### 4.3. Kết quả điều hướng không phải quyền sở hữu

`floorEntry(x)` cho biết một ánh xạ được tìm thấy; nó không giữ cho ánh xạ ấy tiếp tục tồn tại hoặc tiếp tục là ứng viên floor khi các luồng khác thêm/xóa.

Muốn xóa đúng giá trị đã quan sát, có thể dùng `remove(key, expectedValue)`, nhưng phải hiểu điều kiện kiểm tra theo giá trị và tại khóa cụ thể. Nó không đồng thời kiểm tra lại mọi điều kiện chọn khoảng hoặc mọi thay đổi nghiệp vụ trước đó.

Đối với trường hợp chỉ cần lấy và xóa đầu, dùng một lời gọi poll phù hợp thay vì tự ghép firstEntry với remove.

## 5. Iterator nhất quán yếu: duyệt được khi có thay đổi

Iterator của cả hai lớp là **nhất quán yếu (weakly consistent)**:

- Cho phép duyệt trong khi các luồng khác cập nhật.
- Không dùng fail-fast để báo thay đổi đồng thời như iterator thông thường của TreeMap/TreeSet.
- Có thể phản ánh một số thay đổi diễn ra trong khi duyệt.
- Không hứa toàn bộ lượt duyệt là ảnh chụp của cấu trúc ở đúng một thời điểm.

Ví dụ, trong khi duyệt các khóa `[10, 20, 30]`, luồng khác thêm 25 hoặc xóa 20. Không nên viết kiểm thử đòi iterator bắt buộc phải thấy hoặc không thấy mỗi thay đổi đó theo một lịch chạy chưa được kiểm soát.

“Không ném ConcurrentModificationException” không đồng nghĩa “báo cáo là một bản chụp hoàn chỉnh”. Nếu cần một kết quả nhất quán cho nghiệp vụ đối soát, phải thiết kế điểm phối hợp, phiên bản hoặc thời điểm tạm dừng cập nhật phù hợp.

Sao chép bằng constructor trong lúc nguồn đang thay đổi cũng không tự biến lượt đọc nguồn thành một giao dịch snapshot.

### 5.1. Entry của map không hỗ trợ setValue

Các entry do ConcurrentSkipListMap và các góc nhìn của nó trả về là ảnh chụp ánh xạ, không hỗ trợ `Entry.setValue`. Điều này bao gồm các entry dùng khi duyệt, nên không áp dụng máy móc mẫu thay value qua entrySet iterator của TreeMap.

Muốn cập nhật, dùng `put`, `putIfAbsent`, `replace` hoặc các phép tính trên map phù hợp. Ảnh chụp vẫn là sao chép nông của tham chiếu key/value, không tự làm đối tượng V mutable an toàn.

## 6. Các góc nhìn vẫn liên kết với dữ liệu gốc

`subMap`, `headMap`, `tailMap`, `descendingMap` cùng các góc nhìn tương ứng của set hoạt động trên cùng dữ liệu.

Ví dụ:

```java
// Đoạn minh họa.
ConcurrentNavigableMap<Integer, Integer> window =
        counts.subMap(0, true, 2, false);
window.put(1, 5000);
```

Khóa 1 thuộc `[0, 2)`, nên giá trị trong counts cũng đổi. Khóa ngoài khoảng không được thêm qua window. Một lần duyệt window vẫn phải được hiểu theo chính sách nhất quán yếu, không phải bản sao độc lập.

Thứ tự đảo cũng đảo ý nghĩa đầu/cuối và hướng điều hướng. Theo tài liệu các lớp, duyệt và góc nhìn tăng dần thường nhanh hơn chiều giảm; nếu chiều giảm là đường chạy quan trọng, đo với dữ liệu thật thay vì giả định hai chiều có cùng chi phí.

Không xem `putAll`, `clear`, `equals`, `toArray` hoặc một lượt forEach/addAll là một thao tác nguyên tử trên toàn bộ tập dữ liệu. Luồng khác có thể quan sát một phần thay đổi tổng thể.

Đặc biệt, một lần size không phải sự dành chỗ. Chuỗi `if (size() < limit) add(...)` không bảo đảm giới hạn dung lượng khi nhiều luồng cùng chạy. Số lượng có thể đổi ngay sau lần quan sát; cũng không nên giả định size của mọi lớp/góc nhìn skip list đều là thao tác rẻ với cùng cách cài đặt.

## 7. Chương trình hoàn chỉnh với kết quả kiểm chứng được

Chương trình có hai giai đoạn:

1. Bốn tác vụ tăng ba bộ đếm bằng merge và cùng thêm các id trùng nhau vào set.
2. Sau khi hoàn tất giai đoạn ghi, bốn tác vụ lấy công việc từ đầu một map đã nạp sẵn 20 khóa.

Chương trình chỉ in kết quả sau khi đã `Future.get()` tất cả tác vụ liên quan. Nó không in thứ tự từng luồng, nên kết quả không phụ thuộc việc bộ lập lịch ưu tiên luồng nào.

Lưu thành **ConcurrentSkipListDemo.java**:

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentNavigableMap;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.ConcurrentSkipListSet;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ConcurrentSkipListDemo {
    public static void main(String[] args) throws Exception {
        ConcurrentNavigableMap<Integer, Integer> counts =
                new ConcurrentSkipListMap<>();
        ConcurrentSkipListSet<Integer> ids = new ConcurrentSkipListSet<>();
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            CountDownLatch start = new CountDownLatch(1);
            List<Future<Void>> writers = new ArrayList<>();
            for (int worker = 0; worker < 4; worker++) {
                writers.add(pool.submit(() -> {
                    start.await();
                    for (int round = 0; round < 1000; round++) {
                        for (int key = 0; key < 3; key++) {
                            counts.merge(key, 1, Integer::sum);
                        }
                        ids.add(round % 10);
                    }
                    return null;
                }));
            }
            start.countDown();
            for (Future<Void> writer : writers) writer.get();
            if (!counts.equals(Map.of(0, 4000, 1, 4000, 2, 4000))) {
                throw new AssertionError("Lost updates");
            }
            System.out.println("Counts after join: " + counts);
            System.out.println("Set after join: " + ids);
            System.out.println("Floor/ceiling of 5: " +
                    ids.floor(5) + "/" + ids.ceiling(5));
            System.out.println("Map floorEntry(1): " + counts.floorEntry(1));

            ConcurrentNavigableMap<Integer, Integer> window =
                    counts.subMap(0, true, 2, false);
            window.put(1, 5000);
            System.out.println("Value through linked view: " + counts.get(1));
            counts.putIfAbsent(1, 999);
            System.out.println("After putIfAbsent: " + counts.get(1));
            System.out.println("Conditional replace: " +
                    counts.replace(1, 5000, 6000));
            System.out.println("Conditional remove mismatch: " +
                    counts.remove(1, 999));

            ConcurrentNavigableMap<Integer, String> pending =
                    new ConcurrentSkipListMap<>();
            for (int key = 0; key < 20; key++) {
                pending.put(key, "job-" + key);
            }
            List<Future<List<Integer>>> consumers = new ArrayList<>();
            for (int worker = 0; worker < 4; worker++) {
                consumers.add(pool.submit(() -> {
                    List<Integer> local = new ArrayList<>();
                    Map.Entry<Integer, String> entry;
                    while ((entry = pending.pollFirstEntry()) != null) {
                        local.add(entry.getKey());
                    }
                    return local;
                }));
            }
            Set<Integer> unique = new HashSet<>();
            int total = 0;
            for (Future<List<Integer>> consumer : consumers) {
                for (int key : consumer.get()) {
                    total++;
                    if (!unique.add(key)) {
                        throw new AssertionError("Duplicate claim");
                    }
                }
            }
            if (total != 20 || unique.size() != 20 || !pending.isEmpty()) {
                throw new AssertionError("Missing job");
            }
            System.out.println("Claimed/unique/remaining: " +
                    total + "/" + unique.size() + "/" + pending.size());

            try {
                counts.put(99, null);
            } catch (NullPointerException ex) {
                System.out.println("Null values rejected");
            }
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 ConcurrentSkipListDemo.java
java ConcurrentSkipListDemo
```

Kết quả chuẩn:

```text
Counts after join: {0=4000, 1=4000, 2=4000}
Set after join: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
Floor/ceiling of 5: 5/5
Map floorEntry(1): 1=4000
Value through linked view: 5000
After putIfAbsent: 5000
Conditional replace: true
Conditional remove mismatch: false
Claimed/unique/remaining: 20/20/0
Null values rejected
```

### 7.1. Vì sao kết quả đếm là 4000?

Có bốn tác vụ, mỗi tác vụ tăng mỗi khóa 1000 lần. Với mỗi khóa, tổng là `4 × 1000 = 4000`.

Dữ liệu được in và so sánh sau khi mọi writer đã hoàn tất. Nếu in trong lúc ghi, ta không được đòi các giá trị cuối cùng ấy xuất hiện đồng thời trong một lượt duyệt.

### 7.2. Vì sao set chỉ có 10 phần tử?

Mỗi tác vụ thêm nhiều lần các id 0 đến 9. Tính duy nhất của set giữ một phần tử cho mỗi id, bất kể có bao nhiêu luồng cùng thêm. Các phần tử được in theo thứ tự khóa tự nhiên.

### 7.3. Phép poll kiểm chứng điều gì?

Map pending đã được nạp xong trước khi chạy consumers; không có producer thêm lại khóa. Mỗi lời gọi poll lấy và xóa một ánh xạ. Kiểm tra tổng/duy nhất xác nhận 20 khóa được nhận đủ, không trùng, và map cuối cùng rỗng.

Không có lời hứa một consumer cụ thể nhận khóa nào. Thứ tự hoàn tất công việc ở nhiều luồng cũng không nhất thiết trùng thứ tự khóa được lấy. “Nhận việc không trùng trong ví dụ” khác với “tác động nghiệp vụ được thực hiện đúng một lần bất chấp lỗi hoặc khởi động lại”.

Nếu có producer thêm sau khi một consumer vừa thấy map rỗng, vòng lặp consumer đó vẫn đã kết thúc. Poll không chờ dữ liệu và không thay thế cơ chế chờ/đóng hàng đợi.

## 8. Value dùng chung vẫn cần chính sách đồng thời

Map đồng thời bảo vệ cấu trúc ánh xạ, không tự bảo vệ mọi đối tượng được lưu trong V.

Ví dụ, `ConcurrentSkipListMap<Integer, ArrayList<String>>` không làm `ArrayList.add` trên cùng danh sách trở nên an toàn giữa nhiều luồng. Có thể chọn:

- Value bất biến, cập nhật bằng cách tạo giá trị mới.
- Một kiểu value có hợp đồng đồng thời thích hợp.
- Cơ chế đồng bộ bao quanh các thao tác của value.
- Một luồng sở hữu value và các luồng khác gửi yêu cầu.

ConcurrentMap cung cấp quan hệ công bố dữ liệu giữa thao tác đưa đối tượng vào map và thao tác truy cập/xóa tương ứng ở luồng khác. Điều đó không tự đồng bộ mọi sửa đổi mutable xảy ra sau khi công bố.

Trong ví dụ, Integer và String là bất biến, còn các danh sách local chỉ do từng tác vụ sử dụng trước khi trả về. HashSet tổng hợp chỉ được luồng main sửa sau khi nhận kết quả từ Future; nó không bị các consumer đồng thời ghi.

## 9. Chọn lớp theo yêu cầu thực tế

Dùng ConcurrentSkipListMap khi cần nhiều luồng truy cập cùng một chỉ mục khóa có thứ tự: cấu hình theo mốc, dữ liệu theo thời điểm, hoặc tìm ứng viên trong khoảng.

Dùng ConcurrentSkipListSet khi chỉ cần các mốc/phần tử duy nhất mà không có V đi kèm.

Nếu chỉ cần tra đúng khóa và không có truy vấn thứ tự, cân nhắc ConcurrentHashMap. Nếu cần đợi đến khi có công việc, phải chọn cơ chế hàng đợi/chờ phù hợp. Nếu cần một bất biến nguyên tử trên nhiều khóa, không có lớp nào ở đây tự cung cấp giao dịch đa khóa chỉ nhờ việc đổi tên cấu trúc.

Các cấu trúc có thứ tự cũng phải trả giá cho so sánh, liên kết chỉ mục và cập nhật đồng thời. Không khẳng định chúng nhanh hơn mọi map hoặc mọi cách dùng khóa ngoài trong mọi tải công việc.

## 10. Lỗi thường gặp

| Lỗi | Hậu quả hoặc cách sửa |
| --- | --- |
| Contains rồi put để tạo duy nhất | Dùng putIfAbsent |
| Get rồi put để tăng bộ đếm | Dùng phép cập nhật phù hợp như merge với hàm không có tác dụng phụ |
| Cho rằng Concurrent nghĩa là mọi chuỗi đều nguyên tử | Xác định phạm vi một khóa và bất biến nhiều khóa |
| Mong iterator là snapshot | Hiểu tính nhất quán yếu |
| Dùng Entry.setValue của map này | Cập nhật qua API map |
| Đưa ArrayList làm value rồi ghi từ nhiều luồng | Bảo vệ riêng value hoặc dùng kiểu phù hợp |
| Dùng size để giữ giới hạn dung lượng | Điều kiện kiểm tra và thêm chưa kết hợp nguyên tử |
| Cho key/value null như TreeMap | Hai lớp skip list này cấm null |
| Trông chờ thứ tự hoàn tất tác vụ bằng thứ tự khóa | Phân biệt thứ tự chọn và lịch chạy |
| Dùng poll như lời gọi chờ công việc | Poll trả ngay khi không có dữ liệu |
| Đặt tác động cần đúng một lần trong hàm compute/merge | Hàm tính có thể được gọi lại |

## 11. Thực hành

1. Đổi số writer thành 6 và số vòng thành 200. Mỗi khóa phải có tổng 1200 sau khi đã chờ mọi writer; sửa cả kiểm tra expected và số thread khi cần.
2. Cố ý thay merge bằng get rồi put trong một bản thử riêng. Giải thích vì sao kết quả không còn được bảo đảm dù có lần chạy vẫn đúng; không dùng “chưa tái hiện” làm bằng chứng an toàn.
3. Hai luồng cùng gọi `putIfAbsent` cho một khóa chưa có. Sau khi chờ xong, phải chỉ có một ánh xạ; phân biệt kết quả trả về của lần đặt thành công với lần thấy dữ liệu đã có.
4. Tạo góc nhìn `subMap(10, true, 20, false)`, cập nhật khóa 15 và xác minh map gốc đổi. Thử thêm khóa 20 qua góc nhìn và giải thích giới hạn.
5. Duyệt trong lúc có writer nhưng chỉ kiểm tra những thuộc tính được hợp đồng cho phép; không đòi một danh sách cố định các thay đổi phải được thấy.
6. Thay V bằng một kiểu mutable và chỉ ra phần nào map bảo vệ, phần nào vẫn cần thiết kế đồng thời riêng.

Hãy chọn skip list đồng thời khi cần giữ thứ tự dưới truy cập nhiều luồng, rồi dùng đúng thao tác kết hợp cho từng ý định. Thứ tự dữ liệu, tính nguyên tử của thao tác và tính nhất quán của một lượt quan sát là ba vấn đề liên quan nhưng không thể thay thế cho nhau.
