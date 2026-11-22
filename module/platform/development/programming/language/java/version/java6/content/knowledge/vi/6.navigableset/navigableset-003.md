# first, last, pollFirst và pollLast trong NavigableSet

## 1. Đọc đầu mút hay lấy ra khỏi tập hợp?

`NavigableSet<E>` là một tập hợp có thứ tự, hỗ trợ tìm kiếm theo quan hệ thứ tự và thao tác ở hai đầu. Bốn phương thức trong bài phục vụ một câu hỏi thực tế: **cần xem phần tử đầu/cuối, hay cần lấy nó ra để xử lý?**

Ví dụ, một tập mã số đang có thứ tự `[10, 20, 30, 40]`:

- Xem mã ở đầu mà vẫn giữ nguyên dữ liệu: dùng `first()`.
- Xem mã ở cuối mà vẫn giữ nguyên dữ liệu: dùng `last()`.
- Lấy mã ở đầu và đồng thời bỏ nó khỏi tập hợp: dùng `pollFirst()`.
- Lấy mã ở cuối và đồng thời bỏ nó khỏi tập hợp: dùng `pollLast()`.

“Đầu” và “cuối” được xác định bởi **thứ tự của tập hợp hoặc khung nhìn đang dùng**, không phải thời điểm thêm phần tử.

`first()` và `last()` được kế thừa từ `SortedSet`; `pollFirst()` và `pollLast()` thuộc hợp đồng `NavigableSet`. Những phương thức này vẫn áp dụng trong Java hiện hành. Xem [SortedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html) và [NavigableSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableSet.html).

## 2. Bảng phân biệt cần nhớ

| Phương thức | Có phần tử | Có xóa phần tử? | Khi rỗng |
| --- | --- | --- | --- |
| `first()` | Trả phần tử đầu theo thứ tự hiện tại | Không | Ném `NoSuchElementException` |
| `last()` | Trả phần tử cuối theo thứ tự hiện tại | Không | Ném `NoSuchElementException` |
| `pollFirst()` | Trả phần tử đầu theo thứ tự hiện tại | Có | Trả `null` |
| `pollLast()` | Trả phần tử cuối theo thứ tự hiện tại | Có | Trả `null` |

Tất cả đều trả về kiểu `E`; khác biệt cốt lõi nằm ở tác động lên tập hợp và cách biểu diễn trạng thái rỗng. Bảng tuân theo hợp đồng tại [SortedSet.first/last](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html) và [NavigableSet.pollFirst/pollLast](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableSet.html).

Một cách chọn theo ý định:

- “Tập hợp phải có dữ liệu ở đây; tôi chỉ cần xem đầu mút”: `first` hoặc `last`.
- “Có dữ liệu thì lấy ra; hết dữ liệu là tình huống bình thường”: `pollFirst` hoặc `pollLast`.
- “Có thể rỗng nhưng chỉ muốn xem, không muốn xóa”: kiểm tra rỗng rồi đọc trong một ngữ cảnh truy cập được kiểm soát; không thay bằng `poll` vì sẽ làm thay đổi dữ liệu.

## 3. Thứ tự sắp xếp quyết định đầu và cuối

Với `TreeSet<Integer>` dùng thứ tự tự nhiên, số nhỏ đứng trước số lớn. Nếu thêm `40, 10, 30, 20`, `first()` trả 10 và `last()` trả 40.

Với `Comparator.reverseOrder()`, 40 đứng trước 30, rồi 20, 10. Lúc đó `first()` trả 40 và `last()` trả 10. Vì vậy không nên ghi nhớ “first luôn là số nhỏ nhất” mà thiếu điều kiện **theo thứ tự nào**.

Với đối tượng nghiệp vụ, comparator có thể sắp theo ngày hạn, mức ưu tiên hoặc khóa khác. “Đầu” khi đó là đối tượng đứng đầu theo quy tắc ấy. Cần thiết kế quy tắc so sánh trước khi dùng các phương thức đầu mút để quyết định công việc nào được xử lý tiếp. Xem [vai trò của Comparator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Comparator.html).

Đây cũng là một `Set`: không phải danh sách giữ tất cả bản sao hay hàng đợi theo thời gian đến. Khi hai giá trị được comparator xem là bằng nhau, `TreeSet` chỉ giữ một đại diện. Nếu các công việc khác nhau cùng mức ưu tiên đều phải được giữ, quy tắc so sánh cần phân biệt chúng thích hợp, đồng thời bảo đảm sự nhất quán với `equals`. Xem [quy tắc thứ tự và tính duy nhất của TreeSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html).

## 4. Ví dụ đầy đủ chạy trên Java 17+

Lưu tệp `NavigableSetEndsDemo.java`:

```java
import java.util.Comparator;
import java.util.List;
import java.util.NavigableSet;
import java.util.NoSuchElementException;
import java.util.TreeSet;

public class NavigableSetEndsDemo {
    private static void showEmptyRead(NavigableSet<Integer> set,
                                      boolean readFirst) {
        String name = readFirst ? "first" : "last";
        try {
            Integer value = readFirst ? set.first() : set.last();
            System.out.println("empty " + name + "=" + value);
        } catch (NoSuchElementException ex) {
            System.out.println("empty " + name + "=NoSuchElementException");
        }
    }

    public static void main(String[] args) {
        NavigableSet<Integer> numbers =
                new TreeSet<>(List.of(40, 10, 30, 20, 20));

        System.out.println("initial=" + numbers);
        System.out.println("first=" + numbers.first());
        System.out.println("last=" + numbers.last());
        System.out.println("after reads=" + numbers);
        System.out.println("pollFirst=" + numbers.pollFirst());
        System.out.println("pollLast=" + numbers.pollLast());
        System.out.println("remaining=" + numbers);

        Integer value;
        while ((value = numbers.pollFirst()) != null) {
            System.out.println("drain=" + value);
        }
        System.out.println("empty pollFirst=" + numbers.pollFirst());
        System.out.println("empty pollLast=" + numbers.pollLast());
        showEmptyRead(numbers, true);
        showEmptyRead(numbers, false);

        NavigableSet<Integer> single = new TreeSet<>(List.of(7));
        System.out.println("single first/last="
                + single.first() + "/" + single.last());
        System.out.println("single size=" + single.size());
        System.out.println("single pollFirst=" + single.pollFirst());
        System.out.println("single pollLast=" + single.pollLast());

        NavigableSet<Integer> base = new TreeSet<>(List.of(10, 20, 30));
        NavigableSet<Integer> descending = base.descendingSet();
        System.out.println("descending=" + descending);
        System.out.println("descending first=" + descending.first());
        System.out.println("descending last=" + descending.last());
        System.out.println("descending pollFirst=" + descending.pollFirst());
        System.out.println("base after pollFirst=" + base);
        System.out.println("descending pollLast=" + descending.pollLast());
        System.out.println("base after pollLast=" + base);

        NavigableSet<Integer> reversed =
                new TreeSet<>(Comparator.reverseOrder());
        reversed.addAll(List.of(10, 20, 30));
        System.out.println("reverse comparator=" + reversed);
        System.out.println("reverse first/last="
                + reversed.first() + "/" + reversed.last());
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```shell
javac -encoding UTF-8 NavigableSetEndsDemo.java
java NavigableSetEndsDemo
```

Kết quả:

```text
initial=[10, 20, 30, 40]
first=10
last=40
after reads=[10, 20, 30, 40]
pollFirst=10
pollLast=40
remaining=[20, 30]
drain=20
drain=30
empty pollFirst=null
empty pollLast=null
empty first=NoSuchElementException
empty last=NoSuchElementException
single first/last=7/7
single size=1
single pollFirst=7
single pollLast=null
descending=[30, 20, 10]
descending first=30
descending last=10
descending pollFirst=30
base after pollFirst=[10, 20]
descending pollLast=10
base after pollLast=[20]
reverse comparator=[30, 20, 10]
reverse first/last=30/10
```

## 5. Đọc kết quả theo từng thay đổi trạng thái

### first và last chỉ quan sát

Sau hai lần đọc `first()`, `last()`, tập hợp vẫn là `[10, 20, 30, 40]`. Không có phần tử nào bị tiêu thụ.

Điều này hữu ích khi cần hiển thị hai đầu khoảng dữ liệu hoặc kiểm tra giới hạn hiện có. Gọi nhiều lần trong một chương trình đơn luồng không sửa tập hợp sẽ trả lại cùng đầu mút.

### pollFirst và pollLast có tác động

Sau `pollFirst()`, 10 được trả về và dữ liệu trở thành `[20, 30, 40]`. Tiếp tục `pollLast()` trả 40, dữ liệu còn `[20, 30]`.

Đừng gọi `pollFirst()` chỉ để in thử một giá trị nếu vẫn muốn giữ nguyên dữ liệu. Việc bỏ qua giá trị trả về không hủy tác động xóa.

### Khi chỉ có một phần tử

Với `[7]`, cả `first()` lẫn `last()` đều trả 7; kích thước vẫn bằng 1. Đây là **cùng một phần tử**, không phải hai vị trí chứa hai bản sao.

Sau `pollFirst()`, tập hợp rỗng; `pollLast()` tiếp theo trả `null`. Nếu đảo hai thao tác thì lần lấy cuối đầu tiên sẽ nhận 7, lần lấy đầu tiếp theo nhận `null`.

### Vòng lặp lấy đến khi rỗng

Chương trình dùng:

```java
Integer value;
while ((value = numbers.pollFirst()) != null) {
    System.out.println("drain=" + value);
}
```

Mỗi lượt lấy một phần tử rồi xử lý chính phần tử nhận được. Với tập số không chứa `null`, vòng lặp dừng sau khi đã lấy hết; khi kết thúc, dữ liệu ban đầu đã bị tiêu thụ.

Nếu muốn chỉ duyệt mà giữ nguyên dữ liệu, dùng vòng lặp duyệt thông thường. Không dùng vòng lặp trên như một cách “đọc danh sách”.

## 6. descendingSet làm đảo nghĩa đầu/cuối và chia sẻ dữ liệu

`base.descendingSet()` tạo một khung nhìn thứ tự ngược, không tạo bản sao độc lập. Trong ví dụ, `base` nhìn thấy `[10, 20, 30]`, còn `descending` nhìn thấy `[30, 20, 10]`.

Bởi vậy:

- `descending.first()` là 30.
- `descending.last()` là 10.
- `descending.pollFirst()` lấy 30 ra; `base` cũng mất 30.
- `descending.pollLast()` tiếp theo lấy 10 ra; `base` chỉ còn 20.

Khung nhìn này là nơi thao tác thực sự được gọi; phải xét thứ tự của nó khi đọc “first” và “last”. Hợp đồng khung nhìn ngược được mô tả tại [NavigableSet.descendingSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableSet.html).

Nếu cần thử lấy các đầu mút mà giữ nguyên tập gốc, hãy tạo bản sao có cùng thứ tự trước. Ví dụ minh họa, giả sử `source` là `NavigableSet<Integer>`:

```java
NavigableSet<Integer> copy = new TreeSet<>(source);
Integer removedFromCopy = copy.pollFirst();
// source khong bi thay doi boi thao tac tren copy.
```

Constructor nhận `SortedSet` của `TreeSet` giữ cùng thứ tự với nguồn. Đây là bản sao cấu trúc; các đối tượng phần tử có thể vẫn được dùng chung. Xem [các constructor TreeSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html).

## 7. Xử lý rỗng và null cho đúng

### Tránh tự động mở hộp trước khi kiểm tra

Đoạn sau có thể ném `NullPointerException` khi tập hợp rỗng:

```java
// numbers la NavigableSet<Integer>.
int value = numbers.pollFirst();
```

Nguyên nhân là `pollFirst()` trả về `Integer` có giá trị `null`, sau đó Java cố tự động mở hộp thành `int`. Hãy giữ kiểu tham chiếu để kiểm tra:

```java
Integer value = numbers.pollFirst();
if (value != null) {
    int actualNumber = value;
    // Xu ly actualNumber.
}
```

Không gán một số giả như `-1` để biểu diễn rỗng nếu `-1` cũng có thể là dữ liệu hợp lệ.

### Không mặc định mọi NavigableSet đều cấm null

Ví dụ trong bài dùng `TreeSet<Integer>` theo thứ tự tự nhiên và dữ liệu không có `null`. Một `TreeSet` được cấu hình bằng comparator chấp nhận `null` có thể có hành vi khác. API `NavigableSet` lưu ý sự nhập nhằng của giá trị trả về khi triển khai cho phép phần tử `null`. Xem [lưu ý về null](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableSet.html).

Nếu tập hợp cho phép `null`, vòng lặp “poll đến khi trả null” có thể dừng sau khi vừa lấy chính phần tử null, trong khi vẫn còn phần tử khác. Với thiết kế dùng `null` làm tín hiệu rỗng, hãy đặt rõ quy tắc dữ liệu không chứa null.

## 8. Những lỗi thường gặp khi áp dụng

### Coi first là phần tử thêm đầu tiên

`NavigableSet` dùng quy tắc sắp xếp. Muốn giữ thứ tự đến và phần tử trùng, cần cấu trúc phù hợp với yêu cầu ấy; đổi từ `first` sang `pollFirst` không thay đổi bản chất tập hợp.

### Tách “đọc rồi xóa” khi thực chất muốn lấy ra

Mã minh họa:

```java
Integer next = numbers.first();
numbers.remove(next);
```

Trong tình huống đơn luồng, dữ liệu không rỗng và không bị thay đổi xen giữa, đoạn này có thể đạt mục tiêu lấy đầu. Tuy nhiên nó diễn đạt ý định qua hai thao tác và phải xử lý rỗng riêng. Khi muốn lấy và xóa đầu mút với cách báo rỗng bằng null, `pollFirst()` trực tiếp hơn.

Không suy ra từ tên `poll` rằng mọi triển khai đều an toàn đa luồng. `TreeSet` không tự đồng bộ; nếu các luồng dùng chung và có luồng sửa dữ liệu, cần cơ chế phối hợp phù hợp. Kiểm tra `isEmpty()` rồi gọi `first()` cũng không biến hai lời gọi thành một thao tác nguyên tử. Xem [quy tắc đồng bộ TreeSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html).

### Lấy và xóa trong lúc vòng for-each đang duyệt

Không gọi `pollFirst()` hoặc `pollLast()` để sửa chính `TreeSet` ngay trong vòng for-each trên nó rồi mong iterator vẫn hợp lệ. Nếu mục tiêu là lấy lần lượt đến hết, dùng vòng lặp lấy phần tử như ví dụ; nếu xóa theo điều kiện trong quá trình duyệt, cần cơ chế phù hợp với iterator hoặc API xóa theo điều kiện.

### Quên quyền sửa dữ liệu

`first` và `last` là thao tác đọc. `pollFirst` và `pollLast` là thao tác sửa; không mặc định một tập hợp hay khung nhìn chỉ đọc sẽ hỗ trợ chúng. Cần kiểm tra hợp đồng của đối tượng cụ thể trước khi dùng thao tác xóa.

## 9. Tự kiểm tra và thực hành

1. Với tập thứ tự tự nhiên `[2, 5, 9]`, gọi `first()`, `pollLast()`, `last()` theo thứ tự. Giá trị trả về lần lượt là 2, 9, 5; tập cuối cùng là `[2, 5]`.
2. Với cùng dữ liệu nhưng dùng comparator đảo, tự dự đoán kết quả trước khi chạy. Hãy giải thích dựa trên vị trí trong thứ tự comparator, không chỉ dựa trên độ lớn của số.
3. Tạo một `descendingSet`, lấy hết bằng `pollFirst()`, rồi kiểm tra tập gốc. Giải thích vì sao tập gốc cũng rỗng.
4. Viết kiểm thử cho ba trường hợp: tập rỗng, tập một phần tử và tập nhiều phần tử. Với `first/last`, xác nhận dữ liệu không đổi; với `pollFirst/pollLast`, kiểm tra cả giá trị trả về lẫn nội dung còn lại.
5. Sửa chương trình để chỉ in các phần tử theo thứ tự mà không xóa chúng. Xác nhận kích thước trước và sau không đổi.
