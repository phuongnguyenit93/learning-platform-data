# TreeMap: firstKey, lastKey, firstEntry và lastEntry

Khi dữ liệu đã được tổ chức theo khóa, ứng dụng thường cần xem hai đầu của thứ tự: mốc thời gian sớm nhất và muộn nhất, mã nhỏ nhất và lớn nhất, hoặc bản ghi đứng đầu và cuối theo comparator.

`TreeMap` có bốn phương thức phục vụ việc quan sát đó. `firstKey` và `lastKey` trả riêng khóa; `firstEntry` và `lastEntry` trả một cặp khóa–giá trị. Điểm dễ nhầm nằm ở map rỗng, ý nghĩa của “đầu/cuối” khi thứ tự đảo và quan hệ giữa entry kết quả với dữ liệu gốc.

Bài dùng Java 17. Mục tiêu là chọn đúng phương thức cho mục đích đọc, xử lý kết quả vắng rõ ràng và hiểu giới hạn của ảnh chụp ánh xạ.

## 1. Bốn phương thức trả gì?

| Phương thức | Kết quả trên map không rỗng | Khi map rỗng | Xóa ánh xạ không? |
|---|---|---|---|
| firstKey() | Khóa đầu theo thứ tự của map | Ném NoSuchElementException | Không |
| lastKey() | Khóa cuối theo thứ tự của map | Ném NoSuchElementException | Không |
| firstEntry() | Cặp khóa–giá trị ở đầu | Trả null | Không |
| lastEntry() | Cặp khóa–giá trị ở cuối | Trả null | Không |

`firstKey` và `lastKey` thuộc hợp đồng SortedMap; các phương thức trả entry ở hai đầu được NavigableMap bổ sung. TreeMap triển khai NavigableMap nên cung cấp cả bốn phương thức. [Java 17: SortedMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SortedMap.html), [Java 17: NavigableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableMap.html)

Không phương thức nào trong bốn tên trên có ý nghĩa “lấy ra khỏi map”. Nếu mục đích là lấy và xóa, đó là nhóm `pollFirstEntry` hoặc `pollLastEntry`. Đừng dùng poll chỉ để xem dữ liệu rồi vô tình loại ánh xạ.

### 1.1. Tình huống đơn giản

Giả sử TreeMap dùng thứ tự tự nhiên của Integer và chứa:

~~~text
10 -> ten
20 -> twenty
30 -> thirty
~~~

Khi ấy:

~~~text
firstKey()   -> 10
lastKey()    -> 30
firstEntry() -> cặp 10=ten
lastEntry()  -> cặp 30=thirty
~~~

Các dòng `10=ten` và `30=thirty` là cách biểu diễn cặp trong ví dụ, không phải chuỗi khóa cần phân tích bằng cách tách dấu bằng. Trong mã, hãy lấy khóa bằng `entry.getKey()` và giá trị bằng `entry.getValue()`.

### 1.2. Khi chỉ có một ánh xạ

Khóa đầu và khóa cuối là cùng khóa. Hai entry biểu diễn cùng cặp dữ liệu.

Không cần suy ra hai lần gọi trả về cùng một đối tượng entry trong bộ nhớ. Điều ứng dụng quan tâm là khóa và giá trị theo hợp đồng, không phải danh tính đối tượng được tạo để mang kết quả.

Nếu cần so nội dung cặp, dùng phép so sánh nội dung phù hợp; không dùng `==` để yêu cầu hai kết quả entry phải cùng đối tượng.

## 2. “Đầu” và “cuối” theo thứ tự của map

### 2.1. Không phải lần chèn đầu và lần chèn cuối

TreeMap sắp xếp theo thứ tự tự nhiên của khóa hoặc comparator đã chọn. Chèn lần lượt `30, 10, 20` không làm firstKey trở thành 30. Với thứ tự số tăng, đầu là 10 và cuối là 30.

Thứ tự chèn là một yêu cầu khác. Nếu nghiệp vụ hỏi “bản ghi nào được thêm đầu tiên?”, không nên dùng TreeMap rồi diễn giải firstEntry như lịch sử chèn.

Tương tự, firstEntry không tìm giá trị nhỏ nhất. Nó trả ánh xạ có khóa đầu theo thứ tự. Nếu giá trị là độ ưu tiên, giá tiền hoặc thời gian nằm bên trong đối tượng, comparator trên khóa không tự chuyển sang xét các giá trị ấy.

### 2.2. Comparator đảo làm đảo hai đầu

Với comparator giảm dần và các khóa 10, 20, 30:

~~~text
thứ tự map: 30 -> 20 -> 10
firstKey: 30
lastKey:  10
~~~

Cụm “khóa thấp nhất” trong hợp đồng thứ tự phải được đọc theo comparator của map. Nó không luôn có nghĩa số nhỏ nhất theo phép so số tăng dần quen thuộc.

Đây là lý do nên đặt tên kết quả theo nghiệp vụ, chẳng hạn `earliestByTime` chỉ khi comparator thực sự đi theo thời gian từ sớm đến muộn. Nếu comparator ưu tiên điểm cao trước, firstEntry là đầu quy tắc xếp hạng ấy.

### 2.3. Comparator nhiều tiêu chí

Giả sử khóa có điểm và mã định danh. Nếu comparator xét điểm giảm dần rồi mã tăng dần, phần tử đầu là điểm cao nhất; khi bằng điểm, mã nhỏ hơn đứng trước.

Muốn hiểu firstEntry trong tình huống này, phải đọc toàn bộ comparator. Đừng chỉ nhìn kiểu khóa hoặc tên phương thức.

Comparator cũng phải phân biệt các khóa theo ý định của dữ liệu. Nếu hai khóa so sánh bằng 0, TreeMap coi chúng thuộc cùng vị trí khóa; không có hai ánh xạ riêng để first và last lựa chọn giữa chúng. Giữ các thành phần dùng so sánh ổn định là điều kiện để thứ tự cây tiếp tục phản ánh đúng dữ liệu. [Java 17: TreeMap và quy tắc thứ tự khóa](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html)

## 3. Chọn trả khóa hay trả cả entry?

### 3.1. Chỉ cần khóa

Nếu đang có SortedMap không rỗng và chỉ cần mốc đầu hoặc mốc cuối, firstKey/lastKey diễn đạt trực tiếp mục đích.

Đoạn minh họa một phần:

~~~java
SortedMap<Integer, String> labels = new TreeMap<>();
labels.put(20, "middle");
labels.put(10, "start");

Integer earliestKey = labels.firstKey();
~~~

Ví dụ biết chắc labels có dữ liệu do chính các dòng trước đó vừa tạo trong cùng luồng. Đây khác với giả định một map dùng chung “chắc vẫn còn dữ liệu” sau một phép kiểm tra tách rời.

Không cần sao chép toàn bộ keySet vào List chỉ để lấy vị trí 0 hoặc vị trí cuối. Các phương thức đã mô tả đúng thao tác trên sorted map.

### 3.2. Cần cả khóa và giá trị

Dùng firstEntry/lastEntry để nhận cặp:

~~~java
NavigableMap<Integer, String> orderedLabels = new TreeMap<>();
orderedLabels.put(10, "start");
Map.Entry<Integer, String> first = orderedLabels.firstEntry();
if (first != null) {
    System.out.println(first.getKey() + ": " + first.getValue());
}
~~~

Đoạn minh họa khai báo `orderedLabels` bằng NavigableMap để có phương thức firstEntry. Nếu biến chỉ được khai báo SortedMap trong Java 17 thì không gọi trực tiếp firstEntry qua kiểu đó.

Khai báo kiểu biến là phần của thiết kế. Hàm cần phương thức entry ở hai đầu nên nhận NavigableMap phù hợp, thay vì nhận Map rồi ép kiểu mù.

### 3.3. Tránh tách lấy khóa rồi tra giá trị nếu cần một cặp kết quả

Mẫu sau có hai thao tác riêng:

~~~java
Integer key = map.firstKey();
String value = map.get(key);
~~~

Trong một map ổn định trên một luồng, nó có thể cho kết quả mong muốn. Nhưng nếu cần cả khóa lẫn giá trị, firstEntry thể hiện mục đích rõ hơn và không cần lượt tra cứu riêng bằng khóa.

Nếu có sửa đổi khác xen giữa hai lời gọi, key và value có thể không còn phản ánh cùng trạng thái dữ liệu. Một dòng thời gian khái niệm:

~~~text
T1: lấy firstKey, nhận 10
T2: một thao tác khác xóa khóa 10
T3: get(10), không còn ánh xạ tương ứng
~~~

Dùng một phương thức trả cặp loại bỏ nhu cầu tự ghép cặp bằng hai lần đọc đó. Nó không tự biến TreeMap thành cấu trúc an toàn cho nhiều luồng; phần truy cập đồng thời vẫn cần chính sách riêng.

## 4. Map rỗng: ngoại lệ và null là hai hợp đồng khác nhau

### 4.1. FirstKey và lastKey không dùng null làm dấu báo rỗng

Trên map rỗng, hai phương thức trả khóa ném `NoSuchElementException`. Không viết kiểm tra theo mẫu:

~~~java
Integer first = map.firstKey();
if (first == null) {
    // Không phải cách kiểm tra map rỗng bằng firstKey.
}
~~~

Đây là đoạn minh họa một giả định sai. Nếu map rỗng, chương trình không đi tới phép so sánh vì ngoại lệ đã được ném.

Nếu một nghiệp vụ yêu cầu map không được rỗng, ngoại lệ có thể giúp lộ việc điều kiện đó bị vi phạm. Nếu trạng thái rỗng là bình thường, cần thiết kế nhánh xử lý rỗng thay vì coi đó là lỗi bất ngờ.

### 4.2. FirstEntry và lastEntry cho phép rỗng là một kết quả bình thường

Mẫu đọc một đầu và xử lý vắng:

~~~java
Map.Entry<Integer, String> first = map.firstEntry();
if (first == null) {
    System.out.println("No mappings");
} else {
    System.out.println(first.getKey() + "=" + first.getValue());
}
~~~

Không gọi getKey hoặc getValue trước khi đã xử lý khả năng entry bằng null.

Nếu tầng ứng dụng dùng Optional để biểu diễn kết quả vắng, có thể bọc chính entry. Không tự bọc riêng giá trị rồi đánh đồng “giá trị null” với “không có ánh xạ”.

### 4.3. IsEmpty rồi firstKey không phải một thao tác nguyên tử

Trên một luồng, với dữ liệu không bị sửa xen giữa, kiểm tra isEmpty rồi firstKey có thể dùng được. Nhưng hai lời gọi vẫn là hai bước.

Nếu map được chia sẻ và luồng khác có quyền xóa, nó có thể trở thành rỗng sau lần kiểm tra. Không dùng isEmpty như biện pháp thay thế đồng bộ hóa.

Tương tự, gọi firstEntry rồi lastEntry không tự tạo một ảnh chụp nhất quán của cả hai đầu. Nếu cần cả hai ở cùng một trạng thái được bảo vệ, phải tổ chức các lần đọc trong cùng chính sách bảo vệ dữ liệu.

## 5. Entry kết quả của TreeMap là ảnh chụp cặp ánh xạ

### 5.1. Không bám theo thay đổi giá trị về sau

Với TreeMap:

~~~text
lúc đầu:          10 -> ten
captured = firstEntry()

cập nhật map:    10 -> TEN
captured vẫn:    10 -> ten
firstEntry mới:  10 -> TEN
~~~

Entry do firstEntry/lastEntry của TreeMap trả về biểu diễn ánh xạ tại thời điểm kết quả được tạo. Thay một giá trị trong map không biến entry cũ thành cặp mang giá trị mới.

Nếu khóa bị xóa khỏi map, cặp đã chụp vẫn là dữ liệu kết quả cũ; nó không tự biến thành null. Nếu thêm khóa đứng trước, entry đã chụp cũng không tự trở thành đầu mới.

Do đó, đặt tên biến `capturedFirst` hoặc `firstAtReadTime` có thể diễn đạt ý nghĩa tốt hơn tên khiến người đọc tưởng đó là liên kết sống tới đầu hiện tại.

### 5.2. Không dùng setValue để ghi ngược

Các entry điều hướng này của TreeMap không hỗ trợ `setValue`. Gọi nó ném `UnsupportedOperationException`.

Nếu muốn sửa ánh xạ hiện tại, dùng thao tác map phù hợp, chẳng hạn put với khóa đã chọn, đồng thời xem xét việc trạng thái có thể đã thay đổi trước lúc sửa.

Không khái quát thành “mọi Map.Entry đều bất biến”. Entry thu được từ iterator của entrySet có hợp đồng riêng. Chủ đề ở đây là entry được trả trực tiếp bởi firstEntry/lastEntry của TreeMap.

### 5.3. Ảnh chụp cặp không phải sao chép sâu

Giả sử giá trị là một ArrayList:

~~~text
map:   1 -> đối tượng List L
entry: 1 -> cùng đối tượng List L
~~~

Nếu sửa nội dung của L, cả hai tham chiếu đều nhìn thấy nội dung đã sửa. Entry không cho gán lại trường value bằng setValue, nhưng điều đó không làm đối tượng List trở thành bất biến.

Nếu thay ánh xạ trong map để trỏ tới một List mới, entry cũ vẫn trỏ List cũ. Cần tách hai hành động:

- Thay giá trị được tham chiếu bởi ánh xạ.
- Thay nội dung bên trong chính đối tượng giá trị.

Khái niệm cặp không sửa được của `SimpleImmutableEntry` cũng phân biệt việc không hỗ trợ thay value với việc các đối tượng được tham chiếu có tự bất biến hay không. Không cần dựa vào tên lớp thực tế của entry TreeMap để sử dụng hợp đồng này. [Java 17: AbstractMap.SimpleImmutableEntry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractMap.SimpleImmutableEntry.html)

Nếu cần dữ liệu báo cáo tách hoàn toàn khỏi thay đổi sau đó, phải chọn cách sao chép hoặc kiểu dữ liệu bất biến phù hợp với đối tượng giá trị, không chỉ giữ entry.

## 6. Null ở ba vị trí mang ba ý nghĩa

| Vị trí có null | Ý nghĩa cần xét |
|---|---|
| Biến entry bằng null | Với firstEntry/lastEntry của TreeMap, không có ánh xạ vì map hoặc view đang rỗng |
| entry.getValue() bằng null | Có thể là một ánh xạ đang tồn tại với giá trị null |
| Khóa kết quả bằng null | Có thể là khóa null hợp lệ nếu comparator cho phép |

### 6.1. Giá trị null không làm entry biến mất

Một TreeMap chứa `1 -> null` vẫn có firstEntry khác null. Đọc entry.getValue nhận null không chứng minh map rỗng.

Mẫu kiểm tra đúng là xét đối tượng entry trước, rồi xử lý giá trị theo chính sách dữ liệu.

### 6.2. Khóa null có thể hợp lệ với comparator riêng

TreeMap dùng thứ tự tự nhiên không cho phép khóa null. Một comparator chủ động xử lý null, như `Comparator.nullsFirst(...)`, có thể cho phép nó.

Khi map ấy chứa khóa null, firstKey có thể trả null trong khi map không rỗng. Điều này không mâu thuẫn với hợp đồng rỗng: map rỗng vẫn ném ngoại lệ; kết quả null trong trường hợp này chính là một khóa hợp lệ.

Vì vậy, không dùng `firstKey() == null` như phép kiểm tra map rỗng. Nếu tự động mở hộp một khóa Integer có thể null sang int, cũng phải tính đến việc mở hộp null gây lỗi; đó khác với lỗi không có phần tử.

### 6.3. Không phân tích chuỗi in để đoán trạng thái

Dòng `null=unknown` có thể là cách in một entry có khóa null, không phải một entry vắng. Dùng entry và các phương thức truy cập của nó để xác định trạng thái, không dùng tiền tố chuỗi log.

Chương trình đầy đủ kiểm tra cả null ở giá trị và null ở khóa để hai trường hợp này không bị gộp với entry bằng null.

## 7. Hai đầu của view có phạm vi riêng

### 7.1. View khoảng chỉ xét khóa trong vùng

Nếu map gốc có `10, 20, 30` và view là `[15, 30)`, view chỉ chứa 20. FirstKey và lastKey của view đều là 20, dù hai đầu của gốc là 10 và 30.

“Đầu” và “cuối” luôn xét trên đối tượng map hoặc view mà lời gọi được thực hiện. Không lấy hai đầu của gốc rồi tự cho đó cũng là hai đầu của mọi subMap.

### 7.2. View rỗng dù gốc không rỗng

View `[11, 19]` trên dữ liệu trên không có ánh xạ nào. FirstEntry/lastEntry của view trả null, còn firstKey/lastKey của view ném NoSuchElementException.

Điều này quan trọng khi xử lý một khoảng thời gian không có sự kiện: map tổng thể có thể rất lớn, nhưng khoảng đang hỏi vẫn rỗng. Kiểm tra size của gốc không thay thế xử lý kết quả rỗng của view.

View là góc nhìn dùng chung dữ liệu. Khi dữ liệu gốc trong phạm vi thay đổi, các lần đọc hai đầu về sau phản ánh phạm vi hiện tại. Entry đã chụp từ lần đọc trước vẫn là kết quả cũ.

### 7.3. View đảo đổi chỗ hai đầu

Trên descendingMap của cùng dữ liệu tăng dần:

~~~text
gốc:       10, 20, 30
view đảo:  30, 20, 10

firstEntry của view đảo: 30=thirty
lastEntry của view đảo:  10=ten
~~~

Đó là hai đầu theo comparator đảo của view. Không có yêu cầu phải sao chép rồi sắp lại để quan sát chiều ngược.

## 8. Dùng hai đầu trong một quyết định nghiệp vụ

### 8.1. Chọn phương thức từ kết quả cần dùng

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Chỉ cần khóa đầu, dữ liệu bắt buộc không rỗng | firstKey |
| Chỉ cần khóa cuối, dữ liệu bắt buộc không rỗng | lastKey |
| Cần cặp đầu, rỗng là kết quả bình thường | firstEntry và xử lý null |
| Cần cặp cuối, rỗng là kết quả bình thường | lastEntry và xử lý null |
| Cần lấy đồng thời xóa | Cân nhắc phương thức poll tương ứng |
| Cần phần tử gần một mốc | Đó là nhóm floor/ceiling/lower/higher, không phải hai đầu toàn map |

Không dùng lastEntry để hỏi “bản ghi mới nhất” nếu khóa và comparator không thực sự diễn đạt độ mới. Ví dụ, map sắp theo mã sản phẩm không biến mã lớn nhất thành sản phẩm được cập nhật gần nhất.

### 8.2. Kiểm soát ranh giới giữa đọc và hành động

Một entry có thể đủ để in báo cáo ở trạng thái đã đọc. Nhưng nếu hành động tiếp theo là sửa hoặc xóa chính ánh xạ ấy, cần đánh giá trạng thái tại thời điểm hành động.

Trong hệ thống nhiều luồng, đọc firstEntry rồi sửa theo khóa không tự trở thành thao tác nguyên tử. Entry ảnh chụp mang dữ liệu đã đọc, không cấp quyền giữ độc quyền ánh xạ.

TreeMap không tự đồng bộ hóa. Khi dùng một wrapper đồng bộ, mọi truy cập phải tuân thủ cùng cơ chế. Nếu cần đọc cả hai đầu dưới một trạng thái được bảo vệ, có thể giữ khóa trong suốt hai lần đọc.

Đoạn minh họa một phần, với các import phù hợp:

~~~java
NavigableMap<Integer, String> shared =
        Collections.synchronizedNavigableMap(new TreeMap<>());

Map.Entry<Integer, String> first;
Map.Entry<Integer, String> last;
synchronized (shared) {
    first = shared.firstEntry();
    last = shared.lastEntry();
}
~~~

Điều kiện là các truy cập khác cũng tuân thủ wrapper và cùng quy tắc bảo vệ, không đi vòng qua một tham chiếu gốc không được khóa. Việc đọc xong không giữ cho map bất biến mãi về sau. Nếu giá trị có thể thay đổi bên trong, cũng cần chính sách riêng cho các đối tượng đó. [Java 17: Collections.synchronizedNavigableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedNavigableMap(java.util.NavigableMap))

## 9. Chương trình Java đầy đủ

Lưu mã sau vào `TreeMapEndpointsDemo.java`. Chương trình dùng các map riêng để tách từng câu hỏi: thứ tự tự nhiên, rỗng, một ánh xạ, comparator đảo, ảnh chụp cặp, giá trị có thể thay đổi, null và view.

Các phép kiểm tra khẳng định những điều mà phần giải thích dựa vào. Không có phép đo thời gian hoặc giả định về danh tính đối tượng entry.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.NavigableMap;
import java.util.NoSuchElementException;
import java.util.TreeMap;
import java.util.function.Supplier;

public class TreeMapEndpointsDemo {
    private static TreeMap<Integer, String> sample() {
        TreeMap<Integer, String> map = new TreeMap<>();
        map.put(30, "thirty");
        map.put(10, "ten");
        map.put(20, "twenty");
        return map;
    }

    private static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected result");
        }
    }

    private static String emptyKeyResult(Supplier<?> operation) {
        try {
            operation.get();
            return "returned";
        } catch (NoSuchElementException exception) {
            return exception.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        TreeMap<Integer, String> natural = sample();
        require(natural.firstKey() == 10 && natural.lastKey() == 30);
        System.out.println("natural/firstKey=" + natural.firstKey()
                + ", lastKey=" + natural.lastKey());
        System.out.println("natural/firstEntry=" + natural.firstEntry()
                + ", lastEntry=" + natural.lastEntry());
        System.out.println("natural/afterReads=" + natural);

        TreeMap<Integer, String> empty = new TreeMap<>();
        System.out.println("empty/firstKey=" + emptyKeyResult(empty::firstKey));
        System.out.println("empty/lastKey=" + emptyKeyResult(empty::lastKey));
        System.out.println("empty/firstEntry=" + empty.firstEntry()
                + ", lastEntry=" + empty.lastEntry());

        TreeMap<Integer, String> single = new TreeMap<>();
        single.put(7, "only");
        require(single.firstKey().equals(single.lastKey()));
        System.out.println("single/firstEntry=" + single.firstEntry()
                + ", lastEntry=" + single.lastEntry());

        TreeMap<Integer, String> reversed =
                new TreeMap<>(Comparator.reverseOrder());
        reversed.putAll(sample());
        require(reversed.firstKey() == 30 && reversed.lastKey() == 10);
        System.out.println("reverse/firstKey=" + reversed.firstKey()
                + ", lastKey=" + reversed.lastKey());
        System.out.println("reverse/firstEntry=" + reversed.firstEntry()
                + ", lastEntry=" + reversed.lastEntry());

        TreeMap<Integer, String> changing = sample();
        Map.Entry<Integer, String> captured = changing.firstEntry();
        changing.put(10, "TEN");
        require(captured.getValue().equals("ten"));
        System.out.println("snapshot/captured=" + captured
                + ", current=" + changing.firstEntry());
        changing.remove(10);
        require(captured.getKey() == 10 && changing.firstKey() == 20);
        System.out.println("snapshot/afterRemove=" + captured
                + ", newFirst=" + changing.firstEntry());
        boolean rejected = false;
        try {
            captured.setValue("forbidden");
        } catch (UnsupportedOperationException exception) {
            rejected = true;
        }
        require(rejected);
        System.out.println("snapshot/setValueRejected=" + rejected);

        TreeMap<Integer, List<String>> mutable = new TreeMap<>();
        mutable.put(1, new ArrayList<>(List.of("draft")));
        Map.Entry<Integer, List<String>> shallow = mutable.firstEntry();
        mutable.get(1).add("reviewed");
        require(shallow.getValue().equals(List.of("draft", "reviewed")));
        System.out.println("shallow/afterObjectMutation=" + shallow.getValue());
        mutable.put(1, new ArrayList<>(List.of("replacement")));
        System.out.println("shallow/oldValue=" + shallow.getValue()
                + ", currentValue=" + mutable.firstEntry().getValue());

        TreeMap<Integer, String> nullValue = new TreeMap<>();
        nullValue.put(1, null);
        Map.Entry<Integer, String> present = nullValue.firstEntry();
        require(present != null && present.getValue() == null);
        System.out.println("nullValue/entryPresent=" + (present != null)
                + ", key=" + present.getKey() + ", value=" + present.getValue());

        TreeMap<String, String> nullKey =
                new TreeMap<>(Comparator.nullsFirst(
                        Comparator.<String>naturalOrder()));
        nullKey.put("A", "alpha");
        nullKey.put(null, "unknown");
        require(!nullKey.isEmpty() && nullKey.firstKey() == null);
        System.out.println("nullKey/empty=" + nullKey.isEmpty()
                + ", firstKey=" + nullKey.firstKey());
        System.out.println("nullKey/firstEntry=" + nullKey.firstEntry());

        TreeMap<Integer, String> parent = sample();
        NavigableMap<Integer, String> window =
                parent.subMap(15, true, 30, false);
        require(window.firstKey() == 20 && window.lastKey() == 20);
        System.out.println("view/firstKey=" + window.firstKey()
                + ", lastKey=" + window.lastKey());
        NavigableMap<Integer, String> emptyWindow =
                parent.subMap(11, true, 19, true);
        require(parent.size() == 3 && emptyWindow.isEmpty());
        System.out.println("view/parentSize=" + parent.size()
                + ", emptyWindowFirst=" + emptyWindow.firstEntry());
        System.out.println("view/emptyWindowFirstKey="
                + emptyKeyResult(emptyWindow::firstKey));

        NavigableMap<Integer, String> backward = parent.descendingMap();
        require(backward.firstKey().equals(parent.lastKey()));
        System.out.println("descending/firstEntry=" + backward.firstEntry()
                + ", lastEntry=" + backward.lastEntry());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~shell
javac --release 17 -encoding UTF-8 TreeMapEndpointsDemo.java
java TreeMapEndpointsDemo
~~~

Stdout của lần chạy kiểm chứng:

~~~text
natural/firstKey=10, lastKey=30
natural/firstEntry=10=ten, lastEntry=30=thirty
natural/afterReads={10=ten, 20=twenty, 30=thirty}
empty/firstKey=NoSuchElementException
empty/lastKey=NoSuchElementException
empty/firstEntry=null, lastEntry=null
single/firstEntry=7=only, lastEntry=7=only
reverse/firstKey=30, lastKey=10
reverse/firstEntry=30=thirty, lastEntry=10=ten
snapshot/captured=10=ten, current=10=TEN
snapshot/afterRemove=10=ten, newFirst=20=twenty
snapshot/setValueRejected=true
shallow/afterObjectMutation=[draft, reviewed]
shallow/oldValue=[draft, reviewed], currentValue=[replacement]
nullValue/entryPresent=true, key=1, value=null
nullKey/empty=false, firstKey=null
nullKey/firstEntry=null=unknown
view/firstKey=20, lastKey=20
view/parentSize=3, emptyWindowFirst=null
view/emptyWindowFirstKey=NoSuchElementException
descending/firstEntry=30=thirty, lastEntry=10=ten
~~~

Mã đã biên dịch với `--release 17` và chạy thành công. Tùy chọn release xác định mức API và mã đích tương thích; nó không khẳng định JVM thực thi là đúng bản JDK 17.

## 10. Giải thích các nhóm kết quả

### 10.1. Natural, empty và single

Ba dòng natural cho thấy các lần đọc hai đầu không xóa dữ liệu. Map vẫn chứa 10, 20, 30 sau các lời gọi.

Các dòng empty đối chiếu hai cách báo rỗng: phương thức trả khóa ném NoSuchElementException, phương thức trả entry cho null.

Ở single, cả đầu và cuối biểu diễn `7=only`. Chương trình không so sánh hai entry bằng `==` vì không cần cam kết chúng là cùng đối tượng.

### 10.2. Reverse và descending

Map tạo bằng comparator giảm dần có firstKey bằng 30 và lastKey bằng 10. View descending của map tăng dần cũng có hai đầu tương ứng.

Cùng chữ first nhưng kết quả phụ thuộc quy tắc thứ tự. Đây là kết quả cần kiểm tra khi một báo cáo “đầu danh sách” có vẻ ngược mong đợi.

### 10.3. Snapshot

Cặp captured vẫn là `10=ten` sau khi map thành `10=TEN`. Sau khi xóa 10, cặp cũ vẫn đọc được như dữ liệu kết quả đã chụp, trong khi đầu hiện tại của map là `20=twenty`.

SetValue bị từ chối. Tình huống này minh họa entry điều hướng không phải một tay cầm dùng để sửa trực tiếp vị trí đầu hiện tại của cây.

### 10.4. Shallow

Sau khi thêm phần tử `reviewed` vào cùng List, entry cũ thấy `[draft, reviewed]`. Sau khi map được gán một List mới, entry cũ vẫn giữ List cũ, còn entry mới cho `[replacement]`.

Như vậy, ảnh chụp cặp tách việc thay tham chiếu ánh xạ, nhưng không tự sao chép nội dung List.

### 10.5. Null và view

Entry của map có giá trị null vẫn tồn tại. Map cho phép khóa null không rỗng dù firstKey trả null. Các phép kiểm tra dùng đối tượng entry và isEmpty rõ ràng, không suy từ cách in.

View có một khóa cho cùng khóa ở hai đầu. View rỗng trả firstEntry null dù gốc có ba ánh xạ. Lỗi rỗng thuộc phạm vi đang được hỏi.

## 11. Các lỗi dễ gặp

| Lỗi | Điều cần sửa trong cách nghĩ |
|---|---|
| First là phần tử được chèn đầu tiên | First theo thứ tự khóa hiện tại |
| Last là giá trị lớn nhất | Last chọn theo khóa và comparator |
| FirstKey trả null khi map rỗng | Map rỗng ném NoSuchElementException |
| Entry.getValue bằng null nghĩa là không có entry | Kiểm tra chính entry trước |
| FirstKey bằng null nghĩa là map rỗng | Comparator có thể cho phép khóa null |
| Entry trả về luôn cập nhật theo map | Entry điều hướng của TreeMap là ảnh chụp cặp |
| SetValue trên firstEntry sẽ sửa đầu cây | Thao tác không được hỗ trợ |
| Ảnh chụp entry là sao chép sâu | Khóa và giá trị có thể vẫn là các tham chiếu chung |
| Map gốc không rỗng nên mọi view đều có hai đầu | Mỗi view có phạm vi riêng và có thể rỗng |
| Hai lần đọc hai đầu là một lần chụp toàn map | Cần chính sách bảo vệ nếu có sửa đổi cạnh tranh |
| Bốn phương thức đọc sẽ lấy phần tử ra | Chúng không xóa ánh xạ |
| Chỉ cần đổi kiểu biến thành Map để bỏ thứ tự | Thứ tự của đối tượng TreeMap không đổi theo kiểu tham chiếu |

## 12. Thực hành và lời giải

### Bài 1. Nhận diện đúng hai đầu

TreeMap tự nhiên nhận các khóa 80, 10, 50 theo thứ tự chèn đó. FirstKey và lastKey là gì? Nếu dùng comparator giảm dần thì sao?

**Lời giải:** Tự nhiên cho 10 và 80. Giảm dần cho 80 và 10. Thứ tự chèn không quyết định hai đầu; comparator hoặc thứ tự tự nhiên quyết định.

### Bài 2. Chọn hợp đồng rỗng

Một màn hình có thể chưa có bản ghi, cần hiển thị cặp cuối nếu có. Chọn lastKey rồi get hay lastEntry? Cần xử lý điều gì trước khi đọc giá trị?

**Lời giải:** LastEntry diễn đạt trực tiếp nhu cầu lấy cặp và cho null khi rỗng. Phải kiểm tra entry khác null trước khi gọi getKey/getValue. Giá trị bên trong entry cũng có thể null theo chính sách dữ liệu.

### Bài 3. Cặp đã chụp

Map có 1=old và 2=other. Lấy firstEntry rồi put(1, "new"), sau đó xóa 1. Entry đã lấy có tự biến thành 2=other không?

**Lời giải:** Không. Entry điều hướng là ảnh chụp cặp 1=old. Lần đọc firstEntry mới sau khi xóa cho cặp 2=other. Kết quả cũ không tự theo dõi đầu hiện tại của map.

### Bài 4. Không sửa được entry nhưng List vẫn đổi

Giá trị của firstEntry là một ArrayList. SetValue không được hỗ trợ, nhưng thêm phần tử qua entry.getValue vẫn có thể làm thay đổi List. Có mâu thuẫn không?

**Lời giải:** Không. Không hỗ trợ thay trường value của cặp không làm đối tượng List bất biến. Entry giữ tham chiếu đến List; thao tác trên chính List vẫn phụ thuộc hợp đồng List và chính sách dữ liệu.

### Bài 5. View rỗng

Gốc chứa 10, 20, 30. View là subMap(11, true, 19, true). FirstEntry của view và firstKey của view có hành vi gì?

**Lời giải:** View không có ánh xạ. FirstEntry trả null; firstKey ném NoSuchElementException. Gốc không rỗng không thay đổi hợp đồng rỗng của view.

### Bài 6. Khóa null

Một TreeMap dùng comparator nullsFirst và có khóa null cùng khóa A. FirstKey trả null. Có thể dùng kết quả đó để thông báo map rỗng không?

**Lời giải:** Không. Đó là khóa null hợp lệ trong thứ tự đã chọn. Có thể đọc firstEntry rồi kiểm tra đối tượng entry hoặc kiểm tra isEmpty trong bối cảnh truy cập hợp lệ. Map rỗng gọi firstKey sẽ ném ngoại lệ.

### Bài 7. Hai bước đọc và thay đổi xen giữa

Mã lấy firstKey rồi get giá trị bằng khóa đó trên map được chia sẻ. Giữa hai bước, ánh xạ bị xóa. Vì sao một lần get trả null không thể được hiểu đơn giản là “map ban đầu không có dữ liệu”?

**Lời giải:** Hai bước đã quan sát các thời điểm khác nhau. Khóa tồn tại tại lần đọc đầu nhưng có thể không còn ở lần sau; ngoài ra giá trị null cũng có thể là dữ liệu hợp lệ. Nếu cần cặp, dùng phương thức trả entry phù hợp; nếu cần tính nhất quán đồng thời hoặc hành động tiếp theo, thiết kế chính sách bảo vệ trọn phạm vi cần thiết.

## 13. Trước khi chọn một trong bốn phương thức

Hãy xác định thứ tự đang dùng, cần khóa hay cả cặp, trạng thái rỗng có bình thường hay không và kết quả sẽ được dùng như dữ liệu đã đọc hay căn cứ cho một thao tác sửa tiếp theo.

Bốn phương thức đều quan sát hai đầu. Khác biệt về kiểu kết quả và cách báo rỗng giúp ứng dụng biểu diễn đúng nhu cầu; hiểu ảnh chụp cặp giúp tránh nhầm một kết quả đọc với liên kết sống đến dữ liệu hiện tại.
