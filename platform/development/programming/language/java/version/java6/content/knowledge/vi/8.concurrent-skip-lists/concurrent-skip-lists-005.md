# Iterator nhất quán yếu khi dữ liệu đang thay đổi

## 1. Bài toán: duyệt mà không dừng toàn bộ bên ghi

Một dịch vụ có thể vừa cập nhật chỉ mục vừa duyệt để hiển thị trạng thái. Nếu dùng một cấu trúc không hỗ trợ đồng thời rồi sửa nó tùy ý khi đang duyệt, chương trình có thể sai hoặc gặp lỗi phát hiện sửa đổi.

`ConcurrentSkipListMap` và `ConcurrentSkipListSet` cho phép truy cập đồng thời, trong đó iterator có chính sách **nhất quán yếu (weakly consistent)**.

Ý nghĩa thực tế: iterator vẫn có thể tiến trong khi cấu trúc thay đổi, nhưng một lượt duyệt không mặc nhiên là bản chụp toàn bộ dữ liệu ở một thời điểm duy nhất.

Cần phân biệt:

- **An toàn của cấu trúc:** thêm/xóa/đọc đồng thời không phá cấu trúc theo hợp đồng lớp.
- **Thứ tự duyệt:** skip list vẫn có thứ tự dựa trên comparator.
- **Tính nhất quán của toàn bộ kết quả:** các phần tử quan sát được có thể phản ánh những thời điểm khác nhau.

Tính chất thứ nhất và thứ hai không tự tạo ra tính chất thứ ba. Bài này dùng API hiện hành và ví dụ Java 17 trở lên.

## 2. Hợp đồng cần nhớ

Iterator nhất quán yếu cho phép tiếp tục duyệt song song với các thao tác khác. Nó không ném `ConcurrentModificationException` chỉ vì cấu trúc có thay đổi đồng thời. Những thay đổi xảy ra sau khi tạo iterator có thể được phản ánh, nhưng không có bảo đảm mọi thay đổi đều phải xuất hiện trong cùng lượt duyệt.

Đây là chính sách được mô tả trong [java.util.concurrent](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/package-summary.html), đồng thời được công bố cho cả [ConcurrentSkipListMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html) và [ConcurrentSkipListSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentSkipListSet.html).

### 2.1. Nhất quán yếu không có nghĩa ngẫu nhiên vô hạn

Iterator không được tùy tiện sinh ra phần tử chưa từng tồn tại hoặc bỏ qua hợp đồng thứ tự. Nhưng bên gọi không được yêu cầu nó đồng thời hành xử như:

- Một bản sao đóng băng lúc iterator được tạo.
- Một nguồn phát mọi sự kiện thêm/xóa theo thời gian.
- Một lượt đọc nguyên tử của toàn bộ cấu trúc.

Không có ghi đồng thời và dữ liệu không thay đổi, iterator vẫn duyệt bình thường. Chữ “yếu” mô tả cách phối hợp với thay đổi đồng thời, không có nghĩa một tập ổn định cũng chỉ trả dữ liệu tùy hứng.

### 2.2. So sánh ba kiểu kỳ vọng

| Chính sách | Khi dữ liệu gốc đổi | Điều không nên suy ra |
| --- | --- | --- |
| Fail-fast của một cấu trúc thông thường | Có thể phát hiện và ném lỗi sửa đổi đồng thời theo nỗ lực tốt nhất | Không phải cơ chế khóa hoặc bằng chứng chương trình an toàn |
| Iterator snapshot của cấu trúc có hợp đồng snapshot | Duyệt dữ liệu đã được xác định theo hợp đồng bản chụp | Không đồng nghĩa sao chép sâu mọi đối tượng |
| Iterator nhất quán yếu của skip list đồng thời | Cho phép duyệt tiếp, có thể phản ánh một phần thay đổi | Không phải snapshot toàn bộ ở một thời điểm |

Không gọi kiểu thứ ba là “fail-safe” rồi gán cho nó mọi thuộc tính của snapshot. Thuật ngữ chính xác cần dùng ở đây là weakly consistent.

## 3. Một lịch thay đổi và điều có thể quan sát

Giả sử set ban đầu có `[0, 10, 20]` và reader bắt đầu duyệt. Sau khi reader đã lấy 0, writer thực hiện:

```text
remove(10)
add(5)
add(15)
```

Khi writer hoàn tất, set hiện tại là `[0, 5, 15, 20]`. Tuy nhiên, iterator đã được tạo trước đó không có nghĩa vụ biến danh sách kết quả của mình thành đúng bản mới này.

Cũng không được đóng đinh kết quả iterator cũ là `[0, 10, 20]` chỉ vì đó là dữ liệu ban đầu. Những thay đổi sau khi tạo là một phần của chính sách quan sát.

Một cách kiểm chứng phù hợp trong thí nghiệm này:

- Iterator hoàn thành mà không có lỗi fail-fast do những cập nhật được hỗ trợ.
- Các phần tử được trả theo chiều tăng đang dùng.
- Những khóa quan sát được thuộc dữ liệu hợp lệ của thí nghiệm.
- Sau khi chờ writer hoàn tất và không còn bên ghi, một **iterator mới** thấy dữ liệu cuối ổn định.

Không nên kiểm tra “chắc chắn phải thấy 5” hoặc “chắc chắn không được thấy 10” trên iterator cũ, nếu điều đó không được hợp đồng cụ thể bảo đảm. Việc một JDK cho cùng kết quả trong nhiều lần chạy cũng không biến chi tiết quan sát ấy thành hợp đồng có thể dựa vào.

## 4. Chương trình có phối hợp thời điểm, không dựa vào sleep

Ví dụ dùng hai `CountDownLatch`:

1. Reader tạo iterator và lấy phần tử đầu.
2. Reader báo `firstRead`.
3. Writer chờ tín hiệu ấy rồi xóa/thêm dữ liệu.
4. Writer báo `changed`.
5. Reader tiếp tục iterator đã tạo từ trước.

Như vậy chắc chắn có thay đổi **trong vòng đời lượt duyệt**. Không cần đoán rằng `Thread.sleep` bao lâu thì hai luồng sẽ chạy theo ý muốn.

Chương trình không in danh sách chính xác do iterator cũ trả về, vì chi tiết đó không phải kết quả cần đóng đinh. Nó in các thuộc tính được kiểm tra và trạng thái cuối sau khi đã chờ các tác vụ.

Lưu thành **WeakIteratorDemo.java**:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.ConcurrentSkipListSet;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class WeakIteratorDemo {
    public static void main(String[] args) throws Exception {
        ConcurrentSkipListSet<Integer> values =
                new ConcurrentSkipListSet<>(List.of(0, 10, 20));
        CountDownLatch firstRead = new CountDownLatch(1);
        CountDownLatch changed = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        List<Integer> observed;
        try {
            Future<List<Integer>> reader = pool.submit(() -> {
                List<Integer> result = new ArrayList<>();
                Iterator<Integer> iterator = values.iterator();
                result.add(iterator.next());
                firstRead.countDown();
                changed.await();
                while (iterator.hasNext()) {
                    result.add(iterator.next());
                }
                return result;
            });
            Future<Void> writer = pool.submit(() -> {
                firstRead.await();
                try {
                    values.remove(10);
                    values.add(5);
                    values.add(15);
                } finally {
                    changed.countDown();
                }
                return null;
            });
            writer.get();
            observed = reader.get();
        } finally {
            pool.shutdownNow();
        }

        boolean ascending = true;
        for (int i = 1; i < observed.size(); i++) {
            ascending &= observed.get(i - 1) < observed.get(i);
        }
        Set<Integer> allowed = Set.of(0, 5, 10, 15, 20);
        boolean validKeys = observed.stream().allMatch(allowed::contains);
        if (!ascending || !validKeys) throw new AssertionError(observed);
        System.out.println("Traversal completed: true");
        System.out.println("Ascending order: " + ascending);
        System.out.println("Only valid keys: " + validKeys);
        System.out.println("Final set after join: " + values);
        System.out.println("Fresh traversal: " + new ArrayList<>(values));

        Iterator<Integer> removable = values.iterator();
        while (removable.hasNext()) {
            if (removable.next() == 15) removable.remove();
        }
        System.out.println("After iterator.remove: " + values);

        ConcurrentSkipListMap<Integer, String> map =
                new ConcurrentSkipListMap<>();
        map.put(1, "old");
        Map.Entry<Integer, String> entry =
                map.entrySet().iterator().next();
        map.put(1, "new");
        System.out.println("Saved entry value: " + entry.getValue());
        System.out.println("Current map value: " + map.get(1));
        try {
            entry.setValue("attempt");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Entry setValue rejected");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 WeakIteratorDemo.java
java WeakIteratorDemo
```

Kết quả chuẩn:

```text
Traversal completed: true
Ascending order: true
Only valid keys: true
Final set after join: [0, 5, 15, 20]
Fresh traversal: [0, 5, 15, 20]
After iterator.remove: [0, 5, 20]
Saved entry value: old
Current map value: new
Entry setValue rejected
```

### 4.1. Những bảo đảm đến từ đâu?

`CountDownLatch` tạo quan hệ thứ tự giữa các bước của hai tác vụ. `Future.get()` bảo đảm main chỉ kiểm tra dữ liệu sau khi tác vụ tương ứng đã hoàn thành và công bố kết quả.

Những công cụ này làm thí nghiệm dễ kiểm chứng; chúng không thay hợp đồng iterator thành snapshot. Ta vẫn không xác nhận một tập thành viên cố định cho iterator cũ.

Danh sách observed chỉ do reader ghi trước khi trả về. Main đọc nó sau Future.get, nên không có hai luồng cùng sửa ArrayList đó.

### 4.2. Vì sao trạng thái cuối có kết quả cố định?

Khi in `Final set after join`, cả reader và writer đều đã xong. Không còn bên ghi. Thao tác writer đã xác định rõ: bỏ 10, thêm 5 và 15.

`Fresh traversal` tạo lượt đọc mới sau thời điểm ấy, vì vậy phải thấy `[0, 5, 15, 20]` trong thí nghiệm. Đây là kiểm tra dữ liệu ổn định sau phối hợp, không phải bằng chứng iterator cũ đã nhìn cùng một ảnh chụp.

## 5. Map còn có hai mức snapshot khác nhau

### 5.1. Entry riêng lẻ là snapshot, iterator tổng thể vẫn nhất quán yếu

ConcurrentSkipListMap trả các `Map.Entry` là ảnh chụp ánh xạ tại lúc chúng được tạo ra. Các entry này không hỗ trợ `setValue`, kể cả entry nhận từ iterator của entrySet.

Trong ví dụ:

```text
Entry nhận được: 1=old
Map được cập nhật thành: 1=new

entry.getValue() -> old
map.get(1)       -> new
```

Việc một entry là snapshot không có nghĩa mọi entry của một lượt duyệt được chụp cùng lúc. Có thể xem đây là những quan sát riêng của các ánh xạ trong quá trình reader tiến.

Do đó không được tổng hợp một lượt duyệt rồi khẳng định “đây là toàn bộ trạng thái map tại đúng thời điểm t” nếu chưa có cơ chế riêng bảo đảm điều đó.

### 5.2. Muốn sửa value thì dùng map API

Không áp dụng mẫu `entry.setValue(...)` của một iterator TreeMap cho ConcurrentSkipListMap. Hãy chọn `put`, `replace`, `merge` hoặc thao tác phù hợp với điều kiện cập nhật.

Nếu muốn chỉ xóa khi khóa vẫn ánh xạ tới giá trị đã thấy, cân nhắc `remove(key, expectedValue)`. Điều kiện này kiểm tra value tại khóa, không tự bảo đảm khóa vẫn là ứng viên nhỏ nhất, lớn nhất hoặc floor theo một mốc.

Snapshot của value vẫn là sao chép nông. Nếu V là một ArrayList đang được nhiều luồng sửa, concurrent map không tự làm mọi thao tác trên ArrayList đó an toàn.

## 6. Duyệt được không có nghĩa sở hữu công việc

Giả sử hai worker cùng duyệt map công việc. Cả hai có thể quan sát cùng một khóa và cùng bắt đầu xử lý nó. Iterator không phân chia phần tử giữa các worker.

Nếu muốn một worker nhận một công việc, cần một thao tác nhận có ý nghĩa rõ ràng, ví dụ:

- Poll một đầu khi mô hình cho phép lấy/xóa theo thứ tự.
- Xóa có điều kiện ánh xạ đã thấy, chỉ xử lý khi lần xóa thành công.
- Chuyển trạng thái công việc theo một giao thức riêng.

Dù nhận được việc không trùng theo cấu trúc trong bộ nhớ, còn phải xét lỗi xử lý, thêm lại công việc hoặc khởi động lại tiến trình nếu nghiệp vụ yêu cầu. Một lượt iterator không cung cấp cơ chế xác nhận hoàn tất.

Cũng không dùng iterator như một nguồn theo dõi thay đổi liên tục. Iterator có thể đi hết trước khi một producer thêm dữ liệu mới; nó không chờ và không tự phát sự kiện cho mọi lần cập nhật sau đó.

## 7. Iterator.remove và thay đổi qua nguồn khác

Iterator của hai lớp hỗ trợ thao tác remove theo hợp đồng của chúng. Trong chương trình, phần xóa 15 chạy sau khi mọi tác vụ đã dừng, giúp thấy riêng vòng đời của remove:

```java
// Đoạn minh họa với ConcurrentSkipListSet<Integer> values.
Iterator<Integer> iterator = values.iterator();
while (iterator.hasNext()) {
    if (iterator.next() == 15) {
        iterator.remove();
    }
}
```

`remove` xóa phần tử vừa được next trả về. Không gọi trước next hoặc hai lần liên tiếp cho cùng một kết quả next.

Khác iterator fail-fast của TreeSet, iterator của skip list đồng thời cho phép các thay đổi đồng thời được lớp hỗ trợ mà không cần dừng vì một bộ đếm thay đổi cấu trúc. Nhưng điều đó không tạo một giao dịch cho các bước:

```text
đọc phần tử -> kiểm tra nghiệp vụ -> xóa -> xử lý bên ngoài
```

Nếu điều kiện xóa phụ thuộc vào value map đã đọc, đừng mặc định một lần iterator.remove đã kiểm tra lại mọi điều kiện ấy. Chọn thao tác có điều kiện trên map khi cần, và xử lý kết quả thành công/thất bại.

Việc iterator không fail-fast cũng không cho phép sửa tùy tiện đối tượng khóa hoặc thay comparator trong khi dữ liệu đang dùng. Thứ tự ổn định vẫn là yêu cầu của cấu trúc.

## 8. Những thao tác nhìn giống snapshot nhưng chưa đủ

### 8.1. Sao chép trong lúc nguồn vẫn đổi

Các biểu thức như:

```java
// Đoạn minh họa: source đang được luồng khác cập nhật.
List<Integer> copy = new ArrayList<>(source);
```

tạo ra một danh sách độc lập **sau khi sao chép xong**, nhưng quá trình đọc source không mặc nhiên là một thao tác nguyên tử tại một thời điểm.

Bản copy có thể dùng ổn định sau đó, nhưng ý nghĩa nghiệp vụ của tập phần tử đã chép vẫn phụ thuộc quá trình quan sát nguồn. “Độc lập sau sao chép” và “chụp nguyên tử tại một thời điểm” là hai thuộc tính khác nhau.

### 8.2. size và lượt duyệt không phải cùng một phép đọc

Không yêu cầu `size()` trước vòng lặp bằng đúng số phần tử vừa duyệt nếu vẫn có writer. Hai quan sát có thể diễn ra trên dữ liệu khác nhau.

Tương tự, `equals`, `toArray`, `putAll`, `clear` hoặc một lượt forEach không được mặc định nguyên tử trên toàn bộ cấu trúc. Một bulk update có thể được reader nhìn thấy từng phần.

### 8.3. synchronized riêng ở reader chưa phối hợp được writer

Một khối:

```java
// Đoạn minh họa về yêu cầu phối hợp, không phải tự động khóa nội bộ map.
synchronized (gate) {
    // Sao chép hoặc duyệt dữ liệu.
}
```

chỉ tạo một vùng phối hợp nếu mọi writer liên quan cũng tuân thủ cùng gate hoặc một giao thức tương đương. ConcurrentSkipListMap không tự kiểm tra khóa gate do ứng dụng đặt.

Nếu writer vẫn tự do cập nhật ngoài gate, reader chỉ đang khóa một đối tượng mà writer không dùng; ảnh chụp chưa được bảo đảm.

## 9. Nếu nghiệp vụ cần một trạng thái toàn cục nhất quán

Chọn theo yêu cầu thay vì ép iterator làm điều không thuộc hợp đồng:

| Nhu cầu | Cách suy nghĩ phù hợp |
| --- | --- |
| Hiển thị trạng thái đang hoạt động | Thường có thể chấp nhận lượt duyệt nhất quán yếu nếu giao diện diễn đạt phù hợp |
| Chờ tác vụ hoàn tất rồi kiểm tra kết quả | Dùng điểm phối hợp và duyệt sau khi không còn writer liên quan |
| Báo cáo phải nhất quán tại một thời điểm | Thiết kế snapshot dưới giao thức đồng bộ/phiên bản phù hợp |
| Dữ liệu chủ yếu đọc, cập nhật theo phiên bản | Có thể công bố một cấu trúc bất biến mới theo từng phiên bản |
| Mỗi công việc phải được nhận bởi một worker | Dùng thao tác nhận/xóa/chuyển trạng thái, không chỉ iterator |
| Theo dõi mọi thay đổi theo thứ tự thời gian | Cần cơ chế sự kiện/nhật ký thay đổi, không phải duyệt tập hiện tại |

Không có một lựa chọn chung cho mọi trường hợp. Tính nhất quán mạnh hơn có chi phí về khóa, sao chép, phiên bản hoặc phối hợp; cần chọn đúng mức mà nghiệp vụ yêu cầu.

Nếu dữ liệu chứa đối tượng mutable, còn phải kiểm soát trạng thái của chính đối tượng ấy. Chụp cấu trúc map không tự chụp nhất quán mọi trường bên trong các value dùng chung.

## 10. Kiểm thử đúng hợp đồng

Một kiểm thử đồng thời tốt cần nói rõ thuộc tính đang kiểm chứng:

1. **Điều khiển mốc thời gian:** dùng latch/barrier để cập nhật diễn ra ở giai đoạn dự định; không dựa vào sleep để đoán lịch chạy.
2. **Chờ và thu lỗi:** Future.get hoặc cơ chế tương đương để biết tác vụ đã xong và nhận ngoại lệ từ luồng nền.
3. **Kiểm tra thứ tự:** kết quả phải đi theo comparator trong phạm vi điều kiện thử đã thiết kế.
4. **Không đóng đinh chi tiết không được bảo đảm:** tránh yêu cầu mọi khóa vừa thêm phải xuất hiện trong iterator cũ.
5. **Tách kiểm tra cuối:** khi writer dừng, đối chiếu dữ liệu cuối với các cập nhật đã thực hiện.
6. **Không suy từ một lần chạy:** “đã luôn thấy khóa mới trên máy này” không thay thế hợp đồng API.

Nếu cần quan sát lịch chạy, có thể ghi observed trong một thí nghiệm riêng và xem nó như dữ liệu của lần chạy đó. Đừng chép một kết quả quan sát thành stdout được hứa cho mọi JDK.

## 11. Lỗi thường gặp và thực hành

| Lỗi | Cách sửa |
| --- | --- |
| Không có ConcurrentModificationException nên kết quả là snapshot | Phân biệt khả năng duyệt và tính nguyên tử toàn bộ |
| Iterator phải thấy mọi thay đổi sau khi tạo | Chỉ dựa vào bảo đảm của nhất quán yếu |
| Iterator phân việc cho nhiều consumer | Dùng thao tác nhận công việc phù hợp |
| Gọi entry.setValue trên ConcurrentSkipListMap | Cập nhật qua map API |
| Copy list rồi gọi đó là snapshot nguyên tử | Kiểm soát giai đoạn đọc nguồn nếu cần |
| Dùng size trước để xác nhận số phần tử sẽ thấy | Quan sát có thể thuộc thời điểm khác |
| Chỉ khóa reader bằng một gate riêng | Mọi bên ghi phải tham gia cùng giao thức |
| Giá trị mutable tự được map bảo vệ | Thiết kế đồng thời riêng cho value |
| Dùng sleep để bảo đảm thứ tự hai luồng | Dùng công cụ phối hợp rõ quan hệ trước/sau |

Bài tập:

1. Chạy chương trình nhiều lần nhưng chỉ khẳng định các thuộc tính mà nó kiểm tra, không yêu cầu danh sách observed cố định.
2. Trong một bản thí nghiệm, in observed và giải thích vì sao một kết quả cụ thể không tạo ra bảo đảm mới cho iterator.
3. Bỏ writer và duyệt một set ổn định. Kết quả phải trùng toàn bộ dữ liệu hiện có theo thứ tự comparator.
4. Tạo entry iterator của ConcurrentSkipListMap, thay value trong map, rồi so entry đã giữ với giá trị đọc mới. Xác minh setValue không được hỗ trợ.
5. Thiết kế một báo cáo phải nhất quán giữa hai khóa. Nêu rõ cách phối hợp cả writer lẫn reader; đừng chỉ thêm synchronized ở phía đọc.
6. Giải thích vì sao hai worker cùng for-each có thể xử lý cùng một công việc, rồi đề xuất một thao tác nhận việc có kết quả kiểm tra được.

Iterator nhất quán yếu giúp reader tiếp tục làm việc khi dữ liệu thay đổi. Muốn dùng kết quả đúng, cần xác định rõ đang cần một lượt quan sát linh hoạt, một ảnh chụp toàn cục hay quyền xử lý một phần tử; ba nhu cầu ấy cần các hợp đồng khác nhau.
