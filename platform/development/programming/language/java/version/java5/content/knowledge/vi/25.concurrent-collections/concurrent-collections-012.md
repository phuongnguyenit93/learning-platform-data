# Chọn collection theo tỷ lệ đọc ghi và yêu cầu thứ tự

## 1. Bắt đầu từ dữ liệu và hành vi cần bảo đảm

Một bảng tra cứu người dùng, một danh sách bộ xử lý sự kiện và một tập mã công việc không có cùng nhu cầu. Bảng tra cứu cần lấy giá trị theo khóa; danh sách có thể cần thứ tự đăng ký; tập mã cần duy nhất. Khi nhiều luồng cùng truy cập, ta còn phải xác định cách các thao tác đọc/ghi và các lượt duyệt phối hợp với nhau.

Tỷ lệ đọc/ghi ảnh hưởng chi phí, nhưng không thay thế yêu cầu đúng đắn. Một collection rất nhanh mà không giữ được thứ tự nghiệp vụ cần thiết vẫn là lựa chọn sai. Ngược lại, trả chi phí duy trì thứ tự hoặc ảnh chụp khi ứng dụng không cần có thể làm hệ thống phức tạp và tốn tài nguyên hơn.

Cách lựa chọn trong bài áp dụng cho Java hiện đại. Ví dụ dùng Java 17 trở lên; việc đề cập các lựa chọn hiện hành không có nghĩa mọi API đều đã được giới thiệu trong cùng một phiên bản Java.

## 2. Làm rõ “đọc nhiều, ghi ít”

Không chỉ đếm tổng số lời gọi. Cần biết chính xác mỗi bên đang làm gì:

| Loại thao tác | Câu hỏi cần đo hoặc làm rõ |
| --- | --- |
| Đọc một phần tử | Lấy theo khóa, kiểm tra tồn tại hay lấy theo chỉ số? |
| Duyệt toàn bộ | Một lượt đọc vài phần tử hay hàng triệu phần tử? Cần phiên bản ổn định không? |
| Ghi | Thêm, xóa, thay giá trị, hay tính giá trị mới từ giá trị cũ? |
| Phân bố truy cập | Các luồng chạm nhiều khóa độc lập hay cùng tranh một khóa nóng? |
| Đợt tăng tải | Ghi phân tán đều hay dồn thành đợt khiến nhiều bản sao được tạo? |

Ví dụ 99% đọc vẫn chưa đủ để kết luận copy-on-write là phù hợp: 1% còn lại có thể là hàng nghìn lần sửa một tập rất lớn mỗi giây. Ngược lại, một danh sách 20 bộ xử lý được duyệt hàng chục nghìn lần nhưng chỉ đổi vài lần khi cấu hình cập nhật có thể là trường hợp rất hợp.

Những thay đổi trường bên trong một đối tượng cũng là ghi ở mức ứng dụng, dù không gọi `collection.put` hay `list.add`. Tính an toàn của collection không tự bảo vệ các trường mutable ấy.

## 3. Làm rõ “thứ tự”

| Yêu cầu | Ý nghĩa | Không đồng nghĩa với |
| --- | --- | --- |
| Thứ tự chèn | Duyệt theo thứ tự thêm phần tử/khóa | Sắp xếp theo giá trị khóa |
| Thứ tự sắp xếp | Duyệt theo thứ tự tự nhiên hoặc comparator | Thứ tự hoàn tất xử lý |
| FIFO của hàng đợi | Lấy phần tử được xếp trước | Mọi consumer xử lý xong theo cùng thứ tự |
| Theo ảnh chụp | Một lượt duyệt giữ phiên bản cấu trúc lúc bắt đầu | Phần tử bên trong được sao chép sâu và đóng băng |
| Không yêu cầu thứ tự | Mọi thứ tự được hợp đồng cho phép đều chấp nhận được | Dựa vào thứ tự tình cờ của một lần chạy |

`ConcurrentHashMap` không giữ thứ tự chèn và không sắp xếp khóa. `ConcurrentSkipListMap` sắp xếp theo khóa. `LinkedHashMap` mặc định giữ thứ tự chèn, nhưng muốn chia sẻ có ghi giữa nhiều luồng phải thêm giao thức đồng bộ phù hợp.

Nếu chỉ cần một báo cáo hiển thị theo thứ tự vào cuối một đợt xử lý, có thể thu kết quả rồi sắp xếp khi đã phối hợp xong. Không nhất thiết duy trì thứ tự trong mọi cập nhật. Tuy nhiên, nếu nguồn vẫn bị sửa trong lúc thu, việc sắp xếp bản thu không tự tạo ảnh chụp nguyên tử của nguồn.

## 4. Bảng lựa chọn chính

| Nhu cầu | Lựa chọn nên cân nhắc | Điểm đánh đổi |
| --- | --- | --- |
| Map chia sẻ, tra cứu/cập nhật theo khóa, không cần thứ tự | `ConcurrentHashMap` | Duyệt nhất quán yếu; không có giao dịch toàn map |
| Map đồng thời, cần khóa đã sắp xếp hoặc truy vấn khoảng | `ConcurrentSkipListMap` | Phải duy trì cấu trúc có thứ tự, chi phí khác bảng băm |
| Set chia sẻ, nhiều thay đổi, không cần thứ tự | `ConcurrentHashMap.newKeySet()` | Không có thứ tự chèn; iterator nhất quán yếu |
| List nhỏ, duyệt nhiều hơn thay đổi rất nhiều | `CopyOnWriteArrayList` | Cập nhật thường sao chép mảng; cho phép phần tử trùng |
| Set nhỏ, ít thay đổi, cần lượt duyệt theo ảnh chụp | `CopyOnWriteArraySet` | Tìm kiếm tuyến tính và cập nhật thường sao chép |
| Cần thứ tự chèn hoặc thao tác kết hợp dưới một khóa chung | Wrapper `Collections.synchronized...` hoặc khóa do ứng dụng quản lý | Bên đọc/ghi phải tuân theo cùng giao thức; dễ tranh chấp nếu giữ khóa lâu |
| Dữ liệu chỉ dùng trong một luồng hoặc không thay đổi sau công bố an toàn | Collection thông thường hoặc phiên bản bất biến | Cần giữ đúng ranh giới sở hữu/công bố |

Hướng phân biệt concurrent collection, synchronized collection và copy-on-write được trình bày trong [java.util.concurrent — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/package-summary.html).

## 5. Map theo khóa: không thứ tự và có thứ tự

### ConcurrentHashMap khi thứ tự không quan trọng

`ConcurrentHashMap` phù hợp với bảng tra cứu dùng chung, nơi các khóa được đọc/cập nhật độc lập và không cần giữ thứ tự duyệt. Dùng `putIfAbsent`, `replace` hoặc `remove` có điều kiện khi quy tắc cần một lần kiểm tra–thay đổi nguyên tử trên một khóa.

Đừng biến `get` rồi `put` thành phép cập nhật nguyên tử bằng niềm tin rằng map đã thread-safe. Cũng không chọn khóa/chức năng gây tranh chấp tập trung rồi kết luận chỉ đổi tên collection sẽ loại bỏ mọi điểm nghẽn.

Iterator nhất quán yếu cho phép tiếp tục khi map đổi nhưng không bảo đảm mọi mục thuộc cùng một thời điểm. Các quan sát như `size()` trong lúc cập nhật nên được hiểu theo hợp đồng của lớp, không dùng làm điều kiện chắc chắn cho một chuỗi nghiệp vụ nhiều bước.

### ConcurrentSkipListMap khi phải duy trì khóa đã sắp xếp

Nếu thường xuyên cần khóa nhỏ nhất, khóa ngay trước/sau một mốc, hoặc một khoảng khóa, map có thứ tự có thể diễn đạt yêu cầu tốt hơn. `ConcurrentSkipListMap` duy trì thứ tự tự nhiên hoặc comparator và cung cấp các thao tác điều hướng như `floorKey`, `ceilingKey`, `subMap`.

Nó không biến toàn bộ lượt duyệt hoặc cập nhật nhiều mục thành một giao dịch nguyên tử. Iterator vẫn nhất quán yếu. Comparator cần nhất quán với cách ứng dụng xác định khóa; nếu comparator xem hai khóa bằng nhau, map sắp xếp coi chúng là cùng vị trí khóa theo quy tắc của nó. Xem [ConcurrentSkipListMap — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html).

## 6. Copy-on-write khi lượt đọc cần phiên bản cấu trúc ổn định

`CopyOnWriteArrayList` và `CopyOnWriteArraySet` giữ việc duyệt trên một phiên bản mảng. Một đăng ký được thêm trong lúc vòng gọi đang chạy không tự chen vào ảnh chụp của vòng đó; một đăng ký bị xóa vẫn có thể còn trong vòng đã bắt đầu.

Đây thường là quy tắc thuận tiện cho danh sách bộ xử lý ít đổi. Chọn list khi cần phần tử trùng/vị trí; chọn set khi mỗi thành viên bằng nhau chỉ được có một lần. Với set, tìm một phần tử có thể phải so sánh nhiều phần tử, không phải tra theo bảng băm.

Đổi lại, cập nhật thay đổi cấu trúc thường cần sao chép lượng tham chiếu tỷ lệ với kích thước tập/list, tạo cấp phát và áp lực thu gom bộ nhớ. Các iterator sống lâu có thể giữ các phiên bản mảng cũ. Vì vậy, phải xét cả kích thước và tần suất ghi.

Ảnh chụp chỉ giữ tham chiếu phần tử. Đối tượng mutable bên trong vẫn cần quy tắc truy cập riêng. Hợp đồng iterator và chi phí copy-on-write được mô tả trong [CopyOnWriteArrayList — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html).

## 7. Thứ tự chèn và khóa chung

Nếu phải giữ thứ tự chèn, một hướng đơn giản là bảo vệ `LinkedHashMap` bằng wrapper đồng bộ, rồi tuân thủ hợp đồng khi duyệt:

```java
// Đoạn minh họa; imports tương ứng xuất hiện trong chương trình đầy đủ bên dưới.
Map<String, Integer> ordered =
        Collections.synchronizedMap(new LinkedHashMap<>());

List<String> keys;
synchronized (ordered) {
    keys = new ArrayList<>(ordered.keySet());
}
```

Khóa đúng wrapper map khi duyệt các view của nó, không tự chọn khóa `keySet()` rồi cho rằng đã phối hợp đúng với các cập nhật map. Không làm lộ map gốc để bên ngoài sửa mà bỏ qua wrapper. Những yêu cầu này có trong [Collections.synchronizedMap — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map)).

Một khóa chung cũng có thể giúp bảo vệ thao tác kết hợp hoặc chụp nhiều mục nhất quán, miễn là mọi đường thay đổi đều giữ đúng khóa. Chi phí là các luồng có thể phải chờ nhau; giữ khóa trong lúc gọi mạng, đọc tệp hoặc gọi callback không kiểm soát có thể làm độ trễ tăng mạnh.

Chỉ `synchronized (concurrentMap)` quanh một khối đọc không tự chặn các writer đang gọi `put` thông thường trên `ConcurrentHashMap`, vì các writer ấy không tự tuân theo monitor do ứng dụng chọn.

## 8. Ví dụ chạy đầy đủ: thứ tự và phiên bản duyệt

Lưu thành `CollectionChoiceDemo.java`. Đây là ví dụ kiểm tra hợp đồng quan sát, không phải benchmark hiệu năng.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.CopyOnWriteArrayList;

public class CollectionChoiceDemo {
    private static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected collection result");
        }
    }

    public static void main(String[] args) {
        ConcurrentHashMap<String, Integer> lookup = new ConcurrentHashMap<>();
        lookup.put("B", 2);
        lookup.put("A", 1);
        check(lookup.get("A") == 1);
        System.out.println("lookup A: " + lookup.get("A"));

        ConcurrentSkipListMap<String, Integer> sorted =
                new ConcurrentSkipListMap<>();
        sorted.put("B", 2);
        sorted.put("A", 1);
        check(sorted.firstKey().equals("A"));
        System.out.println("sorted keys: " + sorted.keySet());

        Map<String, Integer> insertionOrdered =
                Collections.synchronizedMap(new LinkedHashMap<>());
        insertionOrdered.put("B", 2);
        insertionOrdered.put("A", 1);
        List<String> insertionKeys;
        synchronized (insertionOrdered) {
            insertionKeys = new ArrayList<>(insertionOrdered.keySet());
        }
        check(insertionKeys.equals(List.of("B", "A")));
        System.out.println("insertion keys: " + insertionKeys);

        CopyOnWriteArrayList<String> listeners =
                new CopyOnWriteArrayList<>(List.of("first", "second"));
        Iterator<String> round = listeners.iterator();
        listeners.add("third");

        List<String> roundMembers = new ArrayList<>();
        round.forEachRemaining(roundMembers::add);
        check(roundMembers.equals(List.of("first", "second")));
        System.out.println("snapshot round: " + roundMembers);
        System.out.println("current listeners: " + listeners);

        Set<String> uniqueIds = ConcurrentHashMap.newKeySet();
        check(uniqueIds.add("X"));
        check(!uniqueIds.add("X"));
        check(uniqueIds.add("Y"));
        System.out.println("unique id count: " + uniqueIds.size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 CollectionChoiceDemo.java
java CollectionChoiceDemo
```

Stdout:

```text
lookup A: 1
sorted keys: [A, B]
insertion keys: [B, A]
snapshot round: [first, second]
current listeners: [first, second, third]
unique id count: 2
```

Chương trình đưa B vào trước A. Map sắp xếp vẫn duyệt `[A, B]`, còn map giữ thứ tự chèn duyệt `[B, A]`. Nó không in thứ tự của `ConcurrentHashMap` thành một yêu cầu, vì lớp không bảo đảm thứ tự đó.

Iterator của list được tạo trước khi thêm `third`, nên vòng ảnh chụp chỉ thấy hai thành viên cũ. Tập mã dùng `newKeySet()` có hai mã duy nhất dù thử thêm X hai lần. Ví dụ dùng một luồng để kết quả xác định và để tách hợp đồng dữ liệu khỏi đo đạc tranh chấp; nó không chứng minh một lớp nhanh hơn lớp khác.

## 9. Những lựa chọn nằm ngoài câu hỏi tỷ lệ đọc/ghi

### Có thật sự cần dữ liệu mutable dùng chung không?

Nếu mỗi yêu cầu chỉ dùng collection riêng, `ArrayList` hoặc `HashMap` thông thường thường đơn giản hơn. Nếu cấu hình thay rất ít nhưng mỗi lần phải đổi nhiều mục liên quan, có thể xây một phiên bản bất biến mới rồi công bố toàn bộ qua `volatile` hoặc `AtomicReference`, để một lượt đọc dùng một phiên bản.

Bản không cho sửa qua API chưa chắc là bản sao sâu; một wrapper không cho sửa cũng có thể chỉ là view của nguồn. Việc công bố và trạng thái mutable bên trong vẫn cần được thiết kế đúng.

### Nếu cần chuyển giao công việc, có thể cần Queue

List hoặc set dùng chung không tự là giao thức nhận việc. Nếu yêu cầu là nhiều producer đưa việc và consumer lấy mỗi việc ra, nên xét `Queue`/`BlockingQueue` theo thứ tự lấy, dung lượng và cách chờ. Tập đồng thời có thể giữ mã không trùng nhưng không tự cung cấp `take`, thời hạn chờ hay giới hạn backlog.

### Tính nguyên tử và null phải được kiểm tra riêng

Không collection nào trong bảng tự tạo giao dịch nhiều khóa hoặc làm mọi callback chỉ chạy đúng một lần. Các lớp cũng khác nhau về `null`: `ConcurrentHashMap` và `ConcurrentSkipListMap` cấm khóa/giá trị `null`, còn các lớp copy-on-write nêu trong bài có thể chứa phần tử `null`. Đổi loại phải xét lại hợp đồng đang dựa vào, không chỉ sửa constructor.

## 10. Đánh giá bằng tải thực tế

Sau khi lọc những lớp đáp ứng đúng ngữ nghĩa, hãy đo với kích thước dữ liệu, số luồng và phân bố truy cập gần hệ thống thật. Theo dõi thông lượng, độ trễ các nhóm đọc/ghi, các trường hợp độ trễ cao, lượng cấp phát, áp lực GC và mức tranh chấp.

Đừng chỉ đo một khóa không tranh chấp nếu ứng dụng có một khóa nóng; đừng chỉ đo đọc nếu lúc cập nhật cấu hình có một đợt ghi lớn. Với yêu cầu thứ tự, cần giữ cùng ngữ nghĩa giữa các ứng viên khi so sánh. Một phép đo nhanh bằng vài lần `System.nanoTime()` mà không kiểm soát khởi động JVM và tối ưu hóa có thể dẫn tới kết luận sai.

Quy trình ra quyết định thực dụng là: xác định hình dạng dữ liệu → chốt yêu cầu thứ tự/ảnh chụp/nguyên tử → xác định mức chia sẻ và tỷ lệ thao tác thực → chọn ứng viên → đo và kiểm tra hành vi ở tải biên. Khi yêu cầu nghiệp vụ thay đổi, đánh giá lại lựa chọn thay vì giữ collection chỉ vì nó từng chạy nhanh.

## 11. Tự kiểm tra

1. Ứng dụng đọc 99% có tự động phù hợp với copy-on-write không? Không; còn phụ thuộc kích thước và số lần ghi tuyệt đối.
2. Cần giữ thứ tự chèn có thể thay ngay `LinkedHashMap` bằng `ConcurrentHashMap` không? Không, nếu thứ tự ấy là yêu cầu thật.
3. Cần tìm khóa ngay trước một mốc nên cân nhắc gì? Một map có thứ tự/điều hướng như `ConcurrentSkipListMap`.
4. Iterator copy-on-write có nhận thành viên mới được thêm sau khi nó tạo không? Không.
5. Collection thread-safe có làm `get` rồi `put` thành một phép cập nhật nguyên tử không? Không.
6. Chỉ cần collection riêng của một luồng có nhất thiết dùng collection đồng thời không? Không; cần giữ đúng quyền sở hữu và cách công bố dữ liệu.
