# descendingSet và descendingIterator trong NavigableSet

## 1. Hai nhu cầu khác nhau khi đọc theo thứ tự ngược

Giả sử một `NavigableSet<Integer>` đang có thứ tự `[10, 20, 30, 40]`. Ta muốn đọc từ 40 về 10. Có hai nhu cầu:

- Chỉ cần một lượt duyệt ngược để in hoặc xử lý từng phần tử.
- Cần tiếp tục làm việc với một tập theo thứ tự đảo: lấy đầu/cuối, tìm hàng xóm, tạo khoảng hoặc thêm/xóa phần tử.

`descendingIterator()` phục vụ nhu cầu thứ nhất, trả về một `Iterator<E>`. `descendingSet()` phục vụ nhu cầu thứ hai, trả về một `NavigableSet<E>` là **góc nhìn theo thứ tự đảo** của tập hiện tại.

| Thuộc tính | descendingSet() | descendingIterator() |
| --- | --- | --- |
| Kiểu trả về | `NavigableSet<E>` | `Iterator<E>` |
| Mục đích | Làm việc với một tập theo thứ tự đảo | Duyệt một lần theo thứ tự đảo |
| Có `first`, `last`, `lower`, `subSet` | Có | Không |
| Có trạng thái vị trí đang duyệt | Mỗi iterator tạo từ góc nhìn có trạng thái riêng | Có |
| Là bản sao dữ liệu độc lập | Không | Không |
| Có thể làm thay đổi tập gốc | Có, nếu góc nhìn hỗ trợ thao tác đó | `remove()` có thể xóa nếu được hỗ trợ |

Hai phương thức đều đang được sử dụng trên Java hiện đại. Các ví dụ trong bài chạy bằng Java 17 trở lên và dùng `TreeSet` làm cách cài đặt cụ thể.

## 2. “Ngược” là ngược thứ tự hiện tại

### 2.1. Thứ tự không nhất thiết là số tăng dần

Một `TreeSet` dùng thứ tự tự nhiên hoặc `Comparator` được chỉ định. `descendingSet()` đảo **thứ tự ấy**.

```text
Tập theo thứ tự tự nhiên:
[1, 2, 3]
Góc nhìn đảo:
[3, 2, 1]

Tập vốn dùng Comparator.reverseOrder():
[3, 2, 1]
Góc nhìn đảo của tập này:
[1, 2, 3]
```

Do đó, không nên hiểu tên `descending` là lời hứa “giá trị số luôn giảm”. Với tên người sắp theo độ dài rồi theo bảng chữ cái, nó đảo toàn bộ quy tắc so sánh đó.

Việc tạo góc nhìn không thay comparator hoặc vị trí phần tử của tập gốc. Tập gốc vẫn có cùng thứ tự khi gọi `iterator()`; chỉ góc nhìn dùng chiều ngược.

### 2.2. Hai cách duyệt tương ứng

Với cùng tập s, hai cách sau có cùng thứ tự duyệt khi dữ liệu không thay đổi:

```java
// Đoạn minh họa trong ngữ cảnh s là NavigableSet<E>.
Iterator<E> firstWay = s.descendingIterator();
Iterator<E> secondWay = s.descendingSet().iterator();
```

Mỗi iterator là một đối tượng có trạng thái riêng. Gọi `next()` trên iterator thứ nhất không làm iterator thứ hai tự tiến lên.

Muốn duyệt lại từ đầu, tạo iterator mới. Iterator đã đi hết không tự quay về đầu, và `Iterator` không có thao tác `previous()` như `ListIterator`.

Hợp đồng góc nhìn đảo và iterator đảo được mô tả trong [NavigableSet API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/NavigableSet.html).

## 3. descendingSet là góc nhìn liên kết

### 3.1. Một tập dữ liệu, hai hướng quan sát

Xét:

```java
// Đoạn minh họa, cần import java.util.* hoặc các kiểu tương ứng.
NavigableSet<Integer> base =
        new TreeSet<>(List.of(10, 20, 30, 40));
NavigableSet<Integer> descending = base.descendingSet();
```

Hai biến không đại diện cho hai kho dữ liệu độc lập:

```text
base                   descending
10 -> 20 -> 30 -> 40    40 -> 30 -> 20 -> 10
         cùng các phần tử, hai thứ tự nhìn
```

Với `TreeSet`, các thay đổi được phản ánh qua cả hai phía:

| Thao tác | Ảnh hưởng |
| --- | --- |
| `descending.add(25)` | Tập gốc có thêm 25 đúng vị trí sắp xếp |
| `base.remove(10)` | Góc nhìn không còn 10 |
| `base.add(50)` | 50 xuất hiện đầu tiên ở góc nhìn đảo |
| `descending.clear()` | Xóa toàn bộ phần tử mà góc nhìn này nhìn thấy khỏi tập gốc |

Một tập con đảo có giới hạn thì `clear()` chỉ xóa phần tử thuộc khoảng của tập con, không phải mọi phần tử của tập gốc. Vẫn phải coi đây là thao tác sửa dữ liệu dùng chung.

`add` không phải thao tác “chèn ở đầu danh sách”. Phần tử luôn được đặt theo comparator, không theo vị trí mong muốn hoặc thời điểm thêm.

### 3.2. Góc nhìn đảo hai lần

`s.descendingSet().descendingSet()` có cùng thứ tự và nội dung quan sát được như s.

Đây là tương đương về hành vi. Không viết chương trình dựa vào giả định hai biểu thức luôn có cùng danh tính đối tượng với toán tử `==`. Điều cần dùng là thứ tự, phần tử và quan hệ liên kết với dữ liệu gốc.

### 3.3. Góc nhìn không phải bản chụp

Tạo `descending` hôm nay rồi thêm phần tử vào `base` sau đó sẽ làm nội dung đọc từ góc nhìn thay đổi. Nếu cần giữ kết quả tại một thời điểm, hãy tạo bản sao dưới điều kiện truy cập dữ liệu được kiểm soát.

Các lựa chọn:

```java
// Đoạn minh họa: descending có kiểu NavigableSet<Integer>.
NavigableSet<Integer> setCopy = new TreeSet<>(descending);
List<Integer> listCopy = new ArrayList<>(descending);
```

Ở lệnh đầu, constructor nhận `SortedSet` được chọn vì `NavigableSet` kế thừa `SortedSet`; bản sao giữ thứ tự/comparator của nguồn. Lệnh thứ hai giữ thứ tự duyệt tại thời điểm sao chép trong một danh sách.

Nếu nguồn chỉ được khai báo dưới kiểu `Collection`, constructor `TreeSet(Collection)` có hợp đồng dùng thứ tự tự nhiên. Khi muốn nêu rõ comparator và tránh phụ thuộc vào kiểu tĩnh ở vị trí gọi:

```java
// Đoạn minh họa tạo tập độc lập, giữ comparator của nguồn.
NavigableSet<Integer> setCopy =
        new TreeSet<>(descending.comparator());
setCopy.addAll(descending);
```

Bản sao cấu trúc là sao chép nông: phần tử là đối tượng có thể thay đổi thì hai cấu trúc vẫn giữ tham chiếu tới cùng đối tượng. Bản sao cũng không mặc nhiên là bất biến.

## 4. Các thao tác trên góc nhìn phải đọc theo thứ tự mới

### 4.1. first và last

Với tập gốc tăng `[10, 20, 30, 40]`:

```text
base.first()       -> 10
base.last()        -> 40
descending.first() -> 40
descending.last()  -> 10
```

Trên tập rỗng, `first()` và `last()` ném `NoSuchElementException`. Việc có góc nhìn không tạo ra một phần tử đầu/cuối giả.

### 4.2. Điều hướng cũng đảo chiều

Với các giá trị `[10, 20, 30, 40]`, trên góc nhìn đảo:

```text
descending.lower(30)  -> 40
descending.higher(30) -> 20
```

Theo comparator đảo, 40 đứng trước 30 còn 20 đứng sau 30. Đừng mang trực giác nhỏ/lớn số học của tập tăng sang áp dụng nguyên xi. Quy tắc nhận bằng của `floor` và `ceiling` vẫn giữ nguyên, nhưng phía tìm kiếm là phía trong thứ tự mới.

### 4.3. Khoảng cũng đi theo comparator đảo

Giả sử góc nhìn đang có:

```text
[50, 40, 30, 25, 20]
```

Muốn lấy đoạn từ 40 tới trước 20 theo thứ tự này:

```java
// Đoạn minh họa trong ngữ cảnh có biến descending.
NavigableSet<Integer> window =
        descending.subSet(40, true, 20, false);
```

Kết quả là `[40, 30, 25]`. Đầu nhận 40, cuối loại 20.

Ngược lại, `descending.subSet(20, true, 40, false)` đưa hai đầu theo thứ tự sai đối với comparator của góc nhìn, nên `TreeSet` ném `IllegalArgumentException`.

Tương tự, `headSet` nghĩa là đoạn đứng trước một mốc theo thứ tự đang dùng; `tailSet` nghĩa là đoạn từ mốc về phía sau. Với góc nhìn giảm, “đứng trước” có thể là các số lớn hơn mốc. Hãy viết ra thứ tự quan sát được trước khi chọn hai đầu khoảng.

## 5. descendingIterator: vòng đời một lượt duyệt

### 5.1. hasNext và next

Mẫu duyệt:

```java
// Đoạn minh họa, s là NavigableSet<Integer>.
Iterator<Integer> iterator = s.descendingIterator();
while (iterator.hasNext()) {
    Integer value = iterator.next();
    System.out.println(value);
}
```

- `hasNext()` hỏi còn phần tử để lấy không.
- `next()` lấy phần tử kế tiếp theo chiều đảo và tiến vị trí.
- `next()` khi hết dữ liệu ném `NoSuchElementException`.

Tập rỗng vẫn tạo được iterator; `hasNext()` trả `false`. Không cần cố gọi `next()` để kiểm tra rỗng.

Iterator là công cụ duyệt một chiều. Nó không tự sắp lại dữ liệu, không lưu toàn bộ kết quả thành một danh sách và không hỗ trợ truy cập theo chỉ số.

### 5.2. Xóa đúng phần tử đang duyệt

Iterator của `TreeSet` hỗ trợ `remove()`. Sau một lần `next()`, gọi `remove()` để xóa phần tử vừa trả về:

```java
// Đoạn minh họa với TreeSet đang được tham chiếu qua s.
Iterator<Integer> iterator = s.descendingIterator();
while (iterator.hasNext()) {
    int value = iterator.next();
    if (value >= 40) {
        iterator.remove();
    }
}
```

Phép xóa này ảnh hưởng tập gốc và các góc nhìn liên quan. Không thay bằng `s.remove(value)` ngay trong vòng lặp rồi cho rằng iterator sẽ tự điều chỉnh.

Với iterator của `TreeSet`, gọi `remove()` trước `next()`, hoặc gọi hai lần cho cùng một kết quả `next()`, gây `IllegalStateException`. Trên một cách cài đặt hoặc lớp bao không cho sửa, thao tác xóa có thể không được hỗ trợ và ném `UnsupportedOperationException`. Tính có thể sửa phải được kiểm tra theo hợp đồng của tập thực tế, không chỉ dựa vào kiểu `NavigableSet`.

### 5.3. Thay đổi bên ngoài trong lúc duyệt

Iterator của `TreeSet` là fail-fast: một thay đổi cấu trúc bên ngoài iterator, kể cả qua góc nhìn khác, có thể bị phát hiện bằng `ConcurrentModificationException`.

Ví dụ sai về cách phối hợp thao tác:

```java
// Đoạn minh họa lỗi; không dùng làm mẫu xử lý.
Iterator<Integer> iterator = base.descendingIterator();
while (iterator.hasNext()) {
    int value = iterator.next();
    if (value == 40) {
        base.add(45); // Thay cấu trúc từ bên ngoài iterator.
    }
}
```

Fail-fast là cơ chế phát hiện lỗi theo nỗ lực tốt nhất, không phải khóa đồng bộ hoặc lời hứa mọi thay đổi đều ném lỗi ở cùng một thời điểm. Không dùng việc có/không có ngoại lệ này để chứng minh chương trình an toàn nhiều luồng. Xem hợp đồng iterator và đồng bộ trong [TreeSet API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeSet.html).

Nếu muốn vừa duyệt vừa thay đổi theo nhiều cách, lựa chọn thường là chỉ xóa qua iterator, gom các thay đổi lại để áp dụng sau, hoặc duyệt trên một bản sao phù hợp. Mỗi cách có ý nghĩa khác nhau về dữ liệu được quan sát.

## 6. Chương trình hoàn chỉnh

Lưu thành **DescendingSetDemo.java**. Hàm `collect` chỉ thu một lượt iterator thành danh sách để thuận tiện in và đối chiếu; bản thân `descendingIterator()` không tạo danh sách này.

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Iterator;
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

public class DescendingSetDemo {
    static <E> List<E> collect(Iterator<E> iterator) {
        List<E> result = new ArrayList<>();
        while (iterator.hasNext()) result.add(iterator.next());
        return result;
    }

    public static void main(String[] args) {
        NavigableSet<Integer> base =
                new TreeSet<>(List.of(10, 20, 30, 40));
        NavigableSet<Integer> descending = base.descendingSet();
        System.out.println("Base: " + base);
        System.out.println("View: " + descending);
        System.out.println("Descending iterator: " +
                collect(base.descendingIterator()));
        System.out.println("View iterator: " +
                collect(descending.iterator()));

        descending.add(25);
        System.out.println("After view.add(25): " + base);
        base.remove(10);
        base.add(50);
        System.out.println("After base changes: " + descending);
        System.out.println("View first/last: " +
                descending.first() + "/" + descending.last());

        NavigableSet<Integer> window =
                descending.subSet(40, true, 20, false);
        System.out.println("View range: " + window);
        System.out.println("View lower(30): " + descending.lower(30));
        System.out.println("View higher(30): " + descending.higher(30));
        try {
            descending.subSet(20, true, 40, false);
        } catch (IllegalArgumentException ex) {
            System.out.println("Ascending bounds rejected");
        }

        Iterator<Integer> iterator = base.descendingIterator();
        while (iterator.hasNext()) {
            int value = iterator.next();
            if (value >= 40) iterator.remove();
        }
        System.out.println("After iterator.remove: " + base);
        System.out.println("View after removal: " + descending);

        NavigableSet<Integer> setCopy = new TreeSet<>(descending);
        List<Integer> listCopy = new ArrayList<>(descending);
        base.add(35);
        System.out.println("Live view: " + descending);
        System.out.println("Set copy: " + setCopy);
        System.out.println("List copy: " + listCopy);
        System.out.println("Double descending: " +
                descending.descendingSet());

        NavigableSet<Integer> alreadyDescending =
                new TreeSet<>(Comparator.reverseOrder());
        alreadyDescending.addAll(List.of(1, 2, 3));
        System.out.println("Reverse comparator base: " + alreadyDescending);
        System.out.println("Reverse of that: " +
                alreadyDescending.descendingSet());
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 DescendingSetDemo.java
java DescendingSetDemo
```

Kết quả chuẩn:

```text
Base: [10, 20, 30, 40]
View: [40, 30, 20, 10]
Descending iterator: [40, 30, 20, 10]
View iterator: [40, 30, 20, 10]
After view.add(25): [10, 20, 25, 30, 40]
After base changes: [50, 40, 30, 25, 20]
View first/last: 50/20
View range: [40, 30, 25]
View lower(30): 40
View higher(30): 25
Ascending bounds rejected
After iterator.remove: [20, 25, 30]
View after removal: [30, 25, 20]
Live view: [35, 30, 25, 20]
Set copy: [30, 25, 20]
List copy: [30, 25, 20]
Double descending: [20, 25, 30, 35]
Reverse comparator base: [3, 2, 1]
Reverse of that: [1, 2, 3]
```

Các điểm cần đối chiếu:

1. Hai iterator ban đầu cho cùng thứ tự ngược.
2. Thêm qua góc nhìn làm tập gốc có thêm phần tử; sửa tập gốc làm góc nhìn đổi.
3. Khoảng trên góc nhìn dùng đầu 40 trước đầu 20.
4. Xóa qua iterator làm cả tập gốc và góc nhìn đổi.
5. Hai bản sao không nhận phần tử 35 được thêm sau.
6. Đảo tập đã dùng comparator ngược tạo thứ tự số tăng.

## 7. Chi phí và lựa chọn trong ứng dụng

Với `TreeSet`, góc nhìn dùng chung cây dữ liệu, không cần sao chép rồi sắp xếp lại toàn bộ n phần tử. Tạo iterator cũng không có nghĩa vật chất hóa một danh sách đảo n phần tử. Duyệt toàn bộ cây theo iterator có thời gian O(n); các phép tìm kiếm hoặc thêm/xóa trên cây vẫn dựa vào cấu trúc cây cân bằng.

Đừng suy ra mọi cách cài đặt `NavigableSet` có cùng chi phí nội bộ hoặc hai chiều luôn có tốc độ y hệt. Khi hiệu năng hai hướng là quan trọng, đo với cách cài đặt và khối lượng dữ liệu cụ thể.

Bản sao thành `ArrayList` cần O(n) bộ nhớ cho các tham chiếu; bản sao thành tập cần thêm cấu trúc lưu trữ. Góc nhìn liên kết có thể tiết kiệm việc sao chép, nhưng nó cũng giữ liên hệ với tập gốc và quan sát các thay đổi của tập gốc.

Chọn theo nhu cầu:

| Nhu cầu | Cách phù hợp |
| --- | --- |
| In các mã lớn trước một lần | `descendingIterator()` |
| Lặp bằng for-each theo chiều ngược | `for (E value : s.descendingSet())` |
| Tìm đầu/cuối hoặc khoảng trong thứ tự ngược | `descendingSet()` |
| Giữ kết quả xuất báo cáo độc lập với sửa tập sau đó | Tạo bản sao, bảo đảm việc sao chép diễn ra trên dữ liệu ổn định |
| Chỉ đọc k phần tử lớn nhất hiện có | Iterator đảo và bộ đếm k, khi thứ tự gốc tăng |
| Lấy và xóa liên tục phần tử ở một đầu | Chọn thao tác lấy/xóa đầu thích hợp; đó là sửa dữ liệu, khác với duyệt |

Nếu dữ liệu có thể bị sửa đồng thời, việc sao chép cũng cần cơ chế phối hợp; một constructor sao chép không tự khóa tập nguồn. `TreeSet` không tự an toàn cho truy cập nhiều luồng có sửa dữ liệu.

Tập chỉ giữ các phần tử duy nhất theo thứ tự so sánh. Nếu cần xếp hạng có nhiều mục cùng điểm, đừng vô tình dùng comparator chỉ theo điểm rồi làm mất các mục khác. Quy tắc duy nhất của tập vẫn giữ nguyên khi nhìn theo chiều đảo.

## 8. Lỗi phổ biến

| Lỗi | Hậu quả hoặc cách sửa |
| --- | --- |
| Coi `descendingSet` là bản sao | Thêm/xóa qua một phía làm phía kia đổi |
| Coi iterator đảo là `ListIterator` | Không có `previous`, không truy cập chỉ số |
| Duyệt lại bằng iterator đã dùng hết | Tạo iterator mới cho lượt mới |
| Gọi `next` mà không biết còn dữ liệu | Dùng `hasNext` trước |
| Gọi `remove` hai lần sau một `next` | Vi phạm vòng đời của iterator |
| Sửa `base` trong lúc iterator của góc nhìn đang chạy | Có thể gây lỗi phát hiện sửa đổi đồng thời |
| Dùng khoảng tăng dần trên góc nhìn giảm | Hai đầu có thể sai thứ tự comparator |
| Nghĩ `lower` luôn cho số nhỏ hơn | Đọc quan hệ theo comparator của góc nhìn |
| Dùng `==` để kiểm tra đảo hai lần | Dựa vào hành vi/thứ tự, không phụ thuộc danh tính |
| Sao chép dưới kiểu nguồn không phù hợp rồi mất comparator | Chọn rõ constructor hoặc truyền comparator |

## 9. Thực hành

1. Với tập tăng `[2, 5, 8]`, tạo góc nhìn đảo và một iterator đảo. Cả hai lượt đọc phải cho `8, 5, 2`.
2. Thêm 6 qua góc nhìn. Tập gốc phải thành `[2, 5, 6, 8]`; góc nhìn thành `[8, 6, 5, 2]`.
3. Trên góc nhìn đó, tạo `subSet(8, true, 5, false)`. Kết quả phải là `[8, 6]`. Giải thích vì sao đảo hai đầu không còn hợp lệ.
4. Dùng iterator đảo xóa các số lớn hơn 5. Tập gốc cuối cùng phải là `[2, 5]`, không cần bắt `ConcurrentModificationException` để hoàn thành thao tác.
5. Tạo một bản sao có thứ tự đảo trước khi xóa. Sau khi xóa dữ liệu gốc, xác minh bản sao vẫn giữ nội dung cũ và nêu giới hạn “sao chép nông” nếu phần tử là đối tượng mutable.
6. Tạo hai iterator mới từ cùng tập, lấy một phần tử bằng iterator thứ nhất rồi lấy một phần tử bằng iterator thứ hai. Cả hai phải bắt đầu ở cùng đầu đảo, không chia sẻ vị trí.

Hãy xác định cần **một góc nhìn của tập** hay **một lượt duyệt**, rồi kiểm tra thứ tự comparator và quyền sửa dữ liệu. Ba yếu tố đó quyết định cách dùng đúng `descendingSet()` và `descendingIterator()`.
