# Biên đóng–mở, chính sách null và các view phạm vi

## 1. Một khoảng có thứ tự cần ba quyết định riêng

Giả sử ứng dụng giữ các mức ưu tiên duy nhất trong một TreeSet. Một số mức chưa xác định được biểu diễn bằng `null`. Ứng dụng cần lấy các mức từ 10 đến trước 30 và cho phép cập nhật trong vùng ấy.

Để thao tác đúng, cần trả lời ba câu hỏi khác nhau:

1. **Thứ tự và null:** comparator có chấp nhận `null` không, và nếu có thì đặt nó trước hay sau các giá trị khác?
2. **Biên đóng–mở:** giá trị tương đương mỗi mốc có được lấy vào khoảng không?
3. **Góc nhìn phạm vi:** kết quả là một view liên kết với dữ liệu gốc hay một container độc lập?

Chỉ biết “TreeSet có sắp xếp” chưa trả lời được các câu hỏi đó. Một comparator cho phép `null` không có nghĩa mọi view của Set đều cho phép thêm `null`. Một khoảng hiện không chứa `null` cũng chưa có nghĩa comparator cấm nó.

Trong bài, **view phạm vi** được gọi là **góc nhìn theo khoảng**: nó truy cập cùng dữ liệu nền nhưng có thêm giới hạn. Đây không phải một danh sách kết quả đã được sao chép.

Các quy tắc được dùng dựa trên [SortedSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SortedSet.html), [NavigableSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableSet.html) và các phương thức phạm vi của [TreeSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html).

Một cách đọc thống nhất là:

```text
phần tử có thể được so sánh hợp lệ
    + vị trí theo comparator
    + điều kiện của hai biên
    -> thuộc hoặc không thuộc khoảng
```

Sau khi xác định thành viên của khoảng, còn phải quyết định có muốn các thao tác qua nó làm thay đổi tập gốc hay không.

## 2. Đọc biên đóng–mở khi null có thể là một mốc

Bốn dạng khoảng của `NavigableSet` được xác định bằng hai cờ lấy biên. Điều kiện đều được xét theo **comparator của tập**:

| Dạng khoảng | Lời gọi |
|---|---|
| `[a, b]` | `subSet(a, true, b, true)` |
| `[a, b)` | `subSet(a, true, b, false)` |
| `(a, b]` | `subSet(a, false, b, true)` |
| `(a, b)` | `subSet(a, false, b, false)` |

Overload không có cờ dùng `headSet(b)` loại b, `tailSet(a)` lấy a và `subSet(a,b)` chọn `[a,b)`. “Lấy mốc” nghĩa là lấy một phần tử **so sánh bằng 0** với mốc, ngay cả khi mốc không nằm sẵn trong tập. Ví dụ trên `[0,10,20,30,40]`, khoảng `[15,35]` chứa `[20,30]`.

Với `nullsFirst`, mốc `null` đứng ở đầu quan hệ: `subSet(null, true, 30, false)` có thể chứa chính thành viên `null`, còn `subSet(null, false, 30, false)` loại nó. Đối với `nullsLast`, thứ tự giữa `null` và 30 đảo lại; không tự dùng `null` làm ký hiệu “không giới hạn”. Khi cần bỏ một phía giới hạn, hãy chọn `headSet` hoặc `tailSet` phù hợp.

Nếu hai mốc so sánh bằng 0, `[a,a]` có thể chứa một phần tử tương đương, còn ba dạng có ít nhất một đầu mở đều rỗng. Một view `[a,a]` rỗng ban đầu vẫn có thể tiếp nhận phần tử tại mốc sau này. Mốc đầu đứng sau mốc cuối theo comparator thì khoảng không hợp lệ, thường ném `IllegalArgumentException` trên `TreeSet`. Dùng cờ inclusive thay vì tự cộng 1 để nới biên, vì cách cộng không đúng tổng quát cho số, chuỗi hoặc thời gian.

## 3. Chương trình 1: kiểm tra đủ bốn dạng biên

Lưu tệp `RangeBoundaryMatrixDemo.java`:

```java
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

public class RangeBoundaryMatrixDemo {
    public static void main(String[] args) {
        NavigableSet<Integer> values =
                new TreeSet<>(List.of(0, 10, 20, 30, 40));

        System.out.println("values = " + values);
        System.out.println("[10, 30) = "
                + values.subSet(10, true, 30, false));
        System.out.println("[10, 30] = "
                + values.subSet(10, true, 30, true));
        System.out.println("(10, 30) = "
                + values.subSet(10, false, 30, false));
        System.out.println("(10, 30] = "
                + values.subSet(10, false, 30, true));
        System.out.println("default subSet = " + values.subSet(10, 30));
        System.out.println("absent boundaries = "
                + values.subSet(15, true, 35, true));
        System.out.println("[20, 20] = "
                + values.subSet(20, true, 20, true));
        System.out.println("[20, 20) = "
                + values.subSet(20, true, 20, false));
        System.out.println("(20, 20] = "
                + values.subSet(20, false, 20, true));
        System.out.println("(20, 20) = "
                + values.subSet(20, false, 20, false));
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 RangeBoundaryMatrixDemo.java
java RangeBoundaryMatrixDemo
```

Kết quả của lần chạy kiểm chứng:

```text
values = [0, 10, 20, 30, 40]
[10, 30) = [10, 20]
[10, 30] = [10, 20, 30]
(10, 30) = [20]
(10, 30] = [20, 30]
default subSet = [10, 20]
absent boundaries = [20, 30]
[20, 20] = [20]
[20, 20) = []
(20, 20] = []
(20, 20) = []
```

Các chương trình trong bài dùng ngôn ngữ và API có ở Java 17 trở lên, được biên dịch với `--release 17` và chạy kiểm chứng bằng Azul OpenJDK 24.0.2.

Với hai mốc 10 và 30, chỉ các thành viên đúng tại biên thay đổi khi bật hoặc tắt inclusive. Thành viên nằm hẳn bên trong như 20 vẫn được giữ trong cả bốn dạng.

Phần biên vắng mặt cho thấy đóng hay mở không bắt buộc mốc phải tồn tại. Phần hai mốc cùng là 20 giúp tránh quy tắc quá đơn giản “hai biên bằng nhau thì luôn rỗng”: điều đó đúng với overload mặc định `[20, 20)`, nhưng không đúng với `[20, 20]`.

Khi kiểm thử một truy vấn khoảng, hãy có dữ liệu đúng tại từng biên. Nếu chỉ thử các giá trị nằm sâu bên trong, lỗi đặt nhầm `true` và `false` rất dễ không bị phát hiện.

## 4. Chính sách null bắt đầu từ thứ tự, không bắt đầu từ view

### 4.1. TreeSet theo thứ tự tự nhiên không nhận null

Một TreeSet số nguyên theo thứ tự tự nhiên dùng quan hệ so sánh của Integer. Nó không có quy tắc tự nhiên để đặt `null` trước hoặc sau các số.

Vì vậy, không chỉ `add(null)` là vấn đề. Dùng `null` làm biên của `headSet`, `tailSet` hoặc `subSet` cũng cần một quy tắc so sánh phù hợp. Một Set đang rỗng không biến mốc null thành hợp lệ theo thứ tự tự nhiên.

### 4.2. Comparator có thể định nghĩa vị trí cho null

Hai cấu hình thường dùng:

```java
// Trích đoạn; cần import java.util.Comparator và TreeSet.
TreeSet<Integer> nullFirst =
        new TreeSet<>(Comparator.nullsFirst(Comparator.naturalOrder()));

TreeSet<Integer> nullLast =
        new TreeSet<>(Comparator.nullsLast(Comparator.naturalOrder()));
```

Ở đây:

- `nullsFirst` đặt null trước các giá trị khác.
- `nullsLast` đặt null sau các giá trị khác.
- `naturalOrder` so sánh các giá trị không null.
- Hai null được xem là tương đương, nên Set không lưu nhiều lần xuất hiện của null.

Các quy tắc này được mô tả trong [Comparator.nullsFirst và nullsLast của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html#nullsFirst(java.util.Comparator)).

Null không tự có nghĩa bằng 0, chuỗi rỗng hoặc giá trị nhỏ nhất của kiểu số. Nó có vị trí vì comparator đã được chọn rõ ràng.

### 4.3. Khả năng lưu null không quyết định ý nghĩa nghiệp vụ

Nếu null biểu diễn “chưa biết mức ưu tiên”, một Set các mức ưu tiên chỉ giữ một thành viên null. Nó không tự ghi nhận được số lượng công việc chưa có ưu tiên.

Nếu cần nhiều bản ghi khác nhau cùng thiếu một thuộc tính, hãy thiết kế khóa cho từng bản ghi hoặc một cấu trúc lưu phù hợp. Đừng dùng một Set các giá trị rồi mong nó bảo toàn số lần xuất hiện.

Tương tự, cho null đứng đầu không đương nhiên có nghĩa các bản ghi thiếu dữ liệu nên được xử lý trước. Chính sách sắp xếp và chính sách nghiệp vụ cần được thống nhất có chủ đích.

## 5. null làm biên là một vị trí thật, không phải bỏ trống biên

Với `nullsFirst`, thứ tự có thể là:

```text
null < 10 < 20 < 30
```

Với `nullsLast`:

```text
10 < 20 < 30 < null
```

Khi truyền null làm mốc, các phương thức dùng đúng vị trí ấy. Null không có nghĩa “không có biên dưới” hoặc “không có biên trên”.

Giả sử cả hai tập đều chứa đủ `null, 10, 20, 30`:

| Lời gọi | nullsFirst | nullsLast |
|---|---|---|
| `headSet(null, false)` | `[]` | `[10, 20, 30]` |
| `headSet(null, true)` | `[null]` | `[10, 20, 30, null]` |
| `tailSet(null, false)` | `[10, 20, 30]` | `[]` |
| `tailSet(null, true)` | `[null, 10, 20, 30]` | `[null]` |

Bảng này phụ thuộc việc tập đang có thành viên null. Nếu chưa thêm null, các khoảng có khả năng lấy nó không tự tạo ra nó.

### 5.1. Cách hiểu “không giới hạn” phải tách khỏi null

Nếu chỉ cần giới hạn trên, dùng `headSet`. Nếu chỉ cần giới hạn dưới, dùng `tailSet`. Nếu cần toàn bộ tập, dùng tập gốc hoặc một góc nhìn phù hợp của nó.

Không viết `subSet(null, true, end, false)` như một công thức tổng quát cho “mọi giá trị trước end”. Với thứ tự tự nhiên nó thất bại; với nullsFirst nó bắt đầu từ vị trí null; với nullsLast nó có thể đảo thứ tự biên.

Một API nghiệp vụ có thể dùng null để biểu diễn “người gọi không truyền mốc”, nhưng lớp xử lý phải chuyển ý nghĩa ấy thành lời gọi collection đúng. Không chuyển thẳng null xuống TreeSet rồi giả định collection hiểu cùng quy ước.

### 5.2. Khoảng có thể chủ động lấy hoặc loại null

Với nullsFirst:

```text
[null, 30)   -> null, 10, 20
(null, 30]   -> 10, 20, 30
```

Với nullsLast:

```text
[20, null]   -> 20, 30, null
[20, null)   -> 20, 30
```

Trong cả hai trường hợp, null là mốc đang tham gia so sánh. Cờ inclusive quyết định có giữ lớp tương đương tại mốc ấy hay không.

## 6. Chương trình 2: null ở hai đầu và sự mơ hồ của kết quả null

Lưu tệp `NullableRangeEndpointsDemo.java`:

```java
import java.util.Comparator;
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

public class NullableRangeEndpointsDemo {
    public static void main(String[] args) {
        NavigableSet<Integer> nullFirst =
                new TreeSet<>(Comparator.nullsFirst(Comparator.naturalOrder()));
        nullFirst.addAll(List.of(10, 20, 30));
        nullFirst.add(null);

        System.out.println("nullsFirst = " + nullFirst);
        System.out.println("head null exclusive = "
                + nullFirst.headSet(null, false));
        System.out.println("head null inclusive = "
                + nullFirst.headSet(null, true));
        System.out.println("tail null exclusive = "
                + nullFirst.tailSet(null, false));
        System.out.println("tail null inclusive = "
                + nullFirst.tailSet(null, true));
        System.out.println("[null, 30) = "
                + nullFirst.subSet(null, true, 30, false));
        System.out.println("nullsFirst empty = " + nullFirst.isEmpty());
        System.out.println("nullsFirst first = " + nullFirst.first());

        NavigableSet<Integer> nullLast =
                new TreeSet<>(Comparator.nullsLast(Comparator.naturalOrder()));
        nullLast.addAll(List.of(10, 20, 30));
        nullLast.add(null);

        System.out.println("nullsLast = " + nullLast);
        System.out.println("head null exclusive = "
                + nullLast.headSet(null, false));
        System.out.println("head null inclusive = "
                + nullLast.headSet(null, true));
        System.out.println("tail null exclusive = "
                + nullLast.tailSet(null, false));
        System.out.println("tail null inclusive = "
                + nullLast.tailSet(null, true));
        System.out.println("[20, null] = "
                + nullLast.subSet(20, true, null, true));

        NavigableSet<Integer> after30 = nullLast.tailSet(30, false);
        NavigableSet<Integer> afterNull = nullLast.tailSet(null, false);
        System.out.println("higher 30 = " + nullLast.higher(30));
        System.out.println("after 30 empty = " + after30.isEmpty());
        System.out.println("after 30 first = " + after30.first());
        System.out.println("higher null = " + nullLast.higher(null));
        System.out.println("after null empty = " + afterNull.isEmpty());

        System.out.println("poll first from nullsFirst = "
                + nullFirst.pollFirst());
        System.out.println("after poll first = " + nullFirst);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 NullableRangeEndpointsDemo.java
java NullableRangeEndpointsDemo
```

Kết quả của lần chạy kiểm chứng:

```text
nullsFirst = [null, 10, 20, 30]
head null exclusive = []
head null inclusive = [null]
tail null exclusive = [10, 20, 30]
tail null inclusive = [null, 10, 20, 30]
[null, 30) = [null, 10, 20]
nullsFirst empty = false
nullsFirst first = null
nullsLast = [10, 20, 30, null]
head null exclusive = [10, 20, 30]
head null inclusive = [10, 20, 30, null]
tail null exclusive = []
tail null inclusive = [null]
[20, null] = [20, 30, null]
higher 30 = null
after 30 empty = false
after 30 first = null
higher null = null
after null empty = true
poll first from nullsFirst = null
after poll first = [10, 20, 30]
```

### 6.1. first trả về null không đồng nghĩa tập rỗng

Trong tập nullsFirst, `isEmpty()` là false nhưng `first()` trả về null vì null là thành viên đứng đầu.

Một tập rỗng thực sự làm `first()` ném `NoSuchElementException`. Do đó, kiểm tra “first khác null” không phải cách tổng quát để kiểm tra tập có dữ liệu.

### 6.2. higher có thể dùng null cho hai ý nghĩa

Trong tập nullsLast `[10, 20, 30, null]`:

- `higher(30)` trả về null là **thành viên thật** đứng sau 30.
- `higher(null)` trả về null vì **không có thành viên nào** đứng sau null.

Cùng một giá trị trả về nhưng ý nghĩa khác nhau. Chương trình dùng các view tương ứng để cho thấy sự khác biệt:

```text
sau 30:    view [null], không rỗng
sau null:  view [], rỗng
```

Các phương thức điều hướng trả null khi không tìm thấy được mô tả trong [NavigableSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableSet.html). Khi cho phép chính null là thành viên, người gọi cần một cách riêng để biểu đạt có hoặc không có kết quả.

### 6.3. pollFirst có thể gỡ một thành viên null thật

Lời gọi `pollFirst` trên tập nullsFirst trả null, nhưng sau đó tập mất thành viên null và còn `[10, 20, 30]`.

Đây không phải phép gọi trên một tập rỗng. Vì thế, mẫu lặp sau có thể sai khi collection cho phép null:

```java
// Mẫu dễ sai với Set có thành viên null.
Integer value;
while ((value = values.pollFirst()) != null) {
    process(value);
}
```

Đây là trích đoạn minh họa lỗi, không phải chương trình độc lập. Nếu null đứng đầu, vòng lặp có thể gỡ nó rồi dừng ngay, bỏ lại các giá trị khác.

Trong mã đơn luồng cần lấy hết, có thể phân biệt điều kiện rỗng với giá trị được lấy. Với việc chỉ đọc, iterator cũng tách riêng `hasNext()` và `next()`:

```java
// Trích đoạn đọc; values là một Set cho phép null.
Iterator<Integer> iterator = values.iterator();
while (iterator.hasNext()) {
    Integer value = iterator.next();
    processNullable(value);
}
```

`processNullable` tượng trưng cho xử lý đã được thiết kế chấp nhận null. Không dùng tự động mở hộp `Integer` thành `int` trước khi xử lý trường hợp null.

### 6.4. Optional không giữ được một null có mặt

`Optional.ofNullable(result)` biến null thành Optional rỗng. Nếu result có thể là một thành viên null thật, phép chuyển đó làm mất thông tin “có kết quả”.

Khi yêu cầu phải phân biệt, có thể dùng một kiểu kết quả có cờ tồn tại riêng, hoặc thiết kế mô hình không dùng null làm giá trị thành viên. Quyết định này nên nằm ở giao diện sử dụng, không được suy đoán từ một giá trị null sau khi đã mất ngữ cảnh.

Các ví dụ trên là mã đơn luồng. Việc kiểm tra rỗng rồi đọc hoặc gỡ là nhiều thao tác, không tự có tính nguyên tử trong môi trường nhiều luồng.

## 7. View phạm vi bổ sung giới hạn lên chính sách của tập gốc

Một comparator chấp nhận null mới giải quyết được khả năng so sánh. Một view còn có điều kiện phạm vi của riêng nó.

Ví dụ:

```text
tập gốc theo nullsFirst:
    [null, 10, 20, 30, 40]

view nonNull:
    tailSet(null, false)
    -> [10, 20, 30, 40]

view band bên trong:
    subSet(10, true, 30, false)
    -> [10, 20]
```

Tập gốc cho phép null. Nhưng nonNull loại vị trí null bằng biên mở, nên thêm null qua nonNull không hợp lệ. Tương tự, thêm 30 qua band vi phạm biên trên mở.

Cần tách hai trường hợp lỗi trong các ví dụ này:

| Tình huống | Vấn đề |
|---|---|
| Natural-order TreeSet nhận null | Không có phép so sánh null hợp lệ |
| View nullsFirst đã loại null mà bị thêm null | Giá trị so sánh được nhưng nằm ngoài phạm vi được phép |

Trường hợp thứ nhất thường ném `NullPointerException`; trường hợp thứ hai trên view TreeSet minh họa ném `IllegalArgumentException`.

Đừng thấy IllegalArgumentException rồi cho rằng comparator không biết so sánh null. Cũng đừng thấy comparator hỗ trợ null rồi suy ra mọi lối ghi vào mọi view đều hợp lệ.

### 7.1. Giới hạn liên quan tới phạm vi tương lai, không chỉ dữ liệu hiện có

Một view có giới hạn ngay cả khi không có phần tử. Nó không đơn thuần là danh sách các tham chiếu đã lấy ra ở thời điểm tạo.

Khi thêm một giá trị mới, cấu trúc kiểm tra giá trị ấy có thuộc miền view cho phép hay không. Khi tập gốc thêm một giá trị thuộc khoảng, view thấy nó mà không cần tạo lại.

Ngược lại, một giá trị ngoài khoảng vẫn không thể thêm qua view dù hiện tại tập gốc chưa có giá trị đó.

### 7.2. Góc nhìn con không được mở rộng cha

Một góc nhìn con phải nằm trong giới hạn mà cha cho phép. Khi cha có biên mở, việc đặt mốc con đúng tại biên ấy còn phụ thuộc cờ inclusive.

Với `nonNull = root.tailSet(null, false)`:

- `nonNull.headSet(null, false)` có thể biểu đạt một khoảng rỗng hợp lệ.
- `nonNull.headSet(null, true)` cố bao gồm null mà cha đã loại trừ, nên bị từ chối trong ví dụ.

Không lấy tập các phần tử hiện có để suy luận rằng cả hai yêu cầu “đều rỗng thì chắc giống nhau”. API còn bảo vệ phạm vi có thể nhận dữ liệu về sau.

Cũng không mặc định một view con tự động lấy giao với bất kỳ biên nào được đưa vào. Mốc vượt giới hạn cha có thể gây IllegalArgumentException thay vì trả về phần giao mong muốn.

## 8. Chương trình 3: null hợp lệ ở gốc nhưng bị cấm bởi view

Lưu tệp `NullableRangeViewDemo.java`:

```java
import java.util.Comparator;
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

public class NullableRangeViewDemo {
    public static void main(String[] args) {
        NavigableSet<Integer> root =
                new TreeSet<>(Comparator.nullsFirst(Comparator.naturalOrder()));
        root.addAll(List.of(10, 20, 30, 40));
        root.add(null);

        NavigableSet<Integer> nonNull = root.tailSet(null, false);
        NavigableSet<Integer> band = nonNull.subSet(10, true, 30, false);
        System.out.println("root = " + root);
        System.out.println("nonNull view = " + nonNull);
        System.out.println("band = " + band);
        band.add(15);
        System.out.println("root after band add 15 = " + root);

        try {
            nonNull.add(null);
        } catch (IllegalArgumentException ex) {
            System.out.println("view add null = "
                    + ex.getClass().getSimpleName());
        }
        try {
            band.add(30);
        } catch (IllegalArgumentException ex) {
            System.out.println("band add upper endpoint = "
                    + ex.getClass().getSimpleName());
        }

        System.out.println("empty child at excluded null = "
                + nonNull.headSet(null, false));
        try {
            nonNull.headSet(null, true);
        } catch (IllegalArgumentException ex) {
            System.out.println("child includes excluded null = "
                    + ex.getClass().getSimpleName());
        }

        TreeSet<Integer> snapshot = new TreeSet<>(band);
        System.out.println("snapshot initial = " + snapshot);
        System.out.println("snapshot add null = " + snapshot.add(null));
        System.out.println("snapshot after add null = " + snapshot);

        root.remove(10);
        System.out.println("band after root remove 10 = " + band);
        System.out.println("snapshot after root remove = " + snapshot);
        band.clear();
        System.out.println("root after band clear = " + root);
        System.out.println("snapshot after band clear = " + snapshot);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 NullableRangeViewDemo.java
java NullableRangeViewDemo
```

Kết quả của lần chạy kiểm chứng:

```text
root = [null, 10, 20, 30, 40]
nonNull view = [10, 20, 30, 40]
band = [10, 20]
root after band add 15 = [null, 10, 15, 20, 30, 40]
view add null = IllegalArgumentException
band add upper endpoint = IllegalArgumentException
empty child at excluded null = []
child includes excluded null = IllegalArgumentException
snapshot initial = [10, 15, 20]
snapshot add null = true
snapshot after add null = [null, 10, 15, 20]
band after root remove 10 = [15, 20]
snapshot after root remove = [null, 10, 15, 20]
root after band clear = [null, 30, 40]
snapshot after band clear = [null, 10, 15, 20]
```

### 8.1. View và tập gốc thay đổi qua lại

`band.add(15)` làm tập gốc có thêm 15. Khi tập gốc gỡ 10, band chỉ còn `[15, 20]`.

`band.clear()` gỡ các thành viên hiện nằm trong band khỏi tập gốc. Kết quả gốc là `[null, 30, 40]`: null và 30 vẫn còn vì đều không thuộc band đang xét.

Clear không chỉ “xóa dữ liệu tạm của kết quả”. View liên kết cùng dữ liệu nền, nên quyền thay đổi qua nó là một quyền thay đổi dữ liệu gốc có giới hạn.

### 8.2. Chính sách null và hàng rào khoảng không phải một thứ

Root chứa null và comparator chấp nhận nó. Nhưng `nonNull.add(null)` bị từ chối vì hàng rào dưới đang mở tại null.

`band.add(30)` cũng bị từ chối vì hàng rào trên mở tại 30. Cả hai lỗi đều là vi phạm phạm vi, dù các giá trị có thể được so sánh hợp lệ.

### 8.3. Bản sao không mang theo hàng rào của view

Chương trình tạo:

```java
TreeSet<Integer> snapshot = new TreeSet<>(band);
```

Bản sao có các phần tử hiện có và giữ comparator của band. Nhưng nó là một TreeSet đầy đủ mới, không còn hai mốc giới hạn 10 và 30 của band.

Vì comparator được giữ vẫn là nullsFirst, `snapshot.add(null)` thành công. Điều này không mâu thuẫn với việc band cấm null: snapshot giữ thứ tự, không giữ giới hạn phạm vi.

Sau đó, root thay đổi hoặc band bị clear không làm snapshot mất dữ liệu. Đây là sự độc lập ở cấp container.

## 9. Sao chép dữ liệu, giữ comparator và giữ phạm vi là ba yêu cầu khác nhau

Khi chuyển kết quả một khoảng sang nơi khác, hãy xác định riêng:

| Yêu cầu | Cần bảo vệ |
|---|---|
| Tách container khỏi nguồn | Tạo một collection mới |
| Giữ nguyên thứ tự và vị trí null | Giữ comparator phù hợp |
| Giữ giới hạn đóng–mở khi tiếp tục cho sửa | Tạo lại view có biên trên container mới hoặc đóng gói quy tắc |
| Không cho sửa qua tham chiếu trả về | Dùng giao diện và wrapper phù hợp |
| Tách cả dữ liệu phần tử khả biến | Cần chính sách sao chép hoặc giá trị bất biến |

Một constructor không tự hoàn thành mọi hàng trong bảng.

### 9.1. Giữ comparator khi sao chép SortedSet

Với biến có kiểu SortedSet hoặc NavigableSet, `new TreeSet<>(source)` chọn constructor SortedSet và giữ cùng thứ tự.

Nếu nguồn bị nhìn qua kiểu Collection, overload nhận Collection dùng thứ tự tự nhiên. Khi dữ liệu có null hoặc không có Comparable phù hợp, cách sao chép ấy có thể thất bại.

Có thể truyền rõ comparator:

```java
// Trích đoạn; source là một SortedSet<Integer>.
TreeSet<Integer> copy = new TreeSet<>(source.comparator());
copy.addAll(source);
```

Không chỉ hỏi “đã copy chưa”; còn phải hỏi “copy theo thứ tự nào”.

### 9.2. Muốn giữ phạm vi thì xác lập lại phạm vi

Nếu cần một bản riêng nhưng vẫn giới hạn sửa trong `[10, 30)`:

```java
// Trích đoạn; band là một SortedSet<Integer> theo comparator phù hợp.
TreeSet<Integer> detachedRoot = new TreeSet<>(band);
NavigableSet<Integer> detachedBand =
        detachedRoot.subSet(10, true, 30, false);
```

`detachedBand` liên kết với container mới, không phải root cũ. Nó có lại hai biên nên vẫn không cho thêm ngoài khoảng.

Đây là một view riêng trên nền riêng, không phải khẳng định constructor TreeSet đã nhớ giới hạn của nguồn. Nếu không muốn bên gọi vượt hàng rào qua container nền, không cung cấp trực tiếp detachedRoot cho bên ấy.

### 9.3. Chỉ đọc và bản chụp

Bọc một view bằng wrapper chỉ đọc không tự chụp dữ liệu; các thay đổi qua nguồn vẫn có thể được quan sát.

Muốn một bản chụp chỉ đọc, tạo bản sao trước rồi bọc. Khi nguồn chấp nhận null, phải chọn phép sao chép cũng chấp nhận dữ liệu và giữ thứ tự phù hợp.

Nếu phần tử là đối tượng khả biến, sao chép Set vẫn có thể chia sẻ cùng đối tượng. Sửa trường tham gia comparator có thể làm cả hai cấu trúc không còn được tổ chức đúng; một bản sao container không thay thế thiết kế khóa ổn định.

## 10. Chuyển sang API khác có thể làm đổi chính sách null

Không phải mọi Set đều có cùng quy tắc.

- TreeSet theo thứ tự tự nhiên từ chối null.
- TreeSet có comparator phù hợp có thể chấp nhận null.
- Một view có thể loại null bằng phạm vi dù comparator vẫn chấp nhận.
- `Set.copyOf` không chấp nhận collection chứa thành viên null.
- Wrapper không cho sửa và comparator là hai cơ chế khác nhau.

Theo [Set.copyOf Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)), null trong collection đầu vào gây NullPointerException. Đồng thời, kết quả có kiểu Set nói chung; nó không thay thế một SortedSet có cùng comparator và cùng các API khoảng.

Vì thế, không dùng `Set.copyOf(nullableView)` như một phép mặc định để tạo “bản TreeSet bất biến”. Cần quyết định giữ hay loại null một cách có ý thức, rồi chọn kiểu và cách sao chép phù hợp.

Trong các ví dụ, dữ liệu không null được thêm trước qua `List.of(...)`, rồi null được thêm riêng qua TreeSet có comparator hỗ trợ. Không đưa null vào một factory có chính sách cấm null rồi tưởng rằng lỗi đến từ TreeSet nhận dữ liệu.

Nếu null không có giá trị nghiệp vụ, chính sách đơn giản thường là từ chối ở ranh giới đầu vào. Nếu null có ý nghĩa cần giữ, hãy bảo toàn ý nghĩa ấy qua toàn bộ chuỗi xử lý, thay vì để một phép chuyển collection âm thầm làm đổi yêu cầu.

## 11. Chương trình 4: kiểm tra nơi chính sách thay đổi

Lưu tệp `NullPolicyTransferDemo.java`:

```java
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.NavigableSet;
import java.util.Set;
import java.util.TreeSet;

public class NullPolicyTransferDemo {
    public static void main(String[] args) {
        NavigableSet<Integer> natural = new TreeSet<>();
        try {
            natural.add(null);
        } catch (NullPointerException ex) {
            System.out.println("natural add null = "
                    + ex.getClass().getSimpleName());
        }
        try {
            natural.headSet(null, true);
        } catch (NullPointerException ex) {
            System.out.println("natural null endpoint = "
                    + ex.getClass().getSimpleName());
        }

        NavigableSet<Integer> nullable =
                new TreeSet<>(Comparator.nullsFirst(Comparator.naturalOrder()));
        nullable.addAll(List.of(10, 20));
        nullable.add(null);

        try {
            Set.copyOf(nullable);
        } catch (NullPointerException ex) {
            System.out.println("Set.copyOf nullable = "
                    + ex.getClass().getSimpleName());
        }

        NavigableSet<Integer> snapshot =
                Collections.unmodifiableNavigableSet(new TreeSet<>(nullable));
        nullable.add(15);
        System.out.println("source after add 15 = " + nullable);
        System.out.println("read-only snapshot = " + snapshot);
        try {
            snapshot.add(12);
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot add = "
                    + ex.getClass().getSimpleName());
        }

        NavigableSet<String> collapsed =
                new TreeSet<>(Comparator.nullsFirst(null));
        System.out.println("collapsed add A = " + collapsed.add("A"));
        System.out.println("collapsed add B = " + collapsed.add("B"));
        System.out.println("collapsed contains Z = " + collapsed.contains("Z"));
        collapsed.add(null);
        System.out.println("collapsed members = " + collapsed);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 NullPolicyTransferDemo.java
java NullPolicyTransferDemo
```

Kết quả của lần chạy kiểm chứng:

```text
natural add null = NullPointerException
natural null endpoint = NullPointerException
Set.copyOf nullable = NullPointerException
source after add 15 = [null, 10, 15, 20]
read-only snapshot = [null, 10, 20]
snapshot add = UnsupportedOperationException
collapsed add A = true
collapsed add B = false
collapsed contains Z = true
collapsed members = [null, A]
```

### 11.1. Natural order không nhận null, kể cả làm mốc

Hai lời gọi đầu đều ném NullPointerException: một lời gọi thêm null, một lời gọi dùng null làm biên. Điều đó xác nhận rằng null phải so sánh được trước khi bàn tới đóng hoặc mở.

### 11.2. Set.copyOf không tiếp nhận thành viên null

Nguồn nullable có comparator phù hợp nên chứa null hợp lệ. Tuy nhiên, chính sách của Set.copyOf từ chối dữ liệu ấy. Collection đích có hợp đồng riêng.

Bản chụp chỉ đọc trong chương trình được tạo từ `new TreeSet<>(nullable)` rồi mới bọc. Nó giữ null và thứ tự, không thấy giá trị 15 được thêm vào nguồn sau đó, đồng thời không cho thêm 12 qua tham chiếu snapshot.

### 11.3. Comparator.nullsFirst(null) không có nghĩa natural order

Phần cuối là một cấu hình cố ý dễ nhầm:

```java
new TreeSet<>(Comparator.nullsFirst(null))
```

Theo hợp đồng Comparator, khi comparator bên trong nullsFirst là null, các giá trị **không null đều được xem là tương đương**. Nó không tự chọn thứ tự tự nhiên cho chúng.

Vì vậy, sau khi thêm `"A"`:

- Thêm `"B"` trả về false vì comparator xem A và B bằng nhau.
- Hỏi `contains("Z")` trả về true theo cùng quan hệ so sánh.
- Thêm null tạo thêm một thành viên riêng ở đầu.

Đây là một thứ tự không phù hợp với equals của String và không đáp ứng cách hiểu thông thường về duy nhất theo equals của Set. Ví dụ giúp thấy cấu hình comparator có thể thay đổi cả tính duy nhất, không chỉ vị trí null.

Nếu muốn natural order cho các giá trị không null, hãy truyền `Comparator.naturalOrder()` rõ ràng vào nullsFirst hoặc nullsLast.

## 12. Những vị trí null khác nhau trong cấu hình không cùng ý nghĩa

Có ít nhất ba trường hợp dễ bị trộn lẫn:

| Nơi xuất hiện null | Ý nghĩa |
|---|---|
| Comparator tường minh của TreeSet là null | Dùng thứ tự tự nhiên |
| Đối số comparator của `Comparator.nullsFirst(null)` là null | Mọi giá trị không null được xem là tương đương |
| Mốc của `headSet(null, ...)` hoặc `tailSet(null, ...)` | Một giá trị biên phải được so sánh theo thứ tự đã chọn |

Trong Java, lời gọi constructor bằng null không kèm thông tin kiểu còn có thể vướng chọn overload. Khi cần minh họa trường hợp đầu, dùng một biến có kiểu rõ ràng:

```java
// Trích đoạn: comparator null ở constructor nghĩa là natural order.
Comparator<Integer> noExplicitComparator = null;
TreeSet<Integer> values = new TreeSet<>(noExplicitComparator);
```

TreeSet này vẫn không có chính sách chấp nhận phần tử null. Nó khác với TreeSet dùng một đối tượng comparator nullsFirst thật.

### 12.1. Đảo thứ tự có thể đảo cả vị trí null

Hai ý định sau không giống nhau:

```java
// Trích đoạn minh họa hai quan hệ thứ tự khác nhau.
Comparator<Integer> nullFirstDescending =
        Comparator.nullsFirst(Comparator.reverseOrder());

Comparator<Integer> reverseEverything =
        Comparator.nullsFirst(Comparator.<Integer>naturalOrder()).reversed();
```

Trường hợp thứ nhất giữ null ở đầu, nhưng xếp các số giảm dần.

Trường hợp thứ hai đảo toàn bộ quan hệ đã có, nên null chuyển về cuối. Khi tạo khoảng trên một thứ tự đảo, cả vị trí các mốc lẫn ý nghĩa trước/sau đều phải được đọc lại theo thứ tự đó.

Đừng dùng tên biến “nullFirst” như bằng chứng sau khi comparator đã bị `reversed()`; hãy xem chính quan hệ được tạo ra.

### 12.2. null của phần tử khác với null của một thuộc tính

Giả sử TreeSet chứa Task và sắp theo thuộc tính priority có thể null:

```java
// Trích đoạn mô hình; giả sử name không null.
record Task(String name, Integer priority) {
}

Comparator<Task> byPriorityThenName =
        Comparator.comparing(
                Task::priority,
                Comparator.nullsLast(Comparator.naturalOrder()))
            .thenComparing(Task::name);
```

Comparator bên trong xử lý null của **priority**, không phải tự cho phép đối tượng Task cũng null. Nếu chính phần tử Task có thể null, cần một chính sách ở lớp so sánh bên ngoài nữa.

Ngược lại, chỉ bọc comparator toàn Task bằng nullsFirst chưa tự sửa một comparator bên trong đang mở hộp priority null thành int.

Hãy xác định null nằm ở cấp nào: phần tử, trường dữ liệu, comparator cấu hình hay mốc truy vấn. Đó là bốn vai trò khác nhau, cần được xử lý ở đúng ranh giới.

## 13. Vòng đời view và quyền cập nhật dữ liệu nền

Các view phạm vi của TreeSet được hỗ trợ bởi tập gốc. Điều này làm chúng hữu ích cho thao tác có giới hạn, đồng thời đặt ra một số giả định cần rõ.

### 13.1. Đọc hiện tại hay chụp tại một thời điểm?

View thể hiện dữ liệu phù hợp đang có trên nền. Thêm hoặc xóa ở nền có thể làm view thay đổi nội dung.

Nếu cần báo cáo cố định, kết quả kiểm tra để xử lý về sau hoặc dữ liệu nhỏ giữ lâu, cân nhắc bản sao. Một view nhỏ vẫn có thể giữ tham chiếu tới nền dữ liệu lớn hơn.

Không coi “tạo view không sửa nguồn” là tương đương với “dùng view sẽ không sửa nguồn”. Việc tạo chỉ đọc cấu hình; các thao tác như add, remove, clear sau đó có thể cập nhật nền.

### 13.2. Ràng buộc phạm vi không thay chính sách nghiệp vụ

Một view `[10, 30)` chỉ kiểm tra điều kiện thứ tự, không biết 10–29 có phải mức ưu tiên hợp lệ về nghiệp vụ hay không.

Nếu comparator đặt null ở một đầu và view loại nó, đó là một hàng rào theo cấu trúc. Những quy tắc khác như chỉ nhận mức chia hết cho 5 cần kiểm tra riêng; view không phải một bộ lọc tùy ý cho mọi điều kiện.

### 13.3. Thay đổi dữ liệu dùng so sánh vẫn là lỗi

Biên được kiểm tra khi collection thực hiện thao tác, không phải một cơ chế theo dõi mọi setter của đối tượng đã lưu.

Nếu phần tử có thuộc tính priority khả biến và bị sửa trực tiếp sau khi thêm, vị trí trong cây và việc thuộc khoảng có thể không còn đúng. Cần phần tử bất biến, khóa so sánh ổn định hoặc một luồng gỡ và thêm lại có kiểm soát.

Cũng không sửa cấu hình comparator đang được một cây có dữ liệu sử dụng rồi mong cây tự tổ chức lại.

### 13.4. Iterator và nhiều thao tác

Iterator không phải ảnh chụp. Thay đổi cấu trúc qua tập gốc hoặc view khác trong lúc duyệt có thể gây ConcurrentModificationException. Cơ chế phát hiện sửa đổi không phải cách đồng bộ nhiều luồng.

Một chuỗi kiểm tra rồi cập nhật cũng không tự nguyên tử. Khi thêm nhiều giá trị vào view, một giá trị ngoài phạm vi có thể gây lỗi sau khi các giá trị trước đã được thêm. Nếu cần tất cả thành công hoặc không thay đổi gì, phải có quy trình riêng.

Những giả định đó độc lập với việc comparator xử lý null đúng. Giải quyết chính sách null không tự giải quyết tính nhất quán của một chuỗi cập nhật.

## 14. Kiểm tra một khoảng có null theo từng lớp

Một cách kiểm tra có hệ thống là đi theo thứ tự sau.

### Bước 1: xác lập quan hệ thứ tự

Ghi rõ:

```text
null bị từ chối
hoặc
null đứng đầu
hoặc
null đứng cuối
```

Sau đó ghi thứ tự giữa các giá trị không null. Nếu có nhiều tiêu chí, xác định khi nào kết quả so sánh bằng 0.

### Bước 2: xác lập hai biên và cờ

Nêu rõ `[a, b)`, `[a, b]`, `(a, b]` hay `(a, b)`. Kiểm tra a không đứng sau b theo comparator.

Nếu mốc là null, đọc nó như một mốc thật. Nếu nghiệp vụ muốn không có biên, chọn lời gọi headSet/tailSet phù hợp thay vì tự gán ý nghĩa đặc biệt cho null.

### Bước 3: xác lập phạm vi cha

Nếu đang tạo view từ một view, kiểm tra các mốc và inclusive có nằm trong quyền mà cha cho phép không. Đặc biệt kiểm tra mốc đúng tại một biên mở của cha.

### Bước 4: xác lập quyền thay đổi

Phân biệt:

- View liên kết và có thể sửa.
- View liên kết nhưng bị bọc chỉ đọc.
- Bản sao riêng có thể sửa.
- Bản sao riêng chỉ đọc.
- Bản sao riêng đã được đặt lại giới hạn phạm vi.

Những trường hợp này có thể in ra cùng nội dung ở thời điểm đầu nhưng khác nhau khi có cập nhật.

### Bước 5: kiểm tra dữ liệu đại diện

Ít nhất nên có:

- Tập rỗng.
- Tập chỉ có null nếu chính sách cho phép.
- Tập có null và giá trị thường.
- Giá trị đúng từng biên.
- Giá trị nằm trong và nằm ngoài khoảng.
- Mốc không tồn tại trong tập.
- Hai mốc tương đương.
- Thứ tự đảo nếu ứng dụng dùng comparator giảm dần.
- Thay đổi qua nguồn và qua view.
- Sao chép rồi thử thêm một giá trị từng bị view nguồn loại.

Không kiểm tra bằng một dãy chỉ có các số ở giữa khoảng. Dãy ấy không bộc lộ được lỗi biên hoặc lỗi null.

## 15. Các lỗi thường gặp và cách nhận ra

| Cách làm | Điều bị bỏ sót | Cách xử lý |
|---|---|---|
| Truyền null để biểu diễn không giới hạn | Collection có thể coi đó là mốc thật hoặc không so sánh được | Chuyển yêu cầu nghiệp vụ thành đúng overload |
| Comparator nhận null nên mọi view nhận null | View có hàng rào riêng | Kiểm tra vị trí null so với biên |
| Đổi inclusive để xử lý một null không so sánh được | Đóng/mở không tạo ra quan hệ thứ tự | Thiết kế comparator trước |
| Kiểm tra first khác null để biết có dữ liệu | Thành viên đầu có thể là null | Dùng trạng thái rỗng hoặc cách biểu đạt có kết quả riêng |
| Lặp pollFirst đến khi trả null | Có thể dừng sau khi gỡ một null thật | Tách điều kiện còn phần tử khỏi giá trị phần tử |
| Dùng Optional.ofNullable mà vẫn muốn giữ null có mặt | Optional rỗng làm mất thông tin | Đổi kiểu kết quả hoặc mô hình giá trị |
| Dùng nullsFirst(null) để lấy natural order | Mọi giá trị không null bị coi tương đương | Truyền naturalOrder rõ ràng |
| Copy một view rồi cho rằng vẫn còn giới hạn | Constructor giữ dữ liệu và thứ tự, không giữ hàng rào | Tạo lại view trên bản sao nếu cần |
| Set.copyOf để giữ nguyên một SortedSet nullable | Null bị từ chối và kiểu thứ tự không được giữ | Chọn bản sao có chính sách phù hợp |
| Chỉ đọc nghĩa là dữ liệu cố định | Nguồn của wrapper vẫn có thể đổi | Sao chép khi cần bản chụp |
| Đảo comparator nhưng cho rằng null vẫn đầu | Đảo toàn quan hệ cũng đảo vị trí null | Kiểm tra thứ tự cuối cùng |
| Bọc nullsFirst bên ngoài để chữa mọi null trong thuộc tính | Chỉ xử lý null ở cấp phần tử | Đặt chính sách ở đúng cấp dữ liệu |

Khi gặp ngoại lệ, hãy xác định lỗi nằm ở lớp nào: không so sánh được, sai thứ tự hai mốc, vượt biên cha, thêm ngoài khoảng hay cập nhật qua một wrapper không cho sửa. Không thử đổi ngẫu nhiên các cờ cho đến khi hết lỗi.

## 16. Bài tập áp dụng

### Bài 1: bốn dạng khoảng

Với `[5, 10, 15, 20]` theo thứ tự tăng dần, dự đoán `[10, 20)`, `(10, 20]` và `[10, 10]`.

**Gợi ý trả lời:** lần lượt là `[10, 15]`, `[15, 20]` và `[10]`.

### Bài 2: null không phải không giới hạn

Tập dùng nullsLast, chứa `[5, 10, null]`. `headSet(null, false)` và `tailSet(null, true)` chứa gì?

**Gợi ý trả lời:** lần lượt là `[5, 10]` và `[null]`. Null là mốc cuối của quan hệ, không phải ký hiệu bỏ trống biên.

### Bài 3: null có mặt nhưng khoảng không rỗng

Tập dùng nullsFirst và chỉ có một thành viên null. `first()` trả gì, `isEmpty()` trả gì?

**Gợi ý trả lời:** first trả null là thành viên thật; isEmpty trả false.

### Bài 4: cùng trả null, khác ý nghĩa

Tập nullsLast là `[5, 10, null]`. Giải thích `higher(10)` và `higher(null)`.

**Gợi ý trả lời:** lời gọi đầu tìm được thành viên null; lời gọi sau không tìm được thành viên nào. Nếu cần phân biệt, phải giữ trạng thái tồn tại riêng.

### Bài 5: root có null, view cấm null

Tạo view `root.tailSet(null, false)` từ root dùng nullsFirst. Thêm null qua view có hợp lệ không?

**Gợi ý trả lời:** không. Null so sánh được nhưng bị biên dưới mở loại trừ; trên TreeSet view ví dụ, thao tác gây IllegalArgumentException.

### Bài 6: sao chép một view không chứa null

View vừa nêu không có null. Tạo một TreeSet mới bằng constructor nhận SortedSet, rồi thêm null vào bản sao.

Có thể thành công không?

**Gợi ý trả lời:** có, vì comparator nullsFirst được giữ nhưng giới hạn tailSet không được mang theo. Muốn giữ giới hạn phải tạo lại view trên container mới.

### Bài 7: comparator bên trong bị bỏ trống

TreeSet dùng `Comparator.nullsFirst(null)`, đã thêm chuỗi A. Tại sao thêm B có thể trả false?

**Gợi ý trả lời:** comparator bên trong null nghĩa mọi chuỗi không null được coi tương đương; không có natural order tự động được chèn vào.

### Bài 8: bản chụp chỉ đọc

Nguồn có null hợp lệ. Cần trả một bản riêng giữ thứ tự và không cho thêm/xóa qua tham chiếu trả về. Có nên mặc định dùng Set.copyOf không?

**Gợi ý trả lời:** không. Set.copyOf từ chối null và không bảo toàn giao diện SortedSet cùng comparator. Có thể sao chép sang TreeSet giữ đúng comparator rồi bọc bằng wrapper phù hợp; đồng thời xác định yêu cầu bất biến của từng phần tử.

### Bài 9: null ở thuộc tính

Một Task không null nhưng priority null. Chỉ bọc toàn comparator Task bằng nullsLast đã đủ chưa?

**Gợi ý trả lời:** chưa chắc. Cần xử lý null trong chính phép so sánh priority; wrapper ngoài chỉ xử lý khi toàn phần tử Task là null.

Một thiết kế khoảng rõ ràng cần ghi nhận được cả miền giá trị, vị trí null, quy tắc bao gồm biên và quyền cập nhật qua view. Khi các quyết định này tách bạch, các lời gọi API mới phản ánh đúng ý nghĩa dữ liệu thay vì chỉ tình cờ cho một output mong muốn.
