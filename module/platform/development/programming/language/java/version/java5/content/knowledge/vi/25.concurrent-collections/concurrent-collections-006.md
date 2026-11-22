# Iterator nhất quán yếu và giới hạn ảnh chụp trạng thái

## 1. Duyệt được khi có cập nhật không đồng nghĩa nhìn thấy một thời điểm duy nhất

Khi một collection được nhiều luồng sử dụng, luồng đọc có thể cần duyệt dữ liệu trong lúc luồng khác thêm, sửa hoặc xóa. Dừng mọi bên ghi để duyệt một tập lớn đôi khi quá tốn kém. Một số collection đồng thời vì vậy cho phép lượt duyệt tiếp tục mà không yêu cầu khóa toàn bộ collection.

Cái giá cần hiểu rõ là mức nhất quán của kết quả quan sát. Iterator nhất quán yếu (weakly consistent iterator) cho phép duyệt trong bối cảnh có cập nhật, nhưng không biến toàn bộ kết quả thành một ảnh chụp nguyên tử (atomic snapshot) của collection ở đúng một thời điểm.

Ví dụ, một bảng giám sát có thể chấp nhận các giá trị được đọc ở những thời điểm hơi khác nhau. Một phép kiểm tra ràng buộc giữa nhiều tài khoản hoặc nhiều trạng thái liên quan lại có thể cần một phiên bản tổng thể nhất quán. Chọn sai mức bảo đảm có thể tạo kết luận sai dù không xuất hiện ngoại lệ.

Trong bài, `ConcurrentHashMap` đại diện cho iterator nhất quán yếu và `CopyOnWriteArrayList` đại diện cho iterator kiểu ảnh chụp. Các API vẫn áp dụng trong Java hiện đại; ví dụ chạy được với Java 17 trở lên.

## 2. Ba hợp đồng duyệt cần phân biệt

| Cách duyệt | Ví dụ | Có nghĩa gì khi collection thay đổi? | Có ảnh chụp cố định không? |
| --- | --- | --- | --- |
| Phát hiện sửa đổi theo khả năng tốt nhất (fail-fast) | Iterator của `ArrayList`, `HashMap` trong những trường hợp sửa đổi không được phép | Có thể ném `ConcurrentModificationException` để bộc lộ cách dùng sai | Không |
| Nhất quán yếu | Iterator của `ConcurrentHashMap` | Có thể tiếp tục khi collection được cập nhật; quan sát thay đổi theo hợp đồng của lớp | Không có bảo đảm ảnh chụp toàn bộ map |
| Theo ảnh chụp | Iterator của `CopyOnWriteArrayList` | Duyệt mảng đã được chọn lúc tạo iterator, không nhận các thay đổi cấu trúc về sau | Có ảnh chụp cấu trúc/tham chiếu của mảng đó |

Không nên dùng nhãn không chính thức “fail-safe” để gom mọi trường hợp không ném ngoại lệ vào cùng một cơ chế. Iterator nhất quán yếu và iterator theo ảnh chụp có bảo đảm quan sát khác nhau.

`ConcurrentModificationException` không phải một cơ chế khóa hay một máy dò chắc chắn mọi cuộc tranh chấp. Ngay một luồng cũng có thể vi phạm hợp đồng khi sửa trực tiếp collection trong lúc dùng iterator fail-fast. Ngược lại, không thấy ngoại lệ không chứng minh mã an toàn. Xem [ConcurrentModificationException — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ConcurrentModificationException.html).

## 3. Ý nghĩa cụ thể với ConcurrentHashMap

Iterator từ `keySet()`, `values()` và `entrySet()` của `ConcurrentHashMap` được thiết kế để tiếp tục khi map bị cập nhật. Nó không ném `ConcurrentModificationException` chỉ vì những cập nhật đồng thời đó.

Một thay đổi xảy ra sau khi tạo iterator có thể được phản ánh hoặc không được phản ánh trong lượt duyệt, theo vị trí và thời điểm quan sát. Không đặt yêu cầu rằng mọi phần tử mới phải xuất hiện, mọi phần tử vừa xóa phải biến mất ngay, hay mọi giá trị đều thuộc đúng thời điểm tạo iterator.

Đây không phải quyền đọc dữ liệu tùy tiện ngoài hợp đồng bộ nhớ. Các truy cập của concurrent collection vẫn có bảo đảm công bố dữ liệu tương ứng. Điểm còn thiếu là một thời điểm quan sát duy nhất áp dụng cho toàn bộ kết quả nhiều phần tử.

Một iterator vẫn nên thuộc một luồng đọc; collection cho phép ghi đồng thời không có nghĩa nhiều luồng có thể tùy ý cùng gọi `next()` trên chính một iterator mà không phối hợp. `ConcurrentHashMap` cũng không quy định thứ tự duyệt khóa. Nếu cần in kết quả đã thu theo thứ tự chữ cái, có thể sắp xếp bản thu riêng, nhưng việc sắp xếp không làm dữ liệu nguồn trở thành ảnh chụp nguyên tử.

Các bảo đảm duyệt và giới hạn của các phép quan sát tổng thể được mô tả trong [ConcurrentHashMap — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).

## 4. Vì sao kết quả có thể không đại diện cho bất kỳ thời điểm nào?

Xét hai mục A và B. Bên ghi thay A trước rồi thay B. Một lượt đọc nhiều phần tử không có cơ chế chụp chung có thể gặp lịch quan sát sau:

| Thứ tự | Bên đọc | Bên ghi | Trạng thái map thực tế sau bước ghi |
| --- | --- | --- | --- |
| Ban đầu | Chưa đọc | A=0, B=0 | `{A=0, B=0}` |
| 1 | Đọc được A=0 | Chưa thay đổi | `{A=0, B=0}` |
| 2 | Chưa đọc B | Đổi A thành 1 | `{A=1, B=0}` |
| 3 | Chưa đọc B | Đổi B thành 1 | `{A=1, B=1}` |
| 4 | Đọc được B=1 | Không đổi nữa | `{A=1, B=1}` |

Bản thu của lượt đọc là `{A=0, B=1}`, dù trạng thái ấy không xuất hiện trong các bước ghi đã nêu. Đây là một lịch quan sát có thể xảy ra khi không có ảnh chụp chung, không phải một output bắt buộc của `ConcurrentHashMap` trên mọi lần chạy hoặc mọi thứ tự duyệt.

Cùng nguyên tắc đó, tính tổng bằng một lượt `forEach` hay stream trên dữ liệu đang đổi có thể cộng các phần tử được nhìn ở những thời điểm khác nhau. Có thể hữu ích cho giám sát gần thời gian thực, nhưng không tự là bằng chứng một ràng buộc toàn cục đang đúng.

`size()`, `isEmpty()` và các trạng thái tổng thể khác cũng có thể là quan sát tạm thời khi map đang bị cập nhật. Không lấy chúng làm điều kiện chắc chắn để điều khiển một quy trình nhiều bước đòi hỏi trạng thái không đổi.

## 5. Sao chép collection không tự tạo ảnh chụp nguyên tử

```java
// Đoạn minh họa; live là ConcurrentHashMap<String, Integer> đang bị cập nhật.
Map<String, Integer> detached = new HashMap<>(live);
Map<String, Integer> readOnly = Map.copyOf(live);
```

Sau khi sao chép xong, cấu trúc của `detached` tách khỏi map nguồn. `readOnly` là một map không cho sửa qua API của nó. Tuy nhiên, dữ liệu đầu vào được thu trong một khoảng thời gian, trong khi bên ghi vẫn có thể chạy; bản sao không tự bảo đảm nội dung nguồn đồng thời tồn tại như vậy ở một thời điểm duy nhất.

`new ArrayList<>(live.values())`, stream rồi `toList()`, hoặc `toArray()` cũng không tự thêm một giao thức chụp toàn cục vào `ConcurrentHashMap`. Chuyển kết quả sang một cấu trúc ổn định chỉ giữ lại điều đã quan sát, không sửa lại lịch quan sát trước đó.

Cần phân biệt hai thuộc tính:

- **Bản thu ổn định sau khi tạo:** bên ghi nguồn không tự thêm/xóa mục trong cấu trúc bản sao.
- **Ảnh chụp nhất quán tại một thời điểm:** toàn bộ mục và giá trị đáp ứng một phiên bản chung của trạng thái nguồn.

Thuộc tính đầu không kéo theo thuộc tính sau. Cả hai cũng chưa nói rằng các đối tượng bên trong được sao chép sâu.

## 6. Ảnh chụp của CopyOnWriteArrayList khác ở đâu?

Khi tạo iterator, `CopyOnWriteArrayList` cho iterator dùng mảng của phiên bản tại thời điểm đó. Các thao tác cập nhật list xuất bản mảng khác; iterator cũ không chuyển sang mảng mới.

Vì vậy, nếu list ban đầu là `[A, B]`, tạo iterator rồi thêm C và xóa A, iterator cũ vẫn duyệt `[A, B]` trong khi một lần đọc list hiện tại có thể thấy `[B, C]`. Các thao tác thay đổi qua iterator như `remove()` không được hỗ trợ và ném `UnsupportedOperationException`.

Ảnh chụp này giữ các tham chiếu phần tử, không tự sao chép sâu đối tượng. Nếu list chứa một đối tượng mutable và luồng khác sửa trường của chính đối tượng đó, iterator cũ vẫn giữ cùng tham chiếu. Muốn ảnh chụp nội dung đối tượng, cần dữ liệu bất biến hoặc cơ chế sao chép/đồng bộ phù hợp.

Cách sao chép mảng có chi phí khi cập nhật; không đổi sang `CopyOnWriteArrayList` chỉ để tránh ngoại lệ trong một hệ thống ghi liên tục. Nó thường phù hợp khi số lần đọc/duyệt vượt xa số lần thay đổi, chẳng hạn một danh sách đăng ký ít đổi. Xem [CopyOnWriteArrayList — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html).

## 7. Chương trình chạy đầy đủ

Chương trình tạo một iterator nhất quán yếu, nhận một phần tử, rồi để một writer thay đổi map trước khi duyệt nốt. Nó không kiểm tra một tập kết quả cố định cho iterator yếu, vì hợp đồng không yêu cầu tập đó cố định. Các dòng stdout còn lại được tạo sau các điểm phối hợp rõ ràng.

Lưu vào `IteratorConsistencyDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicReference;

public class IteratorConsistencyDemo {
    record Totals(int left, int right) {}

    private static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected result");
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, Integer> live = new ConcurrentHashMap<>();
        live.put("A", 1);
        live.put("B", 1);

        Iterator<Map.Entry<String, Integer>> weak =
                live.entrySet().iterator();
        List<Map.Entry<String, Integer>> observed = new ArrayList<>();
        observed.add(weak.next());

        Thread writer = new Thread(() -> {
            live.put("A", 2);
            live.remove("B");
            live.put("C", 1);
        }, "writer");
        writer.start();
        writer.join();

        weak.forEachRemaining(observed::add);
        System.out.println("weak traversal completed");
        System.out.println("stable final map: " + new TreeMap<>(live));

        CopyOnWriteArrayList<String> names =
                new CopyOnWriteArrayList<>(List.of("A", "B"));
        Iterator<String> snapshotIterator = names.iterator();
        names.add("C");
        names.remove("A");

        List<String> oldNames = new ArrayList<>();
        snapshotIterator.forEachRemaining(oldNames::add);
        check(oldNames.equals(List.of("A", "B")));
        check(names.equals(List.of("B", "C")));
        System.out.println("snapshot iterator: " + oldNames);
        System.out.println("current list: " + names);

        AtomicReference<Totals> current =
                new AtomicReference<>(new Totals(50, 50));
        Totals saved = current.get();
        current.set(new Totals(40, 60));

        check(saved.left() + saved.right() == 100);
        System.out.println("saved immutable state: " + saved);
        System.out.println("current immutable state: " + current.get());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 IteratorConsistencyDemo.java
java IteratorConsistencyDemo
```

Stdout:

```text
weak traversal completed
stable final map: {A=2, C=1}
snapshot iterator: [A, B]
current list: [B, C]
saved immutable state: Totals[left=50, right=50]
current immutable state: Totals[left=40, right=60]
```

Biến `observed` giữ những entry mà iterator yếu đã trả về. Chương trình không in hay xác nhận một thứ tự hoặc một tập entry cụ thể: các chi tiết không được bảo đảm đó không nên trở thành điều kiện đúng/sai của ví dụ.

`writer.join()` bảo đảm các lần ghi của writer đã hoàn tất trước khi main tạo `TreeMap` ở dòng in trạng thái cuối. Sau đó không còn writer nào sửa `live`, nên `{A=2, C=1}` là kết quả cuối ổn định. Ví dụ không dùng bản sao lúc nguồn đang bị sửa để chứng minh ảnh chụp nhất quán.

Iterator của `CopyOnWriteArrayList` được kiểm tra đúng `[A, B]`, còn list hiện hành là `[B, C]`, vì đó là bảo đảm ảnh chụp của lớp.

Phần `AtomicReference` minh họa một mô hình khác: gộp các giá trị liên quan vào một đối tượng `Totals` bất biến. `saved` nhận đúng một tham chiếu phiên bản, nên thay toàn bộ tham chiếu hiện tại không làm thay đổi phiên bản mà `saved` đang giữ. Đây không phải ảnh chụp của nhiều lần đọc độc lập từ một map đang đổi.

## 8. Khi cần ảnh chụp nhất quán thật sự

### Phối hợp tất cả bên ghi và thao tác chụp bằng một khóa chung

Nếu mọi thao tác thay đổi trạng thái đều giữ cùng một khóa, bên chụp có thể giữ khóa đó trong suốt quá trình sao chép. Khi ấy nguồn không bị thay đổi trong cửa sổ thu thập.

```java
// Đoạn cấu trúc minh họa trong một lớp.
private final Object gate = new Object();
private final Map<String, Integer> values = new HashMap<>();

public void updateBoth(int left, int right) {
    synchronized (gate) {
        values.put("left", left);
        values.put("right", right);
    }
}

public Map<String, Integer> snapshot() {
    synchronized (gate) {
        return Map.copyOf(values);
    }
}
```

Điều kiện thiết yếu là mọi đường đọc/ghi tới `values` phải tuân theo giao thức khóa; không để lộ map nguồn cho bên ngoài sửa trực tiếp. Các giá trị trong ví dụ là `Integer` bất biến, nên không có trường mutable bên trong bị thay ngoài khóa.

Chỉ bọc `synchronized (concurrentMap)` quanh một lượt duyệt `ConcurrentHashMap` không chặn các bên gọi `put` thông thường. Chúng không tự sử dụng monitor do ứng dụng chọn. Khóa chỉ có tác dụng phối hợp với các bên cùng tuân theo nó.

### Công bố một phiên bản bất biến

Nếu các mục phải cùng thuộc một phiên bản, có thể xây một đối tượng bất biến chứa toàn bộ trạng thái rồi công bố nó qua `volatile` hoặc `AtomicReference`. Bên đọc lấy một tham chiếu và dùng phiên bản ấy cho cả phép tính, như `Totals` trong ví dụ.

Nếu nhiều writer cùng tính phiên bản mới từ bản cũ, việc cập nhật cũng phải tránh mất thay đổi, chẳng hạn dùng một giao thức so sánh–thay thế thích hợp. Chỉ gọi `set` sau một phép tính dựa trên dữ liệu cũ không tự gộp cập nhật của nhiều writer.

Với dữ liệu thuộc cơ sở dữ liệu hay nhiều tiến trình, yêu cầu ảnh chụp còn phụ thuộc giao dịch, phiên bản và mức cô lập tương ứng. Iterator Java không tự tạo nhất quán xuyên qua những ranh giới ấy.

## 9. Chọn mức bảo đảm theo nhu cầu

| Nhu cầu | Hướng xử lý |
| --- | --- |
| Bảng giám sát chấp nhận một lượt quan sát không cùng thời điểm | Duyệt nhất quán yếu, mô tả kết quả là quan sát gần thời điểm lấy |
| Duyệt danh sách ít thay đổi và cần giữ phiên bản cấu trúc trong suốt lượt | Cân nhắc iterator theo ảnh chụp của `CopyOnWriteArrayList` |
| Tính ràng buộc chính xác giữa nhiều mục | Dùng giao thức chụp nhất quán hoặc công bố một trạng thái bất biến |
| Chỉ cập nhật một mục nếu nó vẫn đúng giá trị đã quan sát | Dùng thao tác có điều kiện như `replace(key, expected, update)` thay vì dựa vào lượt duyệt cũ |
| Xử lý mỗi phần tử như một công việc chỉ được nhận một lần | Dùng giao thức nhận việc thích hợp; iterator không phải cơ chế lấy độc quyền |

Không dựa vào một lần thử không ném ngoại lệ để suy ra mọi lịch chạy đều đúng. Với kết quả được phép biến thiên, kiểm thử những điều hợp đồng bảo đảm, phối hợp luồng bằng tín hiệu rõ ràng khi cần, và không ép một tập quan sát tình cờ thành output bắt buộc.

## 10. Tự kiểm tra

1. Iterator `ConcurrentHashMap` không ném `ConcurrentModificationException` có nghĩa là đã khóa mọi writer không? Không.
2. Thêm một khóa sau khi tạo iterator yếu có bắt buộc iterator phải thấy khóa ấy không? Không.
3. `new HashMap<>(liveConcurrentMap)` có tự bảo đảm ảnh chụp nguyên tử của nguồn đang bị sửa không? Không; bản sao chỉ ổn định sau khi thu xong.
4. Iterator `CopyOnWriteArrayList` có thấy phần tử mới thêm sau khi nó được tạo không? Không; nó dùng phiên bản mảng ban đầu.
5. Ảnh chụp mảng có tự đóng băng các trường của đối tượng mutable bên trong không? Không.
6. Khóa riêng quanh lượt duyệt có chặn các writer không sử dụng cùng khóa không? Không; mọi bên phải tuân theo giao thức phối hợp.
