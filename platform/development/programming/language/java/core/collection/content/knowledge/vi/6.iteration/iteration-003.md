# Iterator.remove và điều kiện gọi hợp lệ

Khi vừa duyệt vừa cần xóa phần tử khỏi một collection, `Iterator.remove()` cung cấp một thao tác gắn với **chính quá trình duyệt**.

Nó không nhận phần tử hoặc chỉ số. Nếu được hỗ trợ, nó xóa khỏi collection nền **phần tử do lần next() gần nhất của iterator đó trả về**, với giới hạn một lần xóa cho mỗi lần lấy phần tử.

Muốn sử dụng đúng, cần phân biệt ba câu hỏi:

1. Iterator này có hỗ trợ xóa không?
2. Trạng thái hiện tại đã cho phép gọi remove chưa?
3. Collection có bị sửa qua một đường khác làm mất bảo đảm của quá trình duyệt không?

## 1. Vì sao có thao tác xóa trên iterator?

Giả sử danh sách số gồm:

```text
[-2, 0, 3, -1, 4]
```

Ta muốn duyệt từng số và xóa số âm ngay tại chỗ. Iterator đang theo dõi vị trí để lấy phần tử tiếp theo. Việc xóa có thể làm các phần tử phía sau dịch chuyển hoặc thay đổi liên kết bên trong collection.

Nếu dùng thao tác xóa của chính iterator, lớp triển khai có cơ hội cập nhật trạng thái duyệt phù hợp với việc xóa vừa thực hiện.

Mẫu minh họa trong một phương thức:

```java
Iterator<Integer> iterator = numbers.iterator();

while (iterator.hasNext()) {
    int number = iterator.next();
    if (number < 0) {
        iterator.remove();
    }
}
```

Ở đây, `numbers` là một danh sách có iterator hỗ trợ xóa. Thao tác xóa gắn với số vừa được trả về, không cần tìm lại số đó theo giá trị.

Điều này hữu ích cả khi có nhiều phần tử bằng nhau: iterator biết lần xuất hiện nào đã được duyệt tới.

## 2. Ba phương thức và ba vai trò khác nhau

| Phương thức | Vai trò | Có tạo một phần tử mới đủ điều kiện xóa không? |
| --- | --- | --- |
| `hasNext()` | Hỏi còn phần tử để lấy không | Không |
| `next()` | Lấy phần tử tiếp theo | Có, nếu lấy thành công |
| `remove()` | Xóa phần tử đã được lấy gần nhất | Dùng quyền xóa của phần tử đó |

`remove()` có kiểu trả về `void`. Nó không trả phần tử bị xóa và không trả boolean.

Đây là thao tác **tùy chọn** của interface `Iterator`. Nếu iterator không hỗ trợ, lời gọi có thể bị từ chối bằng `UnsupportedOperationException`.

Các quy định chính thức về phần tử bị xóa, số lần gọi, ngoại lệ và thay đổi collection được nêu trong [API Iterator.remove của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html#remove()).

## 3. Nhìn remove như một máy trạng thái nhỏ

Với iterator hỗ trợ xóa và không bị sửa collection trái hợp đồng, có thể dùng hai trạng thái:

| Trạng thái | Ý nghĩa |
| --- | --- |
| Chưa có phần tử được phép xóa | Chưa next thành công, hoặc phần tử gần nhất đã bị remove |
| Có phần tử được phép xóa | Next đã trả một phần tử và phần tử đó chưa bị remove |

Các chuyển trạng thái:

```text
Mới tạo iterator
    |
    v
CHƯA ĐƯỢC REMOVE
    |
    | next() thành công
    v
ĐƯỢC REMOVE PHẦN TỬ VỪA TRẢ VỀ
    |
    | remove() thành công
    v
CHƯA ĐƯỢC REMOVE
```

Có thể gọi `next()` lần nữa mà chưa xóa phần tử cũ. Khi đó, mục tiêu của remove chuyển sang phần tử mới được trả về. Không có việc tích lũy nhiều lượt xóa.

### 3.1. Chưa next thì không có mục tiêu xóa

Đoạn sau sai trạng thái đối với iterator hỗ trợ remove:

```java
Iterator<String> iterator = values.iterator();
iterator.remove();
```

Chưa phần tử nào được iterator trả về. Không được diễn giải remove là “xóa phần tử đầu tiên” hoặc “xóa phần tử sắp được đọc”.

Với iterator của `ArrayList`, tình huống này ném `IllegalStateException`.

### 3.2. Một lần next chỉ cho một lần remove

Chuỗi hợp lệ:

```text
next -> remove -> next -> remove
```

Chuỗi sai trạng thái:

```text
next -> remove -> remove
```

Lần remove thứ hai không có phần tử mới để xóa. Nó không có nghĩa là tiếp tục xóa phần tử kế tiếp.

Nếu muốn xóa phần tử tiếp theo, phải lấy nó bằng next rồi quyết định xóa.

### 3.3. Nhiều lần next không tạo kho lượt remove

Với dữ liệu:

```text
[A, B, C]
```

sau hai lần next trả A rồi B, một lần remove xóa B. Không thể gọi remove tiếp để quay lại xóa A.

Nếu cần quyết định xóa A, phải thực hiện khi A vẫn là phần tử vừa được trả về, hoặc chọn một chiến lược xử lý khác.

### 3.4. hasNext không thay thế next

Gọi `hasNext()` một hoặc nhiều lần không tạo ra phần tử được trả về mới.

Sau:

```text
next trả A -> hasNext -> hasNext -> remove
```

remove vẫn hướng tới A nếu chưa có thao tác khác làm trạng thái không hợp lệ.

Tương tự, sau khi lấy phần tử cuối, `hasNext()` có thể trả false nhưng remove vẫn hợp lệ đối với phần tử cuối vừa lấy. “Không còn phần tử phía sau” khác với “không còn phần tử gần nhất để xóa”.

Một lần next thất bại không trả một phần tử mới; không dùng lời gọi đó như một cách cấp thêm lượt remove.

## 4. Chương trình hoàn chỉnh về trạng thái hợp lệ

Lưu vào **IteratorRemoveStateDemo.java**. Chương trình dùng `ArrayList` để các thao tác xóa được hỗ trợ và tương thích Java 17 trở lên.

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

public class IteratorRemoveStateDemo {
    public static void main(String[] args) {
        List<String> values =
                new ArrayList<>(List.of("A", "B", "A", "C"));
        Iterator<String> iterator = values.iterator();

        try {
            iterator.remove();
        } catch (IllegalStateException ex) {
            System.out.println("Before next: " + ex.getClass().getSimpleName());
        }

        System.out.println("Next: " + iterator.next());
        System.out.println("hasNext: " + iterator.hasNext());
        iterator.remove();
        System.out.println("After first remove: " + values);

        try {
            iterator.remove();
        } catch (IllegalStateException ex) {
            System.out.println("Twice: " + ex.getClass().getSimpleName());
        }

        System.out.println("Skip removal for: " + iterator.next());
        System.out.println("Next: " + iterator.next());
        iterator.remove();
        System.out.println("After removing second A: " + values);

        System.out.println("Last next: " + iterator.next());
        System.out.println("hasNext at end: " + iterator.hasNext());
        iterator.remove();
        System.out.println("After remove at end: " + values);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 IteratorRemoveStateDemo.java
java IteratorRemoveStateDemo
```

Stdout:

```text
Before next: IllegalStateException
Next: A
hasNext: true
After first remove: [B, A, C]
Twice: IllegalStateException
Skip removal for: B
Next: A
After removing second A: [B, C]
Last next: C
hasNext at end: false
After remove at end: [B]
```

### 4.1. Đối chiếu từng giai đoạn

**Trước next:** chưa có phần tử vừa được lấy, nên remove báo sai trạng thái.

**Sau next trả A:** có mục tiêu xóa. Lời gọi hasNext chỉ hỏi phần tử tiếp theo, nên không làm mất mục tiêu A.

**Sau lần xóa đầu:** danh sách còn `[B, A, C]`. Iterator tiếp tục lấy B, không bỏ qua nó vì việc xóa đã được thực hiện qua chính iterator.

**Hai remove liên tiếp:** lần thứ hai báo `IllegalStateException`.

**B rồi A:** chương trình không xóa B. Khi next tiếp tục trả A, remove hướng tới A mới đó.

**Sau phần tử cuối C:** hasNext false nhưng C chưa bị xóa, nên một remove vẫn hợp lệ. Kết quả còn B.

Các ngoại lệ được bắt trong chương trình chỉ để quan sát hợp đồng. Trong mã ứng dụng bình thường, nên tổ chức luồng gọi đúng thay vì dùng ngoại lệ như cách điều khiển vòng lặp.

## 5. remove xóa lần xuất hiện vừa duyệt, không tìm theo giá trị

Xét:

```text
[A, B, A]
```

Nếu iterator đã đi qua A đầu tiên, B, rồi A thứ hai, `iterator.remove()` nhắm tới **A thứ hai**.

Trong khi đó, `list.remove("A")` trên `ArrayList` tìm lần xuất hiện đầu phù hợp theo giá trị. Dù cùng là “xóa A”, hai lời gọi có thể tác động lên hai vị trí khác nhau.

Ngoài ra, với `List<Integer>`, `list.remove(number)` còn có thể bị chọn overload xóa theo chỉ số nếu `number` có kiểu int. `Iterator.remove()` không có tham số, nên không có nhầm lẫn chọn giá trị hay chỉ số ở lời gọi đó.

Thao tác xóa khỏi collection cũng không tự hủy đối tượng mà mọi nơi khác đang tham chiếu. Một biến cục bộ đã nhận đối tượng từ next vẫn có thể tham chiếu đến đối tượng sau khi phần tử được loại khỏi collection.

## 6. Vì sao không gọi collection.remove trong khi đang duyệt?

Mẫu sau không phải cách thay thế an toàn chung:

```java
// Đoạn minh họa cách dùng sai đối với ArrayList thông thường.
for (String value : values) {
    if ("A".equals(value)) {
        values.remove(value);
    }
}
```

Vòng for-each đang dùng một quá trình duyệt phía sau. Lời gọi remove ở đây đi thẳng vào danh sách, không phải thao tác remove của iterator đó.

Với `ArrayList`, iterator có cơ chế phát hiện một số thay đổi cấu trúc ngoài đường được hỗ trợ và có thể ném `ConcurrentModificationException`. Ngoại lệ này không đòi phải có nhiều luồng: một luồng tự sửa danh sách trong lúc duyệt cũng có thể gây ra.

Tuy nhiên, phát hiện kiểu fail-fast chỉ là cơ chế hỗ trợ tìm lỗi theo khả năng tốt nhất. Một vòng lặp sai không báo ngoại lệ ở một dữ liệu nhỏ không trở thành cách dùng đúng. Không viết tính đúng đắn của chương trình dựa vào việc chắc chắn sẽ bắt được `ConcurrentModificationException`. Xem [API ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

Cách rõ ràng khi cần xóa trong một lượt duyệt là giữ một iterator tường minh và gọi remove của chính nó.

### Hai iterator cũng là hai trạng thái riêng

Nếu hai iterator cùng duyệt một danh sách thông thường, việc iterator thứ nhất xóa hợp lệ không tự cập nhật trạng thái của iterator thứ hai.

“Xóa qua iterator” phải hiểu là xóa qua **iterator đang thực hiện lượt duyệt đó**, không phải miễn gọi một remove từ bất kỳ iterator nào cũng an toàn cho mọi lượt duyệt khác.

Nếu lớp collection có chính sách duyệt đồng thời riêng, phải theo hợp đồng của lớp đó; không áp dụng một quy tắc fail-fast cho tất cả iterator trong JDK.

## 7. Hỗ trợ sửa collection và hỗ trợ iterator.remove là hai việc khác

Một đối tượng có phương thức `remove` không có nghĩa mọi iterator của nó đều cho xóa.

| Nguồn iterator thường gặp | Iterator.remove | Lý do cần nhớ |
| --- | --- | --- |
| `new ArrayList<>(...)` | Có hỗ trợ | Có thể loại phần tử và cập nhật quá trình duyệt |
| `Arrays.asList(...)` | Không hỗ trợ xóa cấu trúc | Danh sách có kích thước cố định |
| `List.of(...)` | Không hỗ trợ | Danh sách không cho sửa |
| `CopyOnWriteArrayList` | Không hỗ trợ trên iterator | Iterator quan sát một ảnh chụp |
| View từ một map có thể sửa như `LinkedHashMap.entrySet()` | Có thể hỗ trợ | Xóa ánh xạ qua view của map |

Phải đọc hợp đồng của nguồn cụ thể thay vì suy luận từ kiểu khai báo `Iterator<E>`.

### 7.1. Kích thước cố định khác hoàn toàn không cho sửa

`Arrays.asList` trả danh sách liên kết với mảng, có thể thay phần tử bằng set nhưng không thể giảm kích thước bằng remove. Việc iterator xóa bị từ chối không chứng minh mọi thao tác cập nhật đều bị cấm.

Nếu cần lọc và giảm số phần tử, có thể tạo `new ArrayList<>(source)` để làm việc trên một danh sách có cấu trúc riêng. Xem [API Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

### 7.2. Collection có thể sửa nhưng iterator chỉ đọc ảnh chụp

`CopyOnWriteArrayList` có thể thêm hoặc xóa qua các phương thức của chính collection. Iterator của nó đi qua ảnh chụp tại thời điểm tạo và không hỗ trợ remove.

Vì vậy, “collection có thể xóa” không kéo theo “iterator có thể xóa”. Nếu cần thay đổi một collection có chính sách đồng thời, chọn thao tác được lớp đó quy định thay vì cố dùng một mẫu cho mọi nguồn. Xem [API CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html).

### 7.3. Không trộn lỗi khả năng với lỗi trạng thái

`IllegalStateException` thường phản ánh thứ tự gọi sai khi thao tác được hỗ trợ. `UnsupportedOperationException` phản ánh iterator không cung cấp thao tác đó.

Nếu một lời gọi vừa sai trạng thái vừa nằm trên iterator không hỗ trợ remove, không nên dựa vào một ưu tiên ngoại lệ chung để đoán tình trạng. Kiểm tra khả năng hỗ trợ bằng tài liệu, và viết thứ tự gọi hợp lệ.

## 8. Chương trình hoàn chỉnh: lọc dữ liệu và quan sát khả năng hỗ trợ

Lưu vào **IteratorRemoveUsageDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;

public class IteratorRemoveUsageDemo {
    private static void showUnsupported(
            String label, Iterable<String> source) {
        Iterator<String> iterator = source.iterator();
        iterator.next();
        try {
            iterator.remove();
        } catch (UnsupportedOperationException ex) {
            System.out.println(label + ": " + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        List<Integer> numbers =
                new ArrayList<>(List.of(-2, 0, 3, -1, 4));
        int removed = 0;
        Iterator<Integer> iterator = numbers.iterator();
        while (iterator.hasNext()) {
            int number = iterator.next();
            if (number < 0) {
                iterator.remove();
                removed++;
            }
        }
        System.out.println("Numbers: " + numbers);
        System.out.println("Removed negatives: " + removed);

        Map<String, Integer> stock = new LinkedHashMap<>();
        stock.put("pen", 0);
        stock.put("book", 3);
        stock.put("bag", 0);

        Iterator<Map.Entry<String, Integer>> entries =
                stock.entrySet().iterator();
        while (entries.hasNext()) {
            Map.Entry<String, Integer> entry = entries.next();
            if (entry.getValue() == 0) {
                entries.remove();
            }
        }
        System.out.println("Stock: " + stock);

        showUnsupported("Arrays.asList", Arrays.asList("A", "B"));
        showUnsupported("List.of", List.of("A", "B"));

        CopyOnWriteArrayList<String> snapshots =
                new CopyOnWriteArrayList<>(List.of("A", "B"));
        showUnsupported("CopyOnWrite iterator", snapshots);
        snapshots.remove("A");
        System.out.println("CopyOnWrite direct remove: " + snapshots);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 IteratorRemoveUsageDemo.java
java IteratorRemoveUsageDemo
```

Stdout:

```text
Numbers: [0, 3, 4]
Removed negatives: 2
Stock: {book=3}
Arrays.asList: UnsupportedOperationException
List.of: UnsupportedOperationException
CopyOnWrite iterator: UnsupportedOperationException
CopyOnWrite direct remove: [B]
```

### 8.1. Lọc số âm

Vòng lặp gọi next đúng một lần trong mỗi lượt. Chỉ những số âm mới được remove, nên các số 0, 3 và 4 được giữ.

Biến đếm tăng sau khi remove thành công. Nó không tăng dựa vào kết quả boolean vì `Iterator.remove()` không trả boolean.

### 8.2. Xóa ánh xạ qua entrySet

Map không có phương thức iterator trực tiếp; chương trình lấy iterator từ view `entrySet()`.

Khi `entries.remove()` loại entry có số lượng 0, nó xóa ánh xạ tương ứng khỏi `stock`. Sau lượt duyệt, chỉ còn `book=3`.

Đây không phải xóa khỏi một bản sao entry tách rời. View gắn với map nền. Khả năng loại entry phụ thuộc map và view có hỗ trợ thao tác hay không; xem [API Map.entrySet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#entrySet()).

Sau khi đã xóa entry, không giữ nó như một cách chắc chắn để tiếp tục cập nhật cùng ánh xạ trong map. Nếu cần dữ liệu cho báo cáo, lấy các giá trị cần thiết theo hợp đồng trước hoặc trong lúc xử lý.

### 8.3. Phân biệt iterator với collection

Hàm `showUnsupported` gọi next trước, rồi mới thử remove. Nhờ đó, nó không cố tình tạo lỗi chưa đọc phần tử.

Ba nguồn trong ví dụ từ chối thao tác vì khả năng của iterator. Cuối cùng, xóa trực tiếp trên `CopyOnWriteArrayList` vẫn thành công sau lượt thử, cho thấy collection có thể sửa dù iterator không cung cấp remove.

Các ví dụ không dùng việc bắt ngoại lệ để suy ra mọi đặc tính của nguồn. Chúng kiểm chứng những hợp đồng đã biết của các lớp cụ thể.

## 9. forEachRemaining không phải đường tắt để gọi remove

Có thể nhìn phần triển khai mặc định của `forEachRemaining` như một lượt lấy các phần tử còn lại rồi gọi hành động. Tuy nhiên, không vì vậy mà suy ra luôn được gọi remove bên trong hành động hoặc ngay sau khi kết thúc nó.

Hợp đồng `Iterator` nêu rằng:

- Hành vi không được xác định chung nếu action sửa collection, kể cả thông qua remove, trừ khi lớp ghi đè có chính sách riêng.
- Hành vi không được xác định chung nếu remove được gọi sau một lần forEachRemaining.

Vì vậy, nếu mục đích là duyệt và loại phần tử có điều kiện theo hợp đồng iterator thông thường, dùng vòng:

```java
while (iterator.hasNext()) {
    String value = iterator.next();
    if ("obsolete".equals(value)) {
        iterator.remove();
    }
}
```

Đây là đoạn minh họa với một `Iterator<String>` hỗ trợ remove.

Không dựa vào một lớp triển khai hoặc một phiên bản JDK tình cờ cho phép remove sau forEachRemaining để coi đó là bảo đảm của interface. Xem [API Iterator.forEachRemaining](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html#forEachRemaining(java.util.function.Consumer)).

## 10. Quan hệ với ListIterator và removeIf

### 10.1. ListIterator có hợp đồng rộng hơn

`ListIterator` mở rộng Iterator, hỗ trợ cả next và previous. Remove của nó hướng tới phần tử vừa được trả về bởi một trong hai chiều duyệt.

Nó còn có add và set, nên điều kiện trạng thái cũng cần đọc riêng. Chẳng hạn, một add sau thao tác đọc có thể làm lần remove kế tiếp không hợp lệ.

Không bê máy trạng thái chỉ dùng next của bài này sang toàn bộ API ListIterator mà bỏ qua previous hoặc add. Nếu chỉ đang dùng Iterator tiến một chiều, không cần gọi những API mở rộng đó. Xem [API ListIterator.remove](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html#remove()).

### 10.2. removeIf phù hợp với điều kiện lọc đơn giản

Nếu chỉ cần loại tất cả phần tử thỏa một điều kiện, có thể diễn đạt:

```java
numbers.removeIf(number -> number < 0);
```

Dòng này là đoạn minh họa với danh sách số nguyên không null.

Nó rõ ý định “xóa phần tử thỏa điều kiện”, và một số lớp có cách triển khai tối ưu. Phần triển khai mặc định của `Collection.removeIf` duyệt và dùng iterator.remove cho phần tử khớp.

Điều đó không bảo đảm removeIf luôn chạy được trên mọi nguồn. Với nguồn không hỗ trợ thao tác thay đổi cần thiết, nó có thể bị từ chối. Predicate cũng không nên tự sửa cấu trúc collection đang lọc. Xem [API Collection.removeIf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#removeIf(java.util.function.Predicate)).

Chọn iterator tường minh khi cần điều khiển từng bước duyệt hoặc thực hiện xử lý đi kèm phần tử. Chọn removeIf khi điều kiện lọc đã mô tả đủ ý định.

## 11. Đồng thời và hiệu năng: giới hạn của bảo đảm

### 11.1. Hợp lệ trong một lượt duyệt không có nghĩa an toàn đa luồng

Iterator.remove giúp phối hợp việc xóa với trạng thái của iterator. Nó không tự khóa một `ArrayList` trước các luồng khác.

Ngay cả khi dùng `Collections.synchronizedList`, việc duyệt cần được đồng bộ theo hướng dẫn của lớp bao. Với mẫu tiêu chuẩn, toàn bộ lượt lấy iterator và duyệt phải nằm trong vùng synchronized trên đúng đối tượng list được bao, và các nơi truy cập khác phải tuân thủ cùng cơ chế.

Chỉ đồng bộ từng lời gọi riêng lẻ không biến cả chuỗi hasNext–next–remove thành một giao dịch nguyên tử. Xem [API Collections.synchronizedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedList(java.util.List)).

### 11.2. Đúng ngữ nghĩa không phải lúc nào cũng tối ưu chi phí

Với `ArrayList`, xóa một phần tử có thể phải dịch các tham chiếu ở phía sau. Xóa nhiều phần tử bằng nhiều lần remove có thể tốn chi phí đáng kể.

Nếu mục tiêu là lọc nhiều dữ liệu:

- Cân nhắc removeIf khi có thể mô tả điều kiện rõ ràng.
- Nếu cần giữ nguồn, tạo một kết quả mới chứa những phần tử được giữ.
- Đo với dữ liệu và kiểu collection thực tế khi hiệu năng quan trọng.

Không kết luận mọi Iterator.remove đều có cùng độ phức tạp. Interface quy định ý nghĩa, còn cách tổ chức dữ liệu quyết định chi phí.

## 12. Lỗi thường gặp và cách sửa

| Lỗi | Điều bị hiểu sai | Hướng sửa |
| --- | --- | --- |
| Remove ngay sau khi tạo iterator | Xem remove như xóa phần tử sắp đọc | Gọi next để lấy phần tử trước |
| Gọi remove hai lần liên tiếp | Tưởng mỗi remove tự tiến sang phần tử kế | Mỗi phần tử được next trả về chỉ có một lượt remove |
| Gọi hasNext rồi remove | Tưởng kiểm tra còn dữ liệu cũng tạo mục tiêu xóa | HasNext không thay next |
| Gọi next trong điều kiện rồi next thêm để xóa | Đã tiến qua phần tử cần xử lý | Lưu kết quả một lần next vào biến cục bộ |
| Gọi list.remove trong for-each | Sửa cấu trúc ngoài đường của iterator đang duyệt | Dùng iterator tường minh hoặc removeIf phù hợp |
| Dùng iterator từ List.of hoặc Arrays.asList | Bỏ qua giới hạn thao tác của nguồn | Chọn nguồn hỗ trợ giảm kích thước hoặc tạo bản sao |
| Nghĩ collection concurrent nào cũng hỗ trợ iterator.remove | Nhầm bảo đảm đồng thời với khả năng chỉnh sửa iterator | Đọc hợp đồng lớp cụ thể |
| Gọi remove trong hoặc sau forEachRemaining | Suy từ mã mặc định thành bảo đảm chung | Dùng vòng while rõ ràng khi cần xóa |
| Dựa vào việc không thấy ConcurrentModificationException | Coi fail-fast như cơ chế đồng bộ hoặc kiểm chứng đúng | Sửa cách duyệt, không dựa vào ngoại lệ |
| Cho iterator khác xóa rồi tiếp tục iterator hiện tại | Nhầm trạng thái nhiều iterator là một | Tránh thay đổi ngoài lượt duyệt hiện tại hoặc dùng chính sách phù hợp |

## 13. Tự kiểm tra

1. Với `[A, B, C]`, sau next trả A rồi next trả B, remove xóa phần tử nào?
2. Sau next cuối cùng và hasNext trả false, còn được remove không? Cần những điều kiện gì?
3. Vì sao hasNext không tạo quyền remove mới sau một lần remove?
4. Với `[A, B, A]`, so sánh mục tiêu xóa của iterator ở A thứ hai và `list.remove("A")`.
5. Giải thích vì sao CopyOnWriteArrayList có thể xóa trực tiếp nhưng iterator không cho remove.
6. Vì sao một lần chạy for-each kết hợp list.remove không báo lỗi vẫn không chứng minh cách viết đó an toàn?
7. Khi chỉ cần xóa các số âm, chọn iterator tường minh hay removeIf? Nêu lý do và điều kiện của nguồn dữ liệu.

Điều cần giữ rõ là **khả năng hỗ trợ**, **phần tử vừa được trả về** và **trạng thái lượt duyệt**. Khi cả ba được kiểm soát, Iterator.remove cho phép loại phần tử đúng vị trí mà không phải tìm lại nó hay tự đoán cách điều chỉnh quá trình duyệt.
