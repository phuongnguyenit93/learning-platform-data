# pollFirst, pollLast, descendingSet và descendingIterator

## 1. Chọn cách đọc hoặc lấy phần tử theo thứ tự

Giả sử một tập lưu các mức `10, 20, 30, 40` theo thứ tự tăng dần. Bạn có thể cần xem mức nhỏ nhất mà vẫn giữ dữ liệu, lấy mức lớn nhất ra để xử lý, hoặc đọc từ lớn đến nhỏ.

Ba nhu cầu ấy khác nhau ở hai điểm: **chiều đi qua dữ liệu** và **có xóa phần tử hay không**. Nếu nhầm, mã chỉ định hiển thị có thể làm mất dữ liệu; mã định xử lý từng phần tử lại có thể lặp mãi vì chưa xóa gì.

Bốn phương thức trong bài nằm trên `NavigableSet`:

- `pollFirst()`: lấy và xóa phần tử đầu.
- `pollLast()`: lấy và xóa phần tử cuối.
- `descendingSet()`: tạo khung nhìn ngược thứ tự, dùng chung các thành viên với tập nguồn.
- `descendingIterator()`: tạo bộ duyệt đi ngược thứ tự.

“Đầu/cuối” được xác định theo thứ tự của chính tập hoặc khung nhìn mà bạn gọi phương thức, không theo thời điểm phần tử được thêm. Nếu dùng `Comparator` đảo, số lớn có thể ở đầu của tập gốc và số nhỏ ở đầu của khung nhìn đảo.

Bài học dùng `TreeSet` để kiểm chứng các hành vi trên bằng API có trong Java 17. Bạn cần biết biến, vòng lặp và cách dùng một tập hợp; `NavigableSet`, khung nhìn và bộ duyệt sẽ được giải thích trước khi đi vào mã đầy đủ.

## 2. NavigableSet liên hệ thế nào với Set sắp xếp?

`Set` mô tả tập hợp không trùng. `SortedSet` bổ sung một thứ tự cùng các phép như `first()`, `last()` và lấy vùng theo thứ tự. `NavigableSet` mở rộng tiếp với các phép điều hướng và khả năng làm việc từ hai chiều.

`TreeSet` là một lớp triển khai `NavigableSet`. Có thể khai báo:

~~~java
NavigableSet<Integer> values =
        new TreeSet<>(List.of(40, 10, 30, 20));
~~~

Đây là khai báo minh họa; chương trình hoàn chỉnh phía dưới có các lệnh nhập kiểu cần thiết.

Đối tượng dùng thứ tự tự nhiên của `Integer`, nên duyệt thông thường được `[10, 20, 30, 40]`. Phần tử đầu là 10, phần tử cuối là 40, dù 40 được đưa vào danh sách nguồn trước.

Kiểu khai báo có ý nghĩa khi gọi API. Nếu biến chỉ có kiểu `Set<Integer>` hoặc `SortedSet<Integer>` trong Java 17, trình biên dịch không cho gọi mọi phương thức riêng của `NavigableSet` qua biến ấy. Chọn kiểu thể hiện đúng khả năng mà phần mã cần dùng thay vì ép kiểu tùy tiện.

`NavigableSet` còn có các phép tìm lân cận và các vùng với biên tùy chọn. Trong bài, chúng ta chỉ dùng một vùng nhỏ để quan sát phạm vi tác động của bốn phương thức chính. [Java 17: NavigableSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableSet.html).

## 3. Phân biệt đọc, lấy ra và duyệt

Với một `TreeSet` có thể sửa, bảng sau giúp chọn thao tác:

| Thao tác | Kết quả trả về | Tự xóa thành viên? | Khi không có phần tử |
| --- | --- | --- | --- |
| `first()` | Phần tử đầu | Không | `NoSuchElementException` |
| `last()` | Phần tử cuối | Không | `NoSuchElementException` |
| `pollFirst()` | Phần tử đầu bị lấy ra | Có, nếu có phần tử | Trả `null` |
| `pollLast()` | Phần tử cuối bị lấy ra | Có, nếu có phần tử | Trả `null` |
| `descendingSet()` | Một `NavigableSet` nhìn theo chiều ngược | Không vì riêng việc tạo khung nhìn | Khung nhìn rỗng |
| `descendingIterator()` | Một `Iterator` đi theo chiều ngược | Không vì riêng việc tạo hoặc đọc | `hasNext()` là `false` |

`first` và `last` là những phép đọc. `pollFirst` và `pollLast` là những phép thay đổi thành viên. Khác biệt khi rỗng cũng là một phần hợp đồng, không chỉ cách đặt tên. [Java 17: SortedSet.first và last](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SortedSet.html#first()).

Một bộ duyệt hết phần tử không trả `null` khi gọi `next()`. Nó ném `NoSuchElementException`. Dùng `hasNext()` để biết còn phần tử trước khi gọi tiếp.

Đừng gộp tất cả các thao tác trên thành “lấy đầu/cuối”. Khi xem lại một đoạn mã, hãy xác định rõ giá trị được trả về là phần tử, khung nhìn hay bộ duyệt, rồi mới xét tác dụng lên dữ liệu.

## 4. pollFirst và pollLast vừa trả phần tử vừa xóa nó

Từ trạng thái ban đầu:

~~~text
[10, 20, 30, 40]
~~~

thực hiện lần lượt:

~~~text
pollFirst() → trả 10; tập còn [20, 30, 40]
pollLast()  → trả 40; tập còn [20, 30]
~~~

Mỗi lời gọi thành công loại một thành viên khỏi tập. Không cần gọi tiếp `remove` cho chính phần tử vừa được trả về.

Khi tập rỗng, cả hai trả `null`. Chúng không chờ đến khi có dữ liệu mới, cũng không tự nạp thêm dữ liệu từ nơi khác. Nếu chương trình cần chờ công việc mới đến, đó là một yêu cầu khác với thao tác trên `TreeSet` của bài.

Không dùng `first()` trong một vòng lặp với kỳ vọng mỗi lần đọc sẽ bỏ phần tử cũ. Nếu tập không thay đổi, `first()` tiếp tục trả cùng phần tử đầu.

Cũng không hiểu `pollFirst` là phần tử được thêm sớm nhất. `TreeSet` tổ chức theo thứ tự so sánh, nên thứ tự xử lý bằng `pollFirst` đi theo quy tắc đó. Nếu cần thứ tự đến trước xử lý trước, phải chọn một mô hình phù hợp với thứ tự sự kiện.

Một hệ quả quan trọng khi xử lý công việc: sau khi `pollFirst` trả về, phần tử đã rời tập. Nếu đoạn xử lý tiếp theo thất bại, tập không tự khôi phục nó. Có cần đưa lại hay ghi nhận trạng thái xử lý là quyết định của mã ứng dụng, không phải tác dụng mặc định của `poll`.

## 5. descendingSet là một khung nhìn, không phải bản sao

Từ tập `base = [10, 20, 30]` theo thứ tự tự nhiên:

~~~java
NavigableSet<Integer> descending = base.descendingSet();
~~~

cho khung nhìn có thứ tự duyệt `[30, 20, 10]`.

Có thể hình dung:

~~~text
cùng các thành viên: 10, 20, 30

base:        10 → 20 → 30
descending:  30 → 20 → 10
~~~

Hai dòng là hai hướng nhìn trên dữ liệu được chia sẻ. Không có bước đảo vĩnh viễn quy tắc của `base`. Sau khi tạo khung nhìn, duyệt `base` vẫn cho `10, 20, 30`.

Thêm hoặc xóa qua một phía có thể quan sát ở phía kia:

~~~text
descending.add(25)
base        → [10, 20, 25, 30]
descending  → [30, 25, 20, 10]
~~~

Sau đó thêm `40` qua `base`, khung nhìn đảo sẽ thấy `[40, 30, 25, 20, 10]` khi được duyệt lại.

Việc tạo khung nhìn không nhân bản mọi phần tử và không làm dữ liệu độc lập. Nếu truyền `descending` cho một hàm có thể xóa thành viên, hàm ấy cũng có thể làm thay đổi tập gốc. Đây là thông tin quan trọng trong hợp đồng của hàm, kể cả khi tên biến chỉ mang ý nghĩa “dữ liệu để hiển thị”.

Theo API, thứ tự của khung nhìn tương đương đảo quy tắc so sánh của nguồn. Tạo khung nhìn đảo lần nữa cho một khung nhìn về cơ bản tương đương tập ban đầu; không cần giả định hai biến có cùng tham chiếu đối tượng. [Java 17: TreeSet.descendingSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html#descendingSet()).

## 6. Hai đầu đổi vai khi nhìn theo chiều ngược

Giả sử `base` dùng thứ tự tự nhiên và hiện có:

~~~text
base        = [10, 20, 25, 30, 40]
descending  = [40, 30, 25, 20, 10]
~~~

Lúc này:

| Lời gọi | Thành viên bị xóa | Tương ứng trên tập gốc |
| --- | --- | --- |
| `descending.pollFirst()` | `40` | Lấy cuối của `base` |
| `descending.pollLast()` | `10` | Lấy đầu của `base` |

Các hàng mô tả quan hệ hai đầu; nếu chạy liên tiếp thì mỗi lời gọi thấy trạng thái sau lần trước.

Không phải chỉ chuỗi in ra bị đảo. Các thao tác có hướng của khung nhìn cũng được hiểu theo chiều đảo. Vì thế, `descending.first()` là `base.last()` khi tập không rỗng; `descending.last()` là `base.first()`.

Với cùng một trạng thái và cùng phạm vi thành viên, có thể dùng quy tắc nhớ:

~~~text
đầu của khung nhìn đảo  ↔ cuối của nguồn
cuối của khung nhìn đảo ↔ đầu của nguồn
~~~

Nếu nguồn là một vùng giới hạn của tập lớn hơn, “nguồn” ở đây là chính vùng đó. Phần tử cuối của vùng chưa chắc là phần tử cuối của toàn bộ tập lớn.

Tạo `descending` không thay ý nghĩa của `base.pollFirst()`. Lời gọi trên `base` vẫn dùng chiều của `base`; lời gọi trên `descending` dùng chiều của khung nhìn.

## 7. descendingIterator chỉ tạo một lượt duyệt ngược

Nếu chỉ cần đi qua phần tử theo chiều ngược, có thể dùng:

~~~java
Iterator<Integer> iterator = values.descendingIterator();
while (iterator.hasNext()) {
    Integer value = iterator.next();
    System.out.println(value);
}
~~~

Đoạn minh họa giả sử `values` là một `NavigableSet<Integer>`. `hasNext` hỏi còn phần tử; `next` lấy phần tử kế tiếp trong lượt duyệt. Không có lệnh xóa trong đoạn này.

Với `values = [1, 2, 3, 4]` tự nhiên, lượt duyệt cho `4, 3, 2, 1` nhưng tập vẫn giữ đủ bốn phần tử.

`descendingIterator()` tương đương về tác dụng duyệt với `descendingSet().iterator()`. Chọn cách thứ nhất khi chỉ cần một bộ duyệt; chọn khung nhìn khi cần tiếp tục dùng các phép tập hợp theo chiều đảo.

Tên “descending iterator” không biến kiểu trả về thành `ListIterator`. Bạn vẫn gọi `next()` để tiến qua lượt duyệt ngược đã chọn, không gọi `previous()`, không thêm phần tử vào một vị trí danh sách và không dùng chỉ số.

Bộ duyệt là trạng thái của **một lượt đi qua**. Sau khi đã đọc hết, muốn đọc lại phải tạo bộ duyệt mới. Gọi `hasNext` không tự quay lại đầu, còn gọi `next` sau điểm cuối ném lỗi.

## 8. Xóa trong lúc duyệt bằng chính iterator

Bộ duyệt của `TreeSet` hỗ trợ `remove()`. Phương thức này không nhận một giá trị để tìm; nó xóa phần tử cuối cùng mà chính bộ duyệt vừa trả về bằng `next()`.

Ví dụ lọc các số chẵn trong lượt duyệt ngược:

~~~java
Iterator<Integer> iterator = values.descendingIterator();
while (iterator.hasNext()) {
    int value = iterator.next();
    if (value % 2 == 0) {
        iterator.remove();
    }
}
~~~

Đoạn này được kiểm chứng trong chương trình đầy đủ với tập `[1, 2, 3, 4]`. Nó đi qua `4, 3, 2, 1` và cuối cùng giữ `[1, 3]`.

Thứ tự duyệt ngược không đảo điều kiện số chẵn. Nó chỉ thay trình tự các phần tử được đưa vào điều kiện.

Quy tắc trạng thái của `Iterator.remove`:

- Phải có một lần `next` trả phần tử trước đó.
- Sau mỗi lần `next`, chỉ được `remove` một lần.
- Gọi trước `next` hoặc gọi lần hai cho cùng phần tử dẫn đến `IllegalStateException` trong bộ duyệt của ví dụ.
- `remove` là thao tác tùy chọn ở interface `Iterator`; đừng mặc định mọi bộ duyệt của mọi cấu trúc đều hỗ trợ nó.

Đừng thay `iterator.remove()` bằng `values.remove(value)` hoặc `values.pollLast()` trong chính vòng lặp ấy rồi tiếp tục dùng bộ duyệt cũ. Bạn đang thay đổi dữ liệu ngoài đường cập nhật mà bộ duyệt đang theo dõi. [Java 17: Iterator.remove](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html#remove()).

## 9. Chương trình đầy đủ dùng Java 17

Lưu thành `NavigableSetEndsDemo.java`. Chương trình tách dữ liệu của từng nhóm ví dụ để việc xóa ở nhóm này không làm nhầm kết quả ở nhóm khác.

`readAll` chỉ tiêu thụ một bộ duyệt và ghi kết quả vào danh sách. `drainFirst` lấy hết thành viên bằng `pollFirst` và làm rỗng tập được truyền vào. Hai hàm có chủ đích khác nhau.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.Iterator;
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

public class NavigableSetEndsDemo {
    static <E> List<E> readAll(Iterator<E> iterator) {
        List<E> values = new ArrayList<>();
        while (iterator.hasNext()) {
            values.add(iterator.next());
        }
        return values;
    }

    static <E> List<E> drainFirst(NavigableSet<E> set) {
        List<E> removed = new ArrayList<>();
        while (!set.isEmpty()) {
            removed.add(set.pollFirst());
        }
        return removed;
    }

    public static void main(String[] args) {
        NavigableSet<Integer> ends = new TreeSet<>(List.of(40, 10, 30, 20));
        System.out.println("ends initial=" + ends);
        System.out.println("read first/last=" + ends.first() + "/" + ends.last());
        System.out.println("after read=" + ends);
        System.out.println("pollFirst=" + ends.pollFirst());
        System.out.println("pollLast=" + ends.pollLast());
        System.out.println("ends remaining=" + ends);
        System.out.println("drained=" + drainFirst(ends));
        System.out.println("ends empty=" + ends.isEmpty());
        System.out.println("empty pollFirst=" + ends.pollFirst());
        System.out.println("empty pollLast=" + ends.pollLast());

        NavigableSet<Integer> base = new TreeSet<>(List.of(10, 20, 30));
        NavigableSet<Integer> descending = base.descendingSet();
        System.out.println("base=" + base);
        System.out.println("descending=" + descending);
        System.out.println("descending first/last="
                + descending.first() + "/" + descending.last());
        descending.add(25);
        System.out.println("base after view add=" + base);
        base.add(40);
        System.out.println("view after base add=" + descending);
        System.out.println("view pollFirst=" + descending.pollFirst());
        System.out.println("base after view pollFirst=" + base);
        System.out.println("view pollLast=" + descending.pollLast());
        System.out.println("base after view pollLast=" + base);
        System.out.println("double reverse order="
                + new ArrayList<>(base).equals(
                        new ArrayList<>(descending.descendingSet())));

        NavigableSet<Integer> copy = new TreeSet<>(descending);
        base.add(35);
        System.out.println("base after later add=" + base);
        System.out.println("view after later add=" + descending);
        System.out.println("independent copy=" + copy);
        System.out.println("copy pollFirst=" + copy.pollFirst());
        System.out.println("base after copy poll=" + base);

        NavigableSet<Integer> iteration = new TreeSet<>(List.of(1, 2, 3, 4));
        System.out.println("descending traversal=" + readAll(iteration.descendingIterator()));
        System.out.println("after traversal=" + iteration);
        Iterator<Integer> iterator = iteration.descendingIterator();
        try {
            iterator.remove();
        } catch (IllegalStateException exception) {
            System.out.println("remove before next=" + exception.getClass().getSimpleName());
        }
        List<Integer> visited = new ArrayList<>();
        while (iterator.hasNext()) {
            int value = iterator.next();
            visited.add(value);
            if (value % 2 == 0) {
                iterator.remove();
            }
        }
        System.out.println("visited while filtering=" + visited);
        System.out.println("after iterator remove=" + iteration);
        try {
            iterator.next();
        } catch (java.util.NoSuchElementException exception) {
            System.out.println("next after end=" + exception.getClass().getSimpleName());
        }

        NavigableSet<Integer> custom = new TreeSet<>(Comparator.reverseOrder());
        custom.addAll(List.of(8, 2, 5));
        System.out.println("custom order=" + custom);
        System.out.println("custom descending=" + custom.descendingSet());
        System.out.println("custom descending iterator="
                + readAll(custom.descendingIterator()));
        System.out.println("custom view pollFirst=" + custom.descendingSet().pollFirst());
        System.out.println("custom after view poll=" + custom);
        System.out.println("custom pollFirst=" + custom.pollFirst());
        System.out.println("custom remaining=" + custom);

        NavigableSet<Integer> all = new TreeSet<>(List.of(1, 2, 3, 4, 5));
        NavigableSet<Integer> range = all.subSet(2, true, 5, false);
        NavigableSet<Integer> reverseRange = range.descendingSet();
        System.out.println("reverse range=" + reverseRange);
        System.out.println("range pollFirst=" + reverseRange.pollFirst());
        System.out.println("all after range poll=" + all);
        try {
            reverseRange.add(5);
        } catch (IllegalArgumentException exception) {
            System.out.println("outside range=" + exception.getClass().getSimpleName());
        }

        NavigableSet<String> nullable =
                new TreeSet<>(Comparator.nullsFirst(Comparator.naturalOrder()));
        nullable.addAll(Arrays.asList(null, "b", "a"));
        System.out.println("nullable initial=" + nullable);
        System.out.println("nullable first poll=" + nullable.pollFirst());
        System.out.println("empty after null poll=" + nullable.isEmpty());
        System.out.println("nullable remaining=" + nullable);
        System.out.println("nullable drained=" + drainFirst(nullable));
        System.out.println("nullable empty poll=" + nullable.pollFirst());
        nullable.addAll(Arrays.asList(null, "b", "a"));
        System.out.println("nullable full drain=" + drainFirst(nullable));
        System.out.println("nullable finally empty=" + nullable.isEmpty());
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 NavigableSetEndsDemo.java
java NavigableSetEndsDemo
~~~

Dùng JDK 17 trở lên. `--release 17` yêu cầu kiểm tra mã và API theo Java 17. Tên tệp phải khớp tên lớp `public`.

Kết quả chuẩn:

~~~text
ends initial=[10, 20, 30, 40]
read first/last=10/40
after read=[10, 20, 30, 40]
pollFirst=10
pollLast=40
ends remaining=[20, 30]
drained=[20, 30]
ends empty=true
empty pollFirst=null
empty pollLast=null
base=[10, 20, 30]
descending=[30, 20, 10]
descending first/last=30/10
base after view add=[10, 20, 25, 30]
view after base add=[40, 30, 25, 20, 10]
view pollFirst=40
base after view pollFirst=[10, 20, 25, 30]
view pollLast=10
base after view pollLast=[20, 25, 30]
double reverse order=true
base after later add=[20, 25, 30, 35]
view after later add=[35, 30, 25, 20]
independent copy=[30, 25, 20]
copy pollFirst=30
base after copy poll=[20, 25, 30, 35]
descending traversal=[4, 3, 2, 1]
after traversal=[1, 2, 3, 4]
remove before next=IllegalStateException
visited while filtering=[4, 3, 2, 1]
after iterator remove=[1, 3]
next after end=NoSuchElementException
custom order=[8, 5, 2]
custom descending=[2, 5, 8]
custom descending iterator=[2, 5, 8]
custom view pollFirst=2
custom after view poll=[8, 5]
custom pollFirst=8
custom remaining=[5]
reverse range=[4, 3, 2]
range pollFirst=4
all after range poll=[1, 2, 3, 5]
outside range=IllegalArgumentException
nullable initial=[null, a, b]
nullable first poll=null
empty after null poll=false
nullable remaining=[a, b]
nullable drained=[a, b]
nullable empty poll=null
nullable full drain=[null, a, b]
nullable finally empty=true
~~~

## 10. Đọc kết quả theo tác dụng lên dữ liệu

### 10.1. Đọc đầu/cuối khác với lấy ra

`read first/last=10/40` đi cùng `after read=[10, 20, 30, 40]`: hai phép đọc không xóa.

Sau `pollFirst=10` và `pollLast=40`, tập chỉ còn `[20, 30]`. Hàm `drainFirst` trả danh sách `[20, 30]` và tập trở thành rỗng. Hai lần `poll` cuối trả `null` vì không còn thành viên.

Danh sách được hàm `drainFirst` trả về là dữ liệu đã lấy ra, không phải một khung nhìn tiếp tục thay đổi theo tập vừa bị làm rỗng.

### 10.2. Khung nhìn dùng chung thành viên

`base after view add=[10, 20, 25, 30]` cho thấy thêm qua `descending` có tác dụng lên `base`.

`view after base add=[40, 30, 25, 20, 10]` cho thấy chiều ngược lại: thêm 40 qua `base` xuất hiện khi đọc khung nhìn đảo. Đây là đọc lại sau thay đổi, không phải tiếp tục một bộ duyệt cũ đang hoạt động.

Hai lời gọi `poll` qua khung nhìn lần lượt xóa 40 và 10 khỏi tập gốc. Khác tên biến không tạo hai kho thành viên độc lập.

### 10.3. Đảo hai lần được kiểm tra bằng trình tự

`double reverse order=true` được tính bằng cách chuyển hai phía thành `ArrayList` rồi so sánh. Cách này kiểm tra trình tự, không chỉ cùng thành viên.

Nếu chỉ dùng `base.equals(descending)`, kết quả có thể đúng vì `Set.equals` không dùng thứ tự duyệt. Phép bằng nhau của tập không phải bằng chứng rằng hai phía đang có cùng chiều đi qua dữ liệu.

### 10.4. Bộ duyệt đọc không làm mất phần tử

`descending traversal=[4, 3, 2, 1]` đi cùng `after traversal=[1, 2, 3, 4]` xác nhận chỉ đọc thì tập không bị rút bớt.

Trong lượt lọc kế tiếp, `visited while filtering` vẫn chứa cả bốn số theo chiều ngược. Chỉ số 4 và số 2 bị xóa qua `iterator.remove`, để lại `[1, 3]`.

Lỗi `remove before next` và `next after end` là hai lỗi trạng thái khác nhau: chưa có phần tử hợp lệ để xóa, và không còn phần tử để đọc.

## 11. Comparator đảo có thể làm descending trở thành tăng dần về số học

Chương trình tạo:

~~~java
NavigableSet<Integer> custom =
        new TreeSet<>(Comparator.reverseOrder());
~~~

Với dữ liệu `8, 2, 5`, thứ tự của tập gốc là:

~~~text
custom             = [8, 5, 2]
custom.descendingSet() = [2, 5, 8]
~~~

“Descending” nghĩa là ngược **thứ tự hiện tại của nguồn**, không phải lệnh bắt buộc in số lớn trước số nhỏ.

Do đó:

~~~text
custom.descendingSet().pollFirst() → trả 2
custom sau đó                     → [8, 5]

custom.pollFirst()                → trả 8
custom sau đó                     → [5]
~~~

Cùng tên `pollFirst` nhưng hai đối tượng nhận lời gọi có hai hướng khác nhau. Nếu chỉ nhớ “pollFirst lấy số nhỏ nhất” sẽ dự đoán sai cả hai lời gọi trên.

Khi tập chứa đối tượng nghiệp vụ, thay “số lớn/nhỏ” bằng quy tắc của bộ so sánh: điểm giảm, thời gian tăng hay một chuỗi tiêu chí. Đọc chính xác quy tắc nguồn rồi đảo hướng để hiểu khung nhìn.

Đảo thứ tự không thay đổi những cặp phần tử mà bộ so sánh xem là tương đương. `descendingSet` vẫn là một tập trên cùng thành viên; nó không phục hồi các bản ghi đã bị coi là trùng lúc thêm.

## 12. Bản sao độc lập khác với khung nhìn đảo

Nếu cần thay đổi dữ liệu theo chiều ngược mà không làm biến đổi thành viên của nguồn, hãy tạo bản sao thật sự với quy tắc mong muốn.

Chương trình dùng:

~~~java
NavigableSet<Integer> copy = new TreeSet<>(descending);
~~~

Ở đây `descending` có kiểu `NavigableSet`, cũng là một `SortedSet`. Hàm khởi tạo nhận `SortedSet` giữ thứ tự của nguồn. Vì vậy, bản sao có trình tự `[30, 25, 20]` tại thời điểm sao chép.

Sau đó `base.add(35)`:

~~~text
base        = [20, 25, 30, 35]
descending  = [35, 30, 25, 20]
copy        = [30, 25, 20]
~~~

Khung nhìn thấy thành viên mới; bản sao không nhận nó. Gọi `copy.pollFirst()` trả 30 và không xóa 30 của `base`.

Tuy nhiên, đây là độc lập về cấu trúc chứa thành viên, không phải sao chép sâu các đối tượng. Nếu phần tử là đối tượng có thể sửa, hai tập có thể vẫn giữ tham chiếu tới cùng đối tượng. Trong chương trình, `Integer` là giá trị bất biến nên không có thao tác sửa nội dung phần tử gây nhiễu.

Cũng cần đọc đúng hàm khởi tạo được chọn. Một nguồn được khai báo chỉ là `Collection` có thể chọn hàm tạo theo thứ tự tự nhiên thay vì giữ quy tắc đảo. Khi thứ tự của bản sao quan trọng, truyền rõ quy tắc hoặc dùng đúng kiểu nguồn cho hàm khởi tạo nhận `SortedSet`. [Java 17: TreeSet, các hàm khởi tạo](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html).

## 13. Khung nhìn đảo của một vùng chỉ tác động trong vùng

Trong chương trình:

~~~java
NavigableSet<Integer> all = new TreeSet<>(List.of(1, 2, 3, 4, 5));
NavigableSet<Integer> range = all.subSet(2, true, 5, false);
NavigableSet<Integer> reverseRange = range.descendingSet();
~~~

Vùng `range` chứa `2, 3, 4`: tính biên 2, không tính biên 5. Khung nhìn đảo là `[4, 3, 2]`.

`reverseRange.pollFirst()` lấy 4, không phải 5, vì 5 ở ngoài phạm vi thành viên của vùng. Tập lớn trở thành `[1, 2, 3, 5]`; các thành viên ngoài vùng vẫn còn.

Đảo hướng không xóa giới hạn. `reverseRange.add(5)` vẫn không hợp lệ và ném `IllegalArgumentException`. Việc 5 đang thuộc tập lớn không khiến nó thuộc vùng được truyền vào.

Điều này quan trọng khi viết hàm nhận `NavigableSet` làm tham số. Hàm có thể đang nhận toàn bộ tập hoặc chỉ một khung nhìn giới hạn. “Làm rỗng tập được truyền vào” qua các lần `pollFirst` sẽ xóa hết phần đang nhìn thấy, không nhất thiết xóa hết mọi thành viên của tập lớn ban đầu.

Ngược lại, nếu phần được truyền vào đúng là khung nhìn dùng chung, các phần tử bị lấy ra vẫn biến mất khỏi cấu trúc nguồn. Phạm vi hẹp hơn không đồng nghĩa độc lập dữ liệu.

## 14. null có hai nghĩa khi poll trả về

Tập theo thứ tự tự nhiên trong phần lớn ví dụ không cho phép phần tử `null`. Với mô hình như vậy, nhận `null` từ `pollFirst` hoặc `pollLast` có thể dùng làm dấu hiệu không còn phần tử.

Nhưng `TreeSet` có thể nhận `null` nếu được cung cấp bộ so sánh phù hợp. Phần cuối chương trình dùng `Comparator.nullsFirst(Comparator.naturalOrder())`, tạo thứ tự `[null, a, b]`.

Lời gọi đầu:

~~~text
nullable.pollFirst() → null
nullable.isEmpty()   → false
nullable            → [a, b]
~~~

đã lấy ra **một thành viên thật mang giá trị null**. Nó không có nghĩa tập ban đầu rỗng. Sau khi lấy hết `a, b`, lần `pollFirst` tiếp theo cũng trả `null`, nhưng lần này tập thực sự không còn gì.

Bộ bao `nullsFirst` quy định cách so sánh `null` với các phần tử khác; nó không thay hợp đồng giá trị trả về của `poll`. [Java 17: Comparator.nullsFirst](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html#nullsFirst(java.util.Comparator)).

Vì vậy, mẫu sau chỉ thích hợp khi hợp đồng dữ liệu loại `null`:

~~~java
// Minh họa: chỉ dùng khi null không thể là một thành viên.
Integer value;
while ((value = values.pollFirst()) != null) {
    System.out.println(value);
}
~~~

Nếu tập có `null` ở đầu, vòng lặp dừng sau khi đã lấy nó ra và bỏ lại các thành viên khác chưa xử lý.

Đừng gán ngay kết quả có thể `null` vào `int`. Việc tự mở gói từ `Integer` bằng `null` gây `NullPointerException` trước khi bạn có thể xử lý dấu hiệu rỗng.

## 15. Lấy hết dữ liệu cần chọn điều kiện dừng đúng

Hàm của chương trình:

~~~java
static <E> List<E> drainFirst(NavigableSet<E> set) {
    List<E> removed = new ArrayList<>();
    while (!set.isEmpty()) {
        removed.add(set.pollFirst());
    }
    return removed;
}
~~~

là đoạn trích từ mã đầy đủ. Trong điều kiện một luồng thao tác và không có mã khác xen vào sửa tập, nó xử lý được cả thành viên `null` vì điều kiện dừng dựa vào sự rỗng, không dựa vào giá trị phần tử vừa lấy.

Nếu truyền tập gốc theo thứ tự tự nhiên, danh sách trả về theo chiều tự nhiên. Nếu truyền khung nhìn đảo, danh sách trả về theo chiều đảo và các thành viên tương ứng bị xóa khỏi nguồn.

Dòng `nullable full drain=[null, a, b]` kiểm chứng riêng việc truyền một tập còn chứa null vào hàm: cả null lẫn hai chuỗi đều được lấy ra, và tập rỗng sau đó.

Hàm tạo danh sách chứa toàn bộ kết quả để dễ kiểm chứng. Nếu mục tiêu là xử lý rồi bỏ từng phần tử, ứng dụng có thể xử lý trực tiếp thay vì tích lũy danh sách; cần vẫn xác định rõ chính sách lỗi sau khi phần tử đã bị lấy ra.

Vòng `isEmpty` rồi `pollFirst` không phải một cặp thao tác tự nhiên nguyên tử. Với dữ liệu chia sẻ giữa nhiều luồng, một tác nhân khác có thể thay đổi trạng thái giữa hai lời gọi. Đừng chuyển nguyên xi suy luận một luồng của hàm này thành bảo đảm cạnh tranh cho `TreeSet`.

`TreeSet` không có đồng bộ hóa sẵn. Nếu cần chia sẻ và sửa từ nhiều luồng, phải thiết kế cách phối hợp hoặc chọn cách triển khai đáp ứng hợp đồng cạnh tranh mong muốn, đồng thời xem lại cách xử lý `null` và bộ duyệt của cách triển khai ấy.

## 16. Khung nhìn thấy cập nhật không có nghĩa iterator cũ luôn dùng tiếp được

Hai ý sau khác nhau:

- Khung nhìn dùng chung dữ liệu, nên một lượt đọc mới thấy các thay đổi hợp lệ ở nguồn.
- Bộ duyệt đã được tạo có trạng thái riêng của lượt duyệt và có quy tắc về thay đổi trong lúc đi qua dữ liệu.

Nếu đang dùng bộ duyệt trên `base` mà gọi `descending.pollFirst()`, bạn vẫn đang xóa khỏi cùng dữ liệu nền ngoài chính bộ duyệt đó. Đổi chiều hoặc đổi tên biến không tạo ngoại lệ cho quy tắc sửa dữ liệu khi duyệt.

Bộ duyệt của `TreeSet` có cơ chế báo lỗi sớm khi phát hiện thay đổi cấu trúc ngoài thao tác `remove` của chính nó. `ConcurrentModificationException` hỗ trợ phát hiện lỗi theo khả năng, không được dùng làm cơ chế đồng bộ hay làm điều kiện đúng đắn của chương trình. Không thấy ngoại lệ trong một thử nghiệm không chứng minh cách sửa ấy hợp lệ. [Java 17: TreeSet, chính sách bộ duyệt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html).

Chọn một đường cập nhật cho mỗi lượt làm việc:

- Nếu chỉ đọc, dùng bộ duyệt và không sửa dữ liệu nền trong lượt ấy.
- Nếu lọc khi đang duyệt trên `TreeSet`, dùng `remove` của chính bộ duyệt theo đúng trạng thái.
- Nếu lấy hết phần tử để xử lý, có thể lặp bằng `pollFirst` hoặc `pollLast` mà không giữ một bộ duyệt cũ đang hoạt động.
- Nếu cần lập kế hoạch rồi sửa, kết thúc lượt duyệt trước khi áp dụng thay đổi, hoặc dùng một bản sao độc lập theo yêu cầu.

Các lựa chọn này làm rõ quan hệ giữa cách duyệt và tác dụng lên thành viên, thay vì dựa vào việc mã có tình cờ chạy hết hay không.

## 17. Chọn API theo công việc cần làm

| Công việc | Cách dùng phù hợp trong phạm vi bài |
| --- | --- |
| Xem phần tử đầu/cuối nhưng giữ nó | `first` / `last`, có xử lý trường hợp rỗng |
| Lấy và xóa một phần tử đầu/cuối | `pollFirst` / `pollLast` |
| Chỉ đọc theo chiều ngược | `descendingIterator` hoặc vòng lặp trên `descendingSet` |
| Cần nhiều phép tập hợp theo chiều ngược | Giữ một biến khung nhìn từ `descendingSet` |
| Lọc có điều kiện trong một lượt duyệt ngược | `descendingIterator` và `iterator.remove` |
| Lấy hết từ phía cuối của nguồn | Có thể dùng `pollLast` trên nguồn hoặc `pollFirst` trên khung nhìn đảo |
| Sửa độc lập với thành viên của nguồn | Tạo bản sao thật, xác định rõ quy tắc thứ tự |
| Chỉ xử lý một khoảng | Tạo vùng, rồi chọn chiều nhìn; thay đổi vẫn truyền về nguồn |

Không chọn `poll` chỉ vì tên có vẻ tiện hơn `first` nếu yêu cầu là đọc. Cũng không tạo một bản sao chỉ để đổi chiều nếu khung nhìn hoặc bộ duyệt đã đáp ứng đúng hợp đồng chia sẻ dữ liệu mà bạn cần.

Về chi phí, `descendingSet` không tự tạo một kho chứa độc lập của toàn bộ thành viên. Một bản sao thật phải lưu cấu trúc thành viên riêng. Duyệt toàn bộ hoặc tạo danh sách chứa toàn bộ kết quả phải đi qua các phần tử tương ứng.

`TreeSet` công bố chi phí `O(log n)` cho các phép cơ bản `add`, `remove` và `contains`. Không suy từ việc lấy hai đầu hay có khung nhìn rằng mọi cách triển khai `NavigableSet` đều có cùng chi phí, cùng chính sách bộ duyệt hoặc cùng khả năng chia sẻ giữa các luồng.

Vẫn nhớ đây là tập hợp: những lần thêm được xem là trùng theo phép so sánh không tạo nhiều thành viên để sau này `poll` từng lần. Nếu bạn cần lưu mọi công việc cùng một mức ưu tiên, tiêu chí duy nhất hoặc cấu trúc lưu phải phản ánh yêu cầu đó.

## 18. Thực hành có lời giải

### Bài 1: đọc và lấy ra

Tập tự nhiên ban đầu là `[3, 6, 9]`. Gọi `first()` rồi `pollLast()`. Hai giá trị trả về và tập cuối là gì?

**Lời giải:** `first` trả 3 và không xóa. `pollLast` trả 9 và xóa nó. Tập cuối là `[3, 6]`.

### Bài 2: hai đầu của khung nhìn đảo

Tập gốc tự nhiên là `[2, 4, 8]`. Tạo `reverse = base.descendingSet()`, rồi gọi `reverse.pollFirst()` và `reverse.pollLast()`.

**Lời giải:** Khung nhìn ban đầu là `[8, 4, 2]`. Lần đầu trả 8 và xóa cuối của nguồn. Lần sau trả 2 và xóa đầu của nguồn. Cả tập gốc lẫn khung nhìn còn cùng thành viên 4.

### Bài 3: iterator có tự xóa không?

Bạn duyệt toàn bộ `descendingIterator` của tập `[1, 2, 3]` bằng `next` và không gọi `remove`. Tập còn những gì?

**Lời giải:** Vẫn còn `[1, 2, 3]`. Lượt đọc đi qua `3, 2, 1` nhưng không xóa. Một bộ duyệt đã hết cần được tạo mới nếu muốn đọc lại.

### Bài 4: xóa sai đường trong lúc duyệt

Trong vòng lặp bằng một iterator, bạn gọi `base.pollFirst()` rồi tiếp tục dùng iterator cũ. Có thể xem đó là an toàn vì poll không dùng một phần tử làm đối số không?

**Lời giải:** Không. Poll vẫn thay đổi thành viên của cùng dữ liệu nền ngoài bộ duyệt. Cần dùng đường cập nhật phù hợp: `iterator.remove` cho lọc trong lượt duyệt, hoặc một vòng poll riêng không giữ bộ duyệt cũ.

### Bài 5: tập nguồn đã có Comparator đảo

Tập nguồn dùng `Comparator.reverseOrder()` và chứa số 1, 5, 9. `source.pollFirst()` lấy số nào? `source.descendingSet().pollFirst()` trên trạng thái ban đầu lấy số nào?

**Lời giải:** Nguồn duyệt `[9, 5, 1]` nên `source.pollFirst` lấy 9. Khung nhìn đảo duyệt `[1, 5, 9]` nên lời gọi trên khung nhìn lấy 1. Hai câu trả lời được xét độc lập trên cùng trạng thái ban đầu.

### Bài 6: null không đồng nghĩa rỗng

Tập cho phép null có thứ tự `[null, a, b]`. Vòng lặp dừng khi `pollFirst() == null` có xử lý hết không?

**Lời giải:** Không. Lần đầu đã xóa thành viên null và điều kiện làm vòng lặp dừng, để lại a và b. Trong ví dụ một luồng, có thể kiểm tra `isEmpty` làm điều kiện dừng như hàm `drainFirst`.

### Bài 7: phạm vi vùng

Tập lớn là `[1, 2, 3, 4, 5]`. Vùng gồm từ 2 có tính đến trước 5. Đảo vùng rồi `pollFirst` có lấy 5 không?

**Lời giải:** Không. Vùng chỉ gồm `[2, 3, 4]`, nên khung nhìn đảo lấy 4. Số 5 vẫn ở ngoài vùng và ở lại trong tập lớn.

### Bài 8: bản sao hay khung nhìn?

Bạn cần nhận dữ liệu theo chiều ngược rồi xóa tùy ý mà không xóa các thành viên của nguồn. Chỉ gọi `descendingSet` đã đủ chưa?

**Lời giải:** Chưa. Đó là khung nhìn dùng chung dữ liệu. Cần bản sao thật với thứ tự thích hợp; vẫn phân biệt độc lập cấu trúc tập với sao chép sâu các đối tượng phần tử.

### Bài 9: trạng thái remove

Sau khi tạo descendingIterator, bạn gọi `remove` ngay mà chưa `next`. Hoặc đã `next` một lần rồi `remove` hai lần liên tiếp. Điều gì sai?

**Lời giải:** Chưa có phần tử do bộ duyệt trả về để xóa ở trường hợp đầu. Trường hợp sau xóa hai lần cho cùng một lần next. Bộ duyệt TreeSet trong bài báo `IllegalStateException` cho các lỗi trạng thái này.

### Bài 10: kiểm tra hai lần đảo

Bạn muốn xác nhận `s.descendingSet().descendingSet()` có cùng thứ tự duyệt như s. Chỉ so sánh bằng `Set.equals` có đủ không?

**Lời giải:** Không để chứng minh trình tự, vì phép bằng nhau của tập không xét thứ tự. Chương trình chuyển hai phía sang danh sách và so sánh trình tự. Cũng không cần yêu cầu hai biến trỏ đến cùng một đối tượng bằng `==`.

## 19. Tự kiểm tra khi áp dụng

Trước mỗi đoạn mã, xác định ba điều: đối tượng nhận lời gọi đang nhìn những thành viên nào, nó dùng chiều nào, và thao tác có xóa thành viên không.

Sau đó kiểm tra trường hợp rỗng và chính sách null. Nếu có bộ duyệt đang hoạt động, xác định đường cập nhật được phép thay vì sửa qua một tham chiếu khác rồi tiếp tục dùng nó.

Với cùng một kho thành viên, `descendingSet` chỉ đổi góc nhìn; `descendingIterator` chỉ chọn chiều của một lượt duyệt. Chỉ các phép thay đổi như `poll` hoặc `iterator.remove` mới thực sự rút thành viên ra trong những ví dụ này.
