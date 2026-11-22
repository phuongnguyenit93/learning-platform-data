# Truy vấn khoảng trong lúc có cập nhật đồng thời

## 1. Câu hỏi quan trọng hơn “có bị lỗi khi duyệt không?”

Giả sử nhiều luồng cùng lưu các bản ghi theo khóa, còn một luồng khác đọc các khóa trong khoảng `[20,50)`.

Có hai yêu cầu rất khác nhau:

- Hiển thị dữ liệu gần hiện tại, chấp nhận các bản ghi được quan sát ở những thời điểm khác nhau trong lúc duyệt.
- Tính một kết quả dựa trên toàn bộ khoảng tại đúng một trạng thái nhất quán.

`ConcurrentSkipListMap` hỗ trợ thao tác đồng thời trên map có thứ tự. Nhưng khả năng an toàn khi truy cập đồng thời không tự biến một lượt đọc nhiều bản ghi thành ảnh chụp nguyên tử của toàn khoảng.

Trước khi viết truy vấn, cần xác định: **phạm vi khóa là gì → các luồng có thể thay đổi gì → kết quả cần mức nhất quán nào → cách kiểm tra nào phù hợp với hợp đồng đó**. Bài dùng các API hiện hành, với ví dụ Java 17 trở lên.

## 2. View khoảng vẫn gắn với map gốc

Ví dụ minh họa trong phương thức:

```java
ConcurrentNavigableMap<Integer, String> map =
        new ConcurrentSkipListMap<>();
ConcurrentNavigableMap<Integer, String> range =
        map.subMap(20, true, 50, false);
```

Cần import hai kiểu từ `java.util.concurrent`. `range` là khung nhìn nhận các khóa `20 ≤ k < 50`, theo thứ tự tự nhiên.

Khi map gốc có thay đổi:

- Thêm khóa 25 có thể làm khóa đó xuất hiện trong range.
- Thay giá trị ở khóa 40 làm ánh xạ hiện tại của khóa đó thay đổi.
- Xóa khóa 30 loại ánh xạ đó khỏi dữ liệu gốc.
- Khóa 50 luôn bị loại khỏi range vì cờ biên trên là false.

Kết quả của `subMap` trên `ConcurrentNavigableMap` tiếp tục có hợp đồng map điều hướng đồng thời. Nó không phải map riêng được sao chép tại thời điểm gọi. Xem [ConcurrentNavigableMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentNavigableMap.html).

Giới hạn khoảng và trạng thái dữ liệu là hai chuyện khác nhau: biên vẫn là `[20,50)`, còn tập ánh xạ bên trong có thể thay đổi trong suốt thời gian view được dùng.

## 3. Iterator nhất quán yếu nghĩa là gì trong bài toán này?

Iterator của `ConcurrentSkipListMap` và các view của nó có tính nhất quán yếu (`weakly consistent`). Có thể duyệt trong khi luồng khác cập nhật; không được giả định toàn bộ kết quả tương ứng với một thời điểm duy nhất.

Một lượt đọc có thể kết hợp:

- Một Entry đã lấy trước khi giá trị được cập nhật.
- Một ánh xạ được nhìn thấy ở bước sau.
- Một phần các thay đổi xảy ra trong thời gian lượt duyệt đang tồn tại.

Không gán một danh sách kết quả cụ thể cho mọi cách đan xen. Cũng không dùng việc “không có ConcurrentModificationException” làm bằng chứng rằng đã đọc được một ảnh chụp đầy đủ.

Tài liệu [ConcurrentSkipListMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html) quy định iterator nhất quán yếu, Entry là ảnh chụp của từng ánh xạ khi được tạo và thao tác hàng loạt không được bảo đảm nguyên tử.

Với khóa và comparator ổn định, vẫn cần tôn trọng thứ tự duyệt và phạm vi view. Yêu cầu ảnh chụp toàn khoảng là một bảo đảm bổ sung, không đồng nghĩa với những đặc tính đó.

## 4. Một lịch đan xen để suy nghĩ trước khi chạy

Bắt đầu với:

```text
map   = {10=A, 20=B, 30=C, 40=D, 50=E}
range = [20,50)
```

Lịch thao tác của ví dụ:

```text
Luồng đọc                  Luồng cập nhật
---------                  ---------------
Tạo iterator
Đọc Entry đầu: 20=B
                           Đổi 20 thành B2
                           Thêm 25=X
                           Xóa 30
                           Đổi 40 thành D2
                           Đổi 50 thành E2
Đọc phần còn lại
Đọc lại range sau cập nhật
```

Entry đầu đã nhận vẫn là `20=B`, trong khi ánh xạ hiện tại ở map là `20=B2`. Đây là một lý do đủ để không gọi danh sách đã quan sát là “toàn bộ dữ liệu mới nhất”.

Với các phần tử còn lại, không viết đáp án cứng rằng iterator nhất định phải thấy đúng tập cuối cùng. Điều kiểm tra hợp lý là giữ đúng phạm vi/thứ tự theo cấu trúc được dùng và kiểm tra trạng thái cuối sau khi đã chờ writer hoàn thành.

## 5. Chương trình Java với đan xen có kiểm soát

Ví dụ dùng `CountDownLatch` để mở cổng cho luồng cập nhật và `FutureTask.get()` để chờ công việc hoàn tất, đồng thời chuyển lỗi của công việc về luồng chính.

Không dùng thời gian ngủ để đoán rằng một luồng “chắc đã chạy xong”. `CountDownLatch` là cơ chế đồng bộ có điểm mở cổng xác định; tài liệu mô tả hiệu ứng công bố bộ nhớ của `countDown/await`: [CountDownLatch](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CountDownLatch.html).

Lưu tệp `ConcurrentRangeDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.NavigableMap;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentNavigableMap;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.FutureTask;

public class ConcurrentRangeDemo {
    public static void main(String[] args) throws Exception {
        ConcurrentNavigableMap<Integer, String> map =
                new ConcurrentSkipListMap<>();
        map.put(10, "A");
        map.put(20, "B");
        map.put(30, "C");
        map.put(40, "D");
        map.put(50, "E");

        ConcurrentNavigableMap<Integer, String> range =
                map.subMap(20, true, 50, false);
        Iterator<Map.Entry<Integer, String>> iterator =
                range.entrySet().iterator();
        List<Map.Entry<Integer, String>> observed = new ArrayList<>();
        observed.add(iterator.next());

        CountDownLatch startUpdate = new CountDownLatch(1);
        FutureTask<Void> update = new FutureTask<>(() -> {
            startUpdate.await();
            map.put(20, "B2");
            map.put(25, "X");
            map.remove(30);
            map.put(40, "D2");
            map.put(50, "E2");
            return null;
        });

        Thread writer = new Thread(update, "range-updater");
        writer.start();
        startUpdate.countDown();
        update.get();

        while (iterator.hasNext()) {
            observed.add(iterator.next());
        }
        writer.join();

        boolean withinBounds = true;
        boolean ordered = true;
        Integer previous = null;
        for (Map.Entry<Integer, String> entry : observed) {
            int key = entry.getKey();
            withinBounds &= key >= 20 && key < 50;
            if (previous != null && previous >= key) {
                ordered = false;
            }
            previous = key;
        }

        if (!withinBounds || !ordered) {
            throw new AssertionError("Invalid range traversal");
        }

        NavigableMap<Integer, String> stableCopy =
                new TreeMap<>(range);

        System.out.println("first.observed=" + observed.get(0));
        System.out.println("within.bounds=" + withinBounds);
        System.out.println("ordered=" + ordered);
        System.out.println("final.range=" + range);
        System.out.println("stable.copy=" + stableCopy);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac --release 17 ConcurrentRangeDemo.java
java ConcurrentRangeDemo
```

Stdout của các dòng có kết quả được xác định bởi lịch đồng bộ trong ví dụ:

```text
first.observed=20=B
within.bounds=true
ordered=true
final.range={20=B2, 25=X, 40=D2}
stable.copy={20=B2, 25=X, 40=D2}
```

Chương trình không in cứng toàn bộ `observed` làm kết quả mong đợi. Có thể tự thêm lời gọi in danh sách đó để quan sát hành vi của JDK đang dùng, nhưng không nâng một kết quả quan sát được thành cam kết cho mọi lần chạy hay phiên bản.

Các điểm cần đối chiếu:

1. Không có writer trước lần đọc Entry đầu nên `first.observed` xác định là `20=B`.
2. Công việc cập nhật chạy trong thời gian iterator đã được tạo nhưng chưa duyệt hết.
3. Sau `update.get()`, công việc đã hoàn tất; không có writer nào khác trong chương trình.
4. Các giá trị ở `final.range` vì thế xác định được; khóa 50 không thuộc khoảng.
5. Bản sao được tạo sau khi writer dừng, nên nó được lấy từ nguồn không còn thay đổi trong ví dụ này.

## 6. Sao chép cấu trúc chưa chắc tạo ảnh chụp nguyên tử

Đoạn sau tạo một map riêng:

```java
NavigableMap<Integer, String> copy = new TreeMap<>(range);
```

Nhưng nếu nguồn vẫn đang được sửa, quá trình constructor đọc nguồn có thể quan sát các ánh xạ ở những bước khác nhau. Sau khi tạo xong, `copy` không tự thay đổi theo cấu trúc nguồn; điều đó không chứng minh nội dung của nó khớp đúng một trạng thái nguyên tử trước đó.

Cần phân biệt:

| Thuộc tính | Có được chỉ nhờ sao chép không? |
| --- | --- |
| Map kết quả có cấu trúc riêng | Có |
| Sửa cấu trúc nguồn sau khi sao chép không tự sửa kết quả | Có |
| Toàn bộ kết quả đến từ đúng một thời điểm khi nguồn đang cập nhật | Không tự được bảo đảm |
| Các đối tượng giá trị được sao chép sâu | Không |

Trong chương trình, nguồn đã hết writer trước khi sao chép nên vấn đề được kiểm soát bằng lịch đồng bộ. Trong ứng dụng thực, phải xác định cơ chế nào bảo vệ điều kiện đó.

Bọc kết quả bằng một lớp chỉ đọc cũng chỉ giới hạn thao tác sửa qua lớp bọc; nó không tự bổ sung tính nhất quán tại một thời điểm cho lần thu thập dữ liệu trước đó.

## 7. Chọn mức nhất quán theo công việc

### Khi quan sát gần hiện tại là đủ

Ví dụ bảng theo dõi hoặc màn hình vận hành có thể chấp nhận nội dung được đọc trong một khoảng thời gian ngắn. Có thể dùng trực tiếp view và iterator, miễn là sản phẩm không diễn đạt kết quả như một ảnh chụp tuyệt đối.

Nếu tính tổng từ các Entry đã thu thập, tổng đó nhất quán với chính danh sách đã thu thập. Nó chưa chắc là tổng của map tại một thời điểm xác định.

### Khi cần một trạng thái nhất quán của toàn khoảng

Phải có cơ chế bổ sung phù hợp, chẳng hạn:

- Một khóa ở mức ứng dụng mà mọi writer và bước lấy bản sao đều cùng tuân thủ.
- Tạm dừng writer tại một điểm kiểm soát rồi thu thập dữ liệu.
- Công bố các phiên bản dữ liệu bất biến và để một lần đọc giữ nguyên một phiên bản.

Không chỉ bọc riêng luồng đọc trong `synchronized(map)` rồi cho rằng các thao tác nội bộ của `ConcurrentSkipListMap` sẽ tự dùng cùng khóa ấy. Cơ chế bảo vệ ở mức ứng dụng chỉ có tác dụng khi tất cả đường cập nhật liên quan tuân theo nó.

Nếu nghiệp vụ cần cập nhật nguyên tử nhiều khóa, cũng phải giải quyết yêu cầu đó riêng. Nhiều lời gọi `put/remove` nối tiếp không tự trở thành một giao dịch.

## 8. Truy vấn nhiều bước và phân trang cũng chịu ảnh hưởng

Một chuỗi như `range.size()` rồi duyệt để tính tổng không phải một lần đọc nguyên tử. Kích thước và dữ liệu được duyệt có thể thuộc các trạng thái khác nhau.

Tương tự, `containsKey(k)` rồi `get(k)` có thể gặp việc khóa bị xóa ở giữa hai lời gọi. Khi có thể, dùng một kết quả đọc phù hợp thay cho việc kiểm tra rồi giả định trạng thái không đổi; điều này vẫn không biến nhiều khóa thành một ảnh chụp chung.

Với phân trang theo khóa cuối đã đọc:

- Bản ghi mới được thêm trước con trỏ có thể không xuất hiện ở trang sau.
- Bản ghi bị xóa có thể không còn khi trang tiếp theo được lấy.
- Các trang có thể phản ánh nhiều thời điểm.

Nếu cần một phiên đọc nhất quán qua nhiều trang, phải gắn truy vấn với cơ chế phiên bản hoặc ảnh chụp phù hợp. Chỉ có thứ tự khóa ổn định chưa đủ để bảo đảm toàn bộ phiên đã đọc mọi bản ghi đúng một lần tại cùng một trạng thái.

## 9. Kiểm thử điều đúng với hợp đồng

Một bài kiểm thử đồng thời nên kiểm tra:

- Khóa được đọc không vượt biên và cờ đã chọn.
- Thứ tự đọc phù hợp với comparator.
- Lỗi từ luồng cập nhật được chuyển về bài kiểm thử.
- Kết quả cuối sau điểm chờ hoàn thành khớp các cập nhật đã biết.
- Những bảo đảm bổ sung của ứng dụng, nếu có, được kiểm tra độc lập.

Tránh kiểm thử bắt buộc iterator đang sống phải trả đúng toàn bộ tập cuối cùng. Điều đó áp đặt bảo đảm mạnh hơn hợp đồng nhất quán yếu.

Dùng latch, future hoặc cơ chế đồng bộ có mốc rõ ràng thay vì chờ một số mili giây rồi suy đoán lịch chạy. Các quy tắc nhất quán và đồng bộ của nhóm lớp được mô tả trong [java.util.concurrent](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/package-summary.html).

Một lần chạy thành công chỉ minh họa lịch đã kiểm soát. Nó không chứng minh mọi cách đan xen đều đã được kiểm tra.

## 10. Tự kiểm tra

1. Vì sao `subMap` tạo trước khi writer chạy vẫn có thể nhìn thấy ánh xạ được thêm sau đó?
2. Không có ConcurrentModificationException có đồng nghĩa có ảnh chụp toàn khoảng không?
3. Vì sao `new TreeMap<>(range)` trong lúc writer vẫn hoạt động chưa đủ bảo đảm một trạng thái nguyên tử?
4. Trong ví dụ, điều kiện nào làm `final.range` có kết quả xác định?
5. Nếu cần một lần xuất dữ liệu nhất quán qua nhiều trang, ngoài con trỏ khóa còn cần giải quyết điều gì?

Định hướng: (1) đó là view liên kết dữ liệu gốc; (2) không; (3) thu thập nguồn diễn ra qua nhiều bước; (4) đã chờ công việc cập nhật hoàn tất và không có writer khác; (5) cơ chế giữ cùng phiên bản hoặc ảnh chụp theo yêu cầu nghiệp vụ.

Truy vấn khoảng đồng thời cần phân biệt ba bảo đảm: đúng phạm vi, đúng thứ tự và nhất quán tại một thời điểm. Hãy lựa chọn cơ chế đọc theo đúng bảo đảm mà công việc thực sự cần.
