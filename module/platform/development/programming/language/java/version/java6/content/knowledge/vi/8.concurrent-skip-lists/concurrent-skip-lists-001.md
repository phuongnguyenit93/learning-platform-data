# ConcurrentNavigableMap: kết hợp sắp xếp với truy cập đồng thời

## 1. Hai yêu cầu cần được đáp ứng cùng lúc

Một ứng dụng nhiều luồng có thể vừa cần dùng chung dữ liệu, vừa cần hỏi theo thứ tự khóa:

- Mốc gần nhất không vượt một thời điểm là gì?
- Các khóa nào nằm trong một khoảng?
- Chỉ thêm ánh xạ nếu khóa chưa được luồng khác đăng ký.
- Chỉ thay giá trị nếu trạng thái hiện tại còn đúng như đã dự kiến.

Map hỗ trợ đồng thời nhưng không có thứ tự không tự đáp ứng truy vấn hàng xóm hoặc khoảng. Map có thứ tự nhưng thiếu cơ chế truy cập đồng thời lại cần giao thức bảo vệ từ bên ngoài.

`ConcurrentNavigableMap<K, V>` kết hợp hai nhóm hợp đồng: `ConcurrentMap` và `NavigableMap`. `ConcurrentSkipListMap` là triển khai trong JDK thường dùng khi cần cả hai khả năng. Đây vẫn là API hiện hành, không chỉ là một đặc điểm lịch sử của Java 6. Xem [ConcurrentNavigableMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentNavigableMap.html).

## 2. Giao diện, triển khai và vai trò của skip list

Có thể khai báo theo giao diện:

```java
ConcurrentNavigableMap<Integer, String> map =
        new ConcurrentSkipListMap<>();
```

Trong đó:

- `ConcurrentNavigableMap` mô tả khả năng cần sử dụng.
- `ConcurrentSkipListMap` cung cấp cách triển khai cụ thể.
- Khóa được sắp theo thứ tự tự nhiên hoặc comparator truyền vào constructor.
- Cấu trúc hỗ trợ các phép đọc, thêm, cập nhật và xóa được thực hiện an toàn bởi nhiều luồng.

Triển khai này dựa trên biến thể skip list đồng thời. Tài liệu quy định chi phí trung bình kỳ vọng `O(log n)` cho những thao tác chính như `get/put/remove/containsKey` và các biến thể. Đây không phải lời hứa rằng mọi lời gọi hoàn tất sau cùng một thời gian hay nhanh hơn mọi lựa chọn khác ở mọi tải. Xem [ConcurrentSkipListMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html).

Đổi tên biến hoặc khai báo một map thường qua kiểu `Map` không tạo thêm cơ chế đồng thời cho đối tượng. Cần chọn đúng triển khai và tuân theo hợp đồng của từng thao tác.

## 3. Hai nhóm API bổ sung cho nhau

### Điều hướng theo khóa

Từ `NavigableMap`, có các truy vấn như:

| Cần tìm | API thường dùng |
| --- | --- |
| Khóa lớn nhất không vượt mốc | `floorKey(x)` |
| Khóa nhỏ nhất không thấp hơn mốc | `ceilingKey(x)` |
| Ánh xạ ở phía trước/sau | `lowerEntry(x)`, `higherEntry(x)` |
| Các ánh xạ trong một khoảng | `subMap(...)` |
| Phần trước/sau một biên | `headMap(...)`, `tailMap(...)` |
| Duyệt chiều ngược | `descendingMap()` |

Thứ tự luôn là thứ tự **khóa**, không phải thứ tự giá trị hay thứ tự các luồng hoàn thành.

### Cập nhật nguyên tử theo điều kiện

Từ `ConcurrentMap`, có những thao tác tránh lỗi tách riêng kiểm tra và cập nhật:

| API | Ý định |
| --- | --- |
| `putIfAbsent(k, v)` | Chỉ chèn nếu chưa có ánh xạ |
| `replace(k, expected, replacement)` | Chỉ thay nếu giá trị hiện tại bằng expected |
| `remove(k, expected)` | Chỉ xóa nếu giá trị hiện tại bằng expected |

Phép kiểm tra và thay đổi tương ứng được thực hiện với bảo đảm nguyên tử của thao tác. Giá trị trả về cho biết thao tác có đạt điều kiện hay không. Xem [ConcurrentMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentMap.html).

Ví dụ cần tránh khi có nhiều luồng:

```java
// Khong dung hai buoc nay de bao dam "chi mot luong chen".
if (!map.containsKey(key)) {
    map.put(key, candidate);
}
```

Hai luồng có thể cùng thấy chưa có khóa rồi cùng gọi `put`. Thay bằng `putIfAbsent` diễn đạt đúng một phép kiểm tra–chèn cần nguyên tử.

Trong `ConcurrentSkipListMap`, khóa và giá trị không được null. Vì vậy `putIfAbsent` trả null biểu thị lời gọi vừa chèn thành công khi trước đó chưa có ánh xạ; trả giá trị khác null biểu thị đã có ánh xạ. Hạn chế null thuộc hợp đồng của triển khai này.

## 4. Ví dụ chạy được: hai luồng tranh một khóa

Tệp `ConcurrentSortedMapDemo.java` chạy trên Java 17+.

Hai luồng cùng được phép bắt đầu sau một chốt, rồi gọi `putIfAbsent` cho khóa 10. Không có luồng nào xóa khóa trong giai đoạn này, nên chính xác một lần chèn thành công.

Chương trình không dự đoán A hay B thắng. Sau khi hai luồng kết thúc, nó chuẩn hóa giá trị thành `READY` để phần stdout còn lại ổn định.

```java
import java.util.concurrent.ConcurrentNavigableMap;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentSortedMapDemo {
    private static Thread contender(
            ConcurrentNavigableMap<Integer, String> map,
            String candidate,
            CountDownLatch ready,
            CountDownLatch start,
            AtomicInteger installed) {
        return new Thread(() -> {
            ready.countDown();
            try {
                start.await();
                String previous = map.putIfAbsent(10, candidate);
                if (previous == null) {
                    installed.incrementAndGet();
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        });
    }

    public static void main(String[] args) throws InterruptedException {
        ConcurrentNavigableMap<Integer, String> map =
                new ConcurrentSkipListMap<>();
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        AtomicInteger installed = new AtomicInteger();

        Thread a = contender(map, "A", ready, start, installed);
        Thread b = contender(map, "B", ready, start, installed);
        a.start();
        b.start();
        ready.await();
        start.countDown();
        a.join();
        b.join();

        if (installed.get() != 1 || map.size() != 1) {
            throw new AssertionError("Exactly one insertion was expected");
        }
        System.out.println("successful insertions=" + installed.get());

        String winner = map.get(10);
        System.out.println("conditional replace="
                + map.replace(10, winner, "READY"));
        map.put(30, "THIRTY");
        map.put(20, "TWENTY");

        System.out.println("ordered keys=" + map.navigableKeySet());
        System.out.println("floorKey(25)=" + map.floorKey(25));
        System.out.println("ceilingKey(25)=" + map.ceilingKey(25));

        ConcurrentNavigableMap<Integer, String> range =
                map.subMap(10, true, 30, false);
        System.out.println("range insertion="
                + (range.putIfAbsent(15, "MIDDLE") == null));
        System.out.println("map after range insertion=" + map);
        System.out.println("descending keys="
                + map.descendingMap().navigableKeySet());

        System.out.println("remove wrong value=" + map.remove(20, "WRONG"));
        System.out.println("remove matching value=" + map.remove(20, "TWENTY"));
        System.out.println("final map=" + map);
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```shell
javac -encoding UTF-8 ConcurrentSortedMapDemo.java
java ConcurrentSortedMapDemo
```

Kết quả:

```text
successful insertions=1
conditional replace=true
ordered keys=[10, 20, 30]
floorKey(25)=20
ceilingKey(25)=30
range insertion=true
map after range insertion={10=READY, 15=MIDDLE, 20=TWENTY, 30=THIRTY}
descending keys=[30, 20, 15, 10]
remove wrong value=false
remove matching value=true
final map={10=READY, 15=MIDDLE, 30=THIRTY}
```

## 5. Tại sao ví dụ cho kết quả đó?

### Chốt phối hợp thời điểm bắt đầu

`ready` cho luồng chính biết cả hai luồng đã sẵn sàng. `start` cho phép chúng tiến tới lời gọi tranh khóa từ cùng một giai đoạn.

Điều này không ép CPU chạy hai lệnh đúng cùng một thời điểm và cũng không quyết định luồng thắng. Bảo đảm chỉ một lần chèn đến từ `putIfAbsent`, không phải từ việc dùng chốt.

### Bộ đếm đo số lần chèn thành công

`installed` là `AtomicInteger` vì hai luồng có thể cập nhật bộ đếm. Nó đếm kết quả lời gọi có `previous == null`, không suy diễn từ giá trị cuối cùng của map.

Sau `join()`, không còn luồng tranh khóa chạy. Khi đó việc xác nhận `installed == 1` và `map.size() == 1` diễn ra trên dữ liệu đã ổn định. Không dùng phép kiểm tra kích thước giữa lúc đang có thay đổi để tạo một quy tắc giới hạn dung lượng.

### Cập nhật có điều kiện

Luồng chính đọc giá trị thắng và gọi `replace(10, winner, "READY")`. Trong giai đoạn này không còn luồng khác sửa nên kết quả là true.

Nếu trong ứng dụng thực tế có luồng khác thay giá trị trước phép replace, thao tác có thể trả false. Nơi gọi phải xử lý thất bại ấy thay vì coi giá trị vừa đọc là luôn còn đúng.

Hai lần `remove` cuối thể hiện cùng nguyên tắc: giá trị mong đợi sai thì không xóa; giá trị khớp thì xóa.

### Sắp xếp không phụ thuộc thứ tự chèn

Dù chèn khóa 30 trước 20, dãy khóa vẫn là `[10, 20, 30]`. Tra cứu `floorKey(25)` trả 20, `ceilingKey(25)` trả 30 vì quan hệ thứ tự khóa, không vì thứ tự tác vụ được thực thi.

## 6. Khung nhìn khoảng vẫn giữ khả năng đồng thời

Trong chương trình:

```java
ConcurrentNavigableMap<Integer, String> range =
        map.subMap(10, true, 30, false);
```

Kiểu trả về vẫn là `ConcurrentNavigableMap`, nên có thể tiếp tục dùng `putIfAbsent`, `replace` và các phép điều hướng trên khoảng. Đây là điểm kết hợp giữa giới hạn phạm vi và hợp đồng đồng thời.

`range.putIfAbsent(15, "MIDDLE")` thêm vào chính map gốc. Khóa 30 không được thêm qua range vì biên trên bị loại. Khung nhìn là dữ liệu đang hoạt động, không phải bản sao cố định; thay đổi trong phạm vi phản ánh qua cả hai đường truy cập. Xem [ConcurrentNavigableMap.subMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentNavigableMap.html).

Các khung nhìn `headMap/tailMap/descendingMap` cũng bảo toàn khả năng truy cập đồng thời theo hợp đồng. Chúng không tạo một giao dịch riêng bao trọn mọi thao tác thực hiện trên phạm vi.

## 7. An toàn từng thao tác không có nghĩa an toàn cho mọi chuỗi thao tác

### Đọc rồi cập nhật là hai thời điểm

Mã dưới đây vẫn có lỗi nếu mong muốn một bước tăng nguyên tử:

```java
// Minh hoa: map dang luu Integer va khoa da co.
Integer oldValue = counters.get(key);
counters.put(key, oldValue + 1);
```

Hai luồng có thể cùng đọc một giá trị cũ rồi ghi cùng kết quả. Cấu trúc map vẫn hoạt động đúng nhưng quy tắc đếm của ứng dụng bị sai.

Cần chọn một thao tác cập nhật thích hợp hoặc một cơ chế phối hợp đáp ứng toàn bộ quy tắc. Khi dùng các API nhận hàm như `compute/merge`, cũng phải đọc hợp đồng triển khai; không mặc định hàm luôn chỉ được gọi đúng một lần dưới tranh chấp.

### Quy tắc nhiều khóa cần thiết kế riêng

Hai cập nhật vào hai khóa khác nhau không tự thành một giao dịch. Ví dụ “chuyển một đơn vị từ khóa A sang B” đòi hỏi bảo toàn tổng trên hai ánh xạ; map đồng thời không tự gộp chuỗi ấy thành một bước bất khả phân.

Tương tự, `if (map.size() < limit) map.put(...)` không bảo đảm giới hạn cứng khi có nhiều luồng chèn. Không nên dùng một quan sát tạm thời làm quyền cập nhật độc quyền.

Nếu dùng khóa ngoài để bảo vệ một quy tắc, mọi đường liên quan phải cùng tuân thủ giao thức đó. `synchronized(map)` ở một nơi không tự chặn các luồng khác đang gọi API map mà không lấy cùng khóa.

## 8. Duyệt nhất quán yếu và thao tác hàng loạt

Iterator của `ConcurrentSkipListMap` có tính **nhất quán yếu** (weak consistency). Có thể duyệt trong khi cấu trúc được cập nhật, nhưng không được hiểu kết quả là ảnh chụp toàn bộ map tại một thời điểm duy nhất.

Ví dụ nếu luồng khác thêm nhiều mục trong lúc duyệt, vòng lặp có thể quan sát một phần thay đổi. Không dựa vào việc không có `ConcurrentModificationException` để kết luận dữ liệu đã đứng yên.

Các thao tác hàng loạt như `putAll` và `clear` không được bảo đảm nguyên tử như một giao dịch trên toàn map. Entry do `ConcurrentSkipListMap` và các khung nhìn của nó trả về là ảnh chụp ánh xạ, không hỗ trợ `setValue`. Muốn cập nhật, dùng API map thích hợp. Xem [quy tắc duyệt, entry và thao tác hàng loạt](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html).

Sao chép bằng `new TreeMap<>(map)` cho một cấu trúc mới tách khỏi cập nhật tương lai. Tuy nhiên, nếu nguồn đang thay đổi trong lúc sao chép, không mặc định bản sao ấy là ảnh chụp nhất quán của mọi khóa tại cùng một thời điểm. Nếu nghiệp vụ yêu cầu tính nhất quán đó, cần cơ chế tạo ảnh chụp phù hợp.

## 9. Khả năng nhìn thấy dữ liệu và trạng thái bên trong giá trị

`ConcurrentMap` có bảo đảm về công bố dữ liệu: các hành động trước khi một luồng đặt đối tượng làm khóa hoặc giá trị có quan hệ happens-before với các hành động sau khi luồng khác truy cập hoặc lấy đối tượng ấy ra qua map. Xem [ConcurrentMap: Memory consistency effects](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentMap.html).

Bảo đảm này không biến một đối tượng giá trị có thể thay đổi thành đối tượng an toàn luồng cho mọi thao tác về sau.

Ví dụ nếu giá trị là một `ArrayList`, hai luồng gọi `map.get(key).add(...)` vẫn đang cùng sửa một danh sách thường. Map bảo vệ thao tác ánh xạ; nó không tự bao mọi phương thức của đối tượng bên trong bằng một khóa.

Các cách thiết kế thường dùng gồm giá trị bất biến và thay thế có điều kiện, hoặc giá trị tự có cơ chế đồng bộ phù hợp. Ví dụ của bài dùng `String` bất biến để tập trung vào hợp đồng map.

## 10. Chọn cấu trúc theo yêu cầu

| Nhu cầu chính | Lựa chọn để xem xét |
| --- | --- |
| Dữ liệu riêng một luồng hoặc có giao thức khóa ngoài rõ | `TreeMap` khi cần thứ tự |
| Dùng chung nhiều luồng, không cần thứ tự khóa hay truy vấn khoảng | `ConcurrentHashMap` |
| Dùng chung nhiều luồng, cần điều hướng và phạm vi theo khóa | `ConcurrentSkipListMap` |

`ConcurrentHashMap` không cung cấp các phép điều hướng theo thứ tự khóa như `floorKey/subMap`; xem [ConcurrentHashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html). `TreeMap` có thứ tự nhưng không tự đồng bộ; xem [TreeMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeMap.html).

Không chọn chỉ theo tên hoặc một con số benchmark rời rạc. Cần xét số lượng phần tử, tần suất cập nhật, nhu cầu truy vấn khoảng, comparator và yêu cầu nhất quán của nghiệp vụ. Map có thứ tự đồng thời hữu ích khi chính thứ tự ấy phục vụ những truy vấn thực tế.

## 11. Kiểm thử và thực hành

1. Chạy ví dụ nhiều lần, xác nhận luôn có một lần chèn thành công nhưng không yêu cầu A hay B thắng.
2. Đổi hai luồng thành nhiều luồng cùng đăng ký khóa 10; vẫn không xóa khóa trong giai đoạn tranh chấp và xác nhận chỉ một lần chèn.
3. Cho một luồng thay giá trị giữa lần đọc và `replace(expected,...)`; kiểm tra nơi gọi xử lý kết quả false đúng cách.
4. Thêm dữ liệu qua `subMap`, kiểm tra map gốc thấy cập nhật và khóa ngoài phạm vi bị từ chối.
5. Viết một vòng duyệt trong khi luồng khác cập nhật. Chỉ kiểm tra những tính chất được hợp đồng bảo đảm; không cố định một dãy stdout phụ thuộc lịch chạy.
6. Phân tích quy tắc “giới hạn tối đa N khóa” hoặc “chuyển số lượng giữa hai khóa”. Chỉ ra vì sao an toàn từng lời gọi chưa giải quyết toàn bộ quy tắc.

Một lần chạy không gặp lỗi không thay cho lập luận dựa trên hợp đồng. Ví dụ tranh khóa kiểm tra một tính chất cụ thể; nó không chứng minh mọi chuỗi thao tác trong ứng dụng đều nguyên tử.
