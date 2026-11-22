# So sánh skip list với map đồng thời không cần thứ tự khóa

## 1. Bắt đầu từ truy vấn mà ứng dụng thật sự cần

Khi dùng chung map giữa nhiều luồng, hai lựa chọn thường gặp trong JDK là:

- `ConcurrentHashMap<K,V>`: map đồng thời dựa trên bảng băm, không cam kết thứ tự khóa.
- `ConcurrentSkipListMap<K,V>`: map đồng thời duy trì thứ tự khóa và hỗ trợ điều hướng.

Cả hai đều hữu ích, nhưng chúng phục vụ các kiểu truy vấn khác nhau. Điểm lựa chọn không chỉ là “nhiều luồng thì dùng lớp nào?”, mà còn là **ứng dụng có thực sự cần thứ tự đang được duy trì trong lúc cập nhật không?**

Tra cứu phiên làm việc bằng mã định danh thường chỉ cần đúng khóa. Tra cứu sự kiện gần nhất trước một thời điểm hoặc lấy các mốc trong khoảng lại cần một quan hệ thứ tự. Đây là sự khác biệt về hợp đồng dữ liệu, trước khi đo tốc độ.

Các so sánh trong bài dựa trên API hiện hành: [ConcurrentHashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html) và [ConcurrentSkipListMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html).

## 2. Bảng so sánh khả năng

| Tiêu chí | ConcurrentHashMap | ConcurrentSkipListMap |
| --- | --- | --- |
| Giao diện đồng thời chính | `ConcurrentMap` | `ConcurrentNavigableMap` |
| Tổ chức dữ liệu | Bảng băm | Skip list có thứ tự |
| Thứ tự duyệt khóa | Không có cam kết sắp xếp | Theo thứ tự tự nhiên hoặc comparator |
| Tra cứu đúng khóa | Có | Có |
| `putIfAbsent/replace/remove` có điều kiện | Có | Có |
| `floorKey/ceilingKey/lowerKey/higherKey` | Không có API điều hướng đó | Có |
| `subMap/headMap/tailMap` theo phạm vi khóa | Không có khung nhìn theo thứ tự đó | Có |
| Khung nhìn chiều ngược | Không có ý nghĩa thứ tự khóa được bảo đảm | Có `descendingMap` |
| Lưu khóa hoặc giá trị null | Không | Không |
| Duyệt trong khi có cập nhật | Có, không phải ảnh chụp cố định | Có, không phải ảnh chụp cố định |

`ConcurrentNavigableMap` kết hợp hợp đồng `ConcurrentMap` và `NavigableMap`, kể cả với các khung nhìn khoảng. Xem [ConcurrentNavigableMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentNavigableMap.html).

Đừng hiểu “không có thứ tự” là “luôn in ra ngẫu nhiên”. Một lần chạy `ConcurrentHashMap` có thể tình cờ cho các khóa theo thứ tự tăng. Không có cam kết nghĩa là chương trình không được dựa vào thứ tự quan sát được ấy.

## 3. Điểm chung: cập nhật ánh xạ theo hợp đồng đồng thời

Hai lớp cùng cung cấp các thao tác cập nhật có điều kiện:

```java
map.putIfAbsent(key, candidate);
map.replace(key, expectedValue, replacement);
map.remove(key, expectedValue);
```

Đoạn trên chỉ minh họa lời gọi. Cần xử lý đúng kết quả trả về của từng phương thức.

Các thao tác này giúp tránh tách kiểm tra–cập nhật bằng nhiều lời gọi thường. Tuy nhiên, một chuỗi cập nhật nhiều khóa vẫn không tự trở thành giao dịch. Xem [ConcurrentMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentMap.html).

Ví dụ đếm bằng `get` rồi `put(old + 1)` vẫn có thể mất cập nhật trên cả hai map. Chọn lớp đồng thời là một phần; chọn đúng thao tác cho quy tắc cần nguyên tử là phần khác.

Trong chương trình dưới đây, hai luồng dùng `merge` để tăng một bộ đếm. Hàm `Integer::sum` chỉ tính tổng, không có tác động phụ nên phù hợp với việc một triển khai có thể phải tính lại khi tranh chấp.

## 4. Ví dụ đầy đủ chạy trên Java 17+

Tệp `ConcurrentMapComparison.java`:

```java
import java.util.Objects;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.ConcurrentNavigableMap;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.CountDownLatch;

public class ConcurrentMapComparison {
    private static void exercise(String label, ConcurrentMap<Integer, Integer> map)
            throws InterruptedException {
        map.put(10, 1);
        map.put(30, 3);
        CountDownLatch start = new CountDownLatch(1);

        Runnable addCounts = () -> {
            try {
                start.await();
                for (int i = 0; i < 2000; i++) {
                    map.merge(20, 1, Integer::sum);
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(addCounts);
        Thread b = new Thread(addCounts);
        a.start();
        b.start();
        start.countDown();
        a.join();
        b.join();

        if (!Objects.equals(4000, map.get(20))) {
            throw new AssertionError(label + ": lost count");
        }
        System.out.println(label + " count=" + map.get(20));
        System.out.println(label + " normalized=" + new TreeMap<>(map));
    }

    public static void main(String[] args) throws InterruptedException {
        ConcurrentMap<Integer, Integer> hash = new ConcurrentHashMap<>();
        ConcurrentNavigableMap<Integer, Integer> ordered =
                new ConcurrentSkipListMap<>();

        exercise("hash", hash);
        exercise("skip", ordered);

        System.out.println("same mappings=" + hash.equals(ordered));
        System.out.println("skip ordered keys=" + ordered.navigableKeySet());
        System.out.println("skip floorKey(25)=" + ordered.floorKey(25));
        System.out.println("skip range [10,30)="
                + ordered.subMap(10, true, 30, false));

        System.out.println("hash filtered and sorted keys="
                + hash.keySet().stream()
                      .filter(key -> key >= 10 && key < 30)
                      .sorted()
                      .toList());
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```shell
javac -encoding UTF-8 ConcurrentMapComparison.java
java ConcurrentMapComparison
```

Kết quả chính xác:

```text
hash count=4000
hash normalized={10=1, 20=4000, 30=3}
skip count=4000
skip normalized={10=1, 20=4000, 30=3}
same mappings=true
skip ordered keys=[10, 20, 30]
skip floorKey(25)=20
skip range [10,30)={10=1, 20=4000}
hash filtered and sorted keys=[10, 20]
```

## 5. Ví dụ chứng minh điều gì?

### Cả hai cùng đáp ứng thao tác đếm được chọn

Mỗi luồng tăng khóa 20 đúng 2.000 lần. Sau khi chờ cả hai kết thúc bằng `join()`, kết quả là 4.000 trên mỗi map.

Chương trình kiểm tra trực tiếp giá trị cuối bằng `AssertionError` nếu sai. Đây là kiểm tra tính đúng đắn của thao tác trong tình huống cụ thể; không phải bằng chứng mọi chuỗi thao tác đều nguyên tử.

### normalized chỉ là cách in ổn định

Chương trình in:

```java
new TreeMap<>(map)
```

để chuẩn hóa thứ tự hiển thị sau khi các luồng ghi đã kết thúc. Dòng `hash normalized=...` không có nghĩa `ConcurrentHashMap` tự duy trì thứ tự.

Bản sao được tạo trong ví dụ trên nguồn đã ổn định. Nếu tạo bản sao trong lúc các luồng vẫn cập nhật, không mặc định nó là ảnh chụp toàn map tại cùng một thời điểm.

### ordered có khả năng mà hash không cung cấp trực tiếp

`ordered.floorKey(25)` trả 20. `ordered.subMap(10, true, 30, false)` biểu diễn các ánh xạ trong khoảng `[10,30)`.

Với map băm, ví dụ phải duyệt các khóa, lọc theo điều kiện số học rồi sắp xếp kết quả. Đoạn stream chạy sau khi các luồng ghi đã kết thúc và trả một danh sách, không phải một khung nhìn khoảng đang hoạt động của map gốc.

Hai kết quả nhìn giống nhau trong dữ liệu nhỏ nhưng được tạo bởi hai mô hình khác nhau.

## 6. Duy trì thứ tự khác với sắp xếp khi cần hiển thị

### Khi truy vấn khoảng là một phần thường xuyên của nghiệp vụ

Giả sử một chỉ mục sự kiện phải thường xuyên trả các mốc giữa hai thời điểm. Skip list duy trì thứ tự trong quá trình cập nhật, nên API phạm vi và điều hướng là một phần trực tiếp của cấu trúc.

Khung nhìn `subMap` dùng chung dữ liệu và có giới hạn phạm vi; cập nhật trong khoảng có thể phản ánh qua nguồn và view. Nó không phải kết quả lọc cũ cần tự làm mới.

### Khi chỉ thỉnh thoảng cần một báo cáo đã sắp xếp

Một map băm có thể vẫn phù hợp nếu truy cập chính là đúng khóa, còn yêu cầu thứ tự chỉ xuất hiện khi tạo báo cáo hoặc hiển thị. Khi đó có thể lấy dữ liệu theo một cơ chế nhất quán thích hợp rồi sắp xếp bản xuất.

Không cần trả chi phí duy trì một thứ tự thường trực nếu ứng dụng không dùng nó. Ngược lại, không nên quét toàn bộ map và sắp xếp lặp lại cho một luồng truy vấn phạm vi dày đặc mà chưa đánh giá cấu trúc phù hợp hơn.

Nếu cần vừa một map băm vừa một chỉ mục có thứ tự riêng cho cùng dữ liệu, vấn đề mới là giữ hai cấu trúc nhất quán. Không mặc định cập nhật cả hai trở thành nguyên tử chỉ vì từng cấu trúc an toàn luồng.

## 7. Mô hình khóa cũng khác nhau

### Map băm dựa trên equals và hashCode

Với `ConcurrentHashMap`, khóa cần hợp đồng `equals/hashCode` đúng và ổn định khi đang nằm trong map. Hàm băm phân tán kém hoặc nhiều khóa trùng hash có thể làm ảnh hưởng hiệu năng.

Một số chi tiết nội bộ có thể dùng phép so sánh để xử lý va chạm, nhưng điều đó không tạo cam kết rằng `keySet` được duyệt theo thứ tự khóa.

### Skip list dựa trên phép so sánh

Với `ConcurrentSkipListMap`, các khóa phải so sánh được theo thứ tự tự nhiên hoặc comparator. Kết quả so sánh bằng 0 quyết định hai khóa được xem là cùng một vị trí thứ tự.

Nếu comparator xem hai khóa khác nhau theo equals là bằng nhau, map có thứ tự có thể giữ hoặc cập nhật một ánh xạ trong khi map băm giữ hai khóa riêng. Khi so sánh hai lựa chọn, phải bảo đảm mô hình danh tính khóa nhất quán với yêu cầu, không chỉ thay constructor.

Các ví dụ dùng `Integer`, có thứ tự tự nhiên nhất quán với equals, nên phép so sánh ánh xạ cuối cùng có ý nghĩa rõ ràng.

Không sửa các thuộc tính quyết định hash, equals hoặc thứ tự của một khóa khi nó còn trong cấu trúc. Khả năng truy cập đồng thời không tự sửa được dữ liệu khóa bị thay đổi như vậy.

## 8. Không mặc định hợp đồng callback giống nhau

Hai lớp cùng có `computeIfAbsent`, nhưng không nên suy rằng mọi chi tiết về lời gọi hàm đều giống nhau.

- Với `ConcurrentHashMap`, lời gọi phương thức được thực hiện nguyên tử; hợp đồng nêu hàm được gọi đúng một lần cho mỗi lời gọi phương thức khi khóa vắng, và không gọi nếu khóa có. Hàm nên ngắn, đơn giản và không sửa map trong quá trình tính.
- Với `ConcurrentSkipListMap`, không có bảo đảm tương ứng rằng hàm được áp dụng đúng một lần một cách nguyên tử chỉ khi vắng mặt.

Xem [ConcurrentHashMap.computeIfAbsent](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html) và [ConcurrentSkipListMap.computeIfAbsent](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html).

Ngay cả bảo đảm của `ConcurrentHashMap` cũng không có nghĩa một khóa chỉ có thể kích hoạt khởi tạo đúng một lần trong toàn bộ vòng đời ứng dụng: giá trị có thể bị xóa, hàm có thể trả null hoặc thất bại, rồi lời gọi sau lại cần tính.

Khi di chuyển giữa hai triển khai, hãy kiểm tra các callback có tác động phụ, có giữ tài nguyên hoặc dựa vào giả định số lần gọi không. Tính đúng đắn của ví dụ đếm chỉ phụ thuộc cập nhật merge và hàm cộng thuần, không phụ thuộc số lần callback được thử.

## 9. Duyệt đồng thời không phải chụp trạng thái toàn cục

Cả hai map đều cho phép quan sát trong lúc có cập nhật mà không dựa trên cơ chế fail-fast của collection thường. Nhưng điều đó không biến vòng duyệt thành ảnh chụp nhất quán.

Một vòng lặp có thể quan sát dữ liệu phản ánh những thời điểm khác nhau trong quá trình cập nhật. Các quan sát tổng hợp như kích thước hoặc kiểm tra toàn map cần được diễn giải thận trọng khi nguồn chưa đứng yên. Xem [hợp đồng quan sát đồng thời của ConcurrentHashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html) và [quy tắc iterator của ConcurrentSkipListMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html).

Thứ tự khóa trong skip list vẫn có ý nghĩa, nhưng không đảm bảo rằng mọi ánh xạ trong một dãy kết quả từng cùng tồn tại với nhau tại một thời điểm duy nhất.

Nếu nghiệp vụ cần báo cáo nhất quán trên nhiều khóa, cần cơ chế ảnh chụp hoặc giao thức phối hợp phù hợp. Đổi từ map băm sang skip list không tự giải quyết yêu cầu ấy.

Giá trị có thể thay đổi bên trong cũng cần thiết kế riêng. Ví dụ một `ArrayList` được lưu làm giá trị không tự trở nên an toàn khi hai luồng cùng sửa danh sách chỉ vì map chứa nó là concurrent.

## 10. So sánh hiệu năng theo đúng câu hỏi

Tài liệu `ConcurrentSkipListMap` nêu chi phí trung bình kỳ vọng `O(log n)` cho các thao tác chính. `ConcurrentHashMap` được thiết kế cho tra cứu và cập nhật đồng thời qua bảng băm, nhưng thời gian thực tế phụ thuộc phân bố khóa, va chạm, mở rộng và tranh chấp.

Không kết luận “một lớp luôn nhanh hơn lớp kia” từ một vòng lặp nhỏ hoặc chỉ từ tên cấu trúc. Cần đo đúng loại tải:

- Tra cứu khóa có sẵn và khóa vắng.
- Tỷ lệ đọc, thêm, thay và xóa.
- Khóa phân tán hay nhiều luồng tranh cùng vài khóa.
- Tần suất truy vấn khoảng và số phần tử phải trả về.
- Chi phí comparator hoặc hashCode.
- Kích thước dữ liệu, cấp phát và đặc điểm bộ nhớ.
- Độ trễ cùng thông lượng, không chỉ tổng thời gian một lần chạy.

Đoạn chương trình trong bài chạy hai thử nghiệm nối tiếp, có chốt và tạo luồng. Nó không phải benchmark, không dùng để xếp hạng tốc độ.

Khi yêu cầu bắt buộc có `floorKey/subMap`, hãy đánh giá cả chi phí tự quét/sắp xếp mà map băm sẽ cần để trả cùng kết quả. So sánh hai lời gọi get đơn lẻ không đại diện cho toàn bộ nghiệp vụ đó.

## 11. Cách chọn trong một số tình huống

| Tình huống | Hướng chọn ban đầu |
| --- | --- |
| Cache tra theo ID; không cần thứ tự ID | `ConcurrentHashMap` |
| Bộ đếm theo tên/mã; không dùng truy vấn khoảng | `ConcurrentHashMap` |
| Chỉ mục mốc thời gian cần mốc trước/sau và khoảng | `ConcurrentSkipListMap` |
| Bảng ngưỡng cần floor/ceiling trong khi cập nhật đồng thời | `ConcurrentSkipListMap` |
| Chỉ cần sắp xếp một bản báo cáo hiếm khi chạy | Xem xét map băm và bản xuất được sắp xếp |
| Cần giao dịch nhiều khóa hoặc ảnh chụp toàn cục | Thiết kế cơ chế nhất quán bổ sung |

Đây là điểm khởi đầu dựa trên khả năng cần dùng, không phải kết luận thay cho đo đạc và quy tắc nghiệp vụ.

Ở ranh giới thành phần, có thể dùng kiểu `ConcurrentMap` nếu chỉ cần tra cứu/cập nhật đồng thời. Nếu nơi gọi thật sự cần điều hướng và khoảng, thể hiện yêu cầu ấy qua `ConcurrentNavigableMap` để tránh giấu khả năng bắt buộc sau một kiểu quá hẹp.

## 12. Thực hành

1. Bỏ phần truy vấn khoảng khỏi ví dụ; chỉ giữ bộ đếm. Xác định hợp đồng chung nào còn đủ để viết hàm xử lý.
2. Thêm truy vấn “khóa lớn nhất không vượt 27”. Thực hiện trực tiếp trên skip list và bằng một phép quét rõ ràng trên map băm, sau khi các luồng ghi kết thúc.
3. Tạo bộ dữ liệu mà thứ tự duyệt map băm tình cờ tăng dần. Giải thích vì sao chương trình vẫn không được dựa vào điều đó.
4. Dùng comparator không nhất quán với equals trong một bản thử riêng, quan sát số khóa của hai loại map và giải thích khác biệt.
5. Thiết kế một phép đo cho tải thật gồm nhiều truy vấn khoảng. Liệt kê cả chi phí chuẩn bị/sắp xếp kết quả, thay vì chỉ đo get.
6. Phân tích yêu cầu báo cáo nhất quán trong lúc có cập nhật. Chỉ ra vì sao thứ tự và an toàn từng thao tác vẫn chưa đủ.
