# first, last, headSet, tailSet và subSet

## 1. Làm việc với hai đầu và các khoảng của một Set có thứ tự

Giả sử ứng dụng giữ các mức giá duy nhất theo thứ tự. Nó cần biết mức thấp nhất, mức cao nhất, các mức trước một ngưỡng hoặc các mức nằm giữa hai ngưỡng. Nếu dữ liệu đã nằm trong một Set sắp xếp, không cần chuyển sang một List rồi tự quét lại chỉ để biểu đạt những yêu cầu ấy.

Năm phương thức của `SortedSet` phục vụ hai nhóm thao tác:

- `first()`, `last()`: đọc một phần tử ở hai đầu theo thứ tự.
- `headSet(...)`, `tailSet(...)`, `subSet(...)`: tạo một **góc nhìn theo khoảng** trên tập hiện có.

Điểm dễ nhầm nhất là nhóm thứ hai trả về một góc nhìn liên kết với dữ liệu gốc, không phải một bản sao được lọc độc lập. Khi dùng TreeSet, các thay đổi hợp lệ qua góc nhìn có thể cập nhật trực tiếp tập gốc.

Bài này dùng TreeSet để minh họa `SortedSet` và các overload của `NavigableSet`. Các quy tắc API được đối chiếu với [SortedSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SortedSet.html) và [NavigableSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableSet.html).

Các thuật ngữ cần phân biệt:

| Thuật ngữ | Ý nghĩa trong bài |
|---|---|
| Tập gốc | Collection giữ dữ liệu mà góc nhìn đang dựa vào |
| Góc nhìn (view) | Một cách truy cập tập gốc với giới hạn và cùng dữ liệu nền |
| Biên dưới, biên trên | Các mốc giới hạn khoảng theo thứ tự của Set |
| Biên đóng, inclusive | Cho phép phần tử tương đương với mốc biên |
| Biên mở, exclusive | Không cho phép phần tử tương đương với mốc biên |
| Bản sao, bản chụp | Một collection riêng được tạo từ dữ liệu ở thời điểm sao chép |

“Trước”, “sau”, “đầu” và “cuối” luôn phải được đọc theo **thứ tự của Set**, không mặc định theo số học tăng dần.

## 2. first và last: đọc phần tử, không xóa phần tử

Với Set theo thứ tự số nguyên tăng dần:

```text
[10, 20, 30, 40, 50]
 ^               ^
first           last
```

`first()` trả về `10`, `last()` trả về `50`. Hai lời gọi không gỡ chúng khỏi tập.

Đây không phải hai chỉ số của một List:

- `first` là thành viên đứng đầu theo thứ tự.
- `last` là thành viên đứng cuối theo thứ tự.
- SortedSet không cung cấp `get(index)` chỉ vì nó có một thứ tự.
- Trong TreeSet, phần tử đầu không nhất thiết là nút gốc của cây nội bộ.

Nếu gọi trên một góc nhìn, hai phương thức chỉ xét những thành viên nằm trong góc nhìn ấy. Ví dụ, với khoảng `[20, 50)` của tập trên, `first` là `20`, còn `last` là `40`.

### 2.1. Tập rỗng là một trường hợp cần xử lý

`first()` và `last()` ném `NoSuchElementException` nếu tập đang xét rỗng. “Tập đang xét” có thể là tập gốc có dữ liệu nhưng góc nhìn không có thành viên.

Ví dụ, tập gốc chứa `10, 20, 30`, còn khoảng `[21, 29)` không chứa phần tử nào. Gọi `first` trên khoảng ấy vẫn thất bại.

Trong luồng đơn luồng hoặc đã được phối hợp đúng, có thể kiểm tra `isEmpty()` khi việc không có dữ liệu là bình thường. Không suy luận rằng `first` sẽ trả về `null` để báo rỗng. Nếu comparator cho phép một thành viên `null`, first có thể trả về chính thành viên ấy; đó vẫn là trường hợp có dữ liệu, không phải dấu hiệu tập rỗng.

Các phương thức `pollFirst` và `pollLast` của NavigableSet có hành vi khác: chúng vừa lấy vừa gỡ phần tử và trả về `null` khi không có. Không thay `first` bằng `pollFirst` chỉ để tránh ngoại lệ nếu không muốn thay đổi dữ liệu.

### 2.2. “Nhỏ nhất” phụ thuộc quan hệ thứ tự

Với comparator giảm dần, dãy duyệt có thể là:

```text
[50, 40, 30, 20, 10]
 ^               ^
first           last
```

Lúc này `first()` trả về số lớn nhất theo giá trị số học. Vì vậy, gọi first là “đầu theo comparator” chính xác hơn gọi nó luôn là “số nhỏ nhất”.

## 3. Ba dạng khoảng mặc định của SortedSet

Trước hết xét thứ tự tự nhiên tăng dần, với tập:

```text
S = [10, 20, 30, 40, 50]
```

Các overload không có cờ boolean có quy tắc cố định:

| Lời gọi | Điều kiện theo thứ tự | Ký hiệu khoảng | Ví dụ |
|---|---|---|---|
| `S.headSet(b)` | Phần tử đứng trước b | `(-∞, b)` | `headSet(30)` → `[10, 20]` |
| `S.tailSet(a)` | Phần tử từ a trở đi, gồm a | `[a, +∞)` | `tailSet(30)` → `[30, 40, 50]` |
| `S.subSet(a, b)` | Từ a đến trước b | `[a, b)` | `subSet(20, 50)` → `[20, 30, 40]` |

Ký hiệu vô cực ở đây chỉ diễn tả phía không có biên bổ sung; không cần có một đối tượng “vô cực” trong Set.

Hai quy tắc nên đọc thành câu:

- `headSet` mặc định **không lấy mốc trên**.
- `tailSet` mặc định **có lấy mốc dưới**.

Vì vậy, `headSet(x)` và `tailSet(x)` có thể chia tập thành hai phần không chồng nhau theo cùng một mốc. Nếu thành viên tương đương x tồn tại, nó thuộc phía tail.

Với `subSet(a, b)`, phía đầu đóng và phía cuối mở. Đây là khoảng nửa mở, thường thuận tiện khi chia các vùng liền kề.

### 3.1. Biên là mốc so sánh, không cần là thành viên

Với `S = [10, 20, 30, 40, 50]`:

```text
headSet(25)      -> [10, 20]
tailSet(25)      -> [30, 40, 50]
subSet(25, 45)   -> [30, 40]
```

Không có `25` hoặc `45` trong Set vẫn tạo khoảng hợp lệ. Các mốc được dùng để so sánh, không phải yêu cầu tìm đúng hai đối tượng đang lưu rồi cắt theo vị trí của chúng.

Do đó, không cần gọi `contains(a)` hoặc `contains(b)` như một điều kiện bắt buộc trước khi tạo subSet. Điều cần kiểm tra là mốc có so sánh được, có đúng thứ tự và có nằm trong giới hạn của góc nhìn cha hay không.

### 3.2. Khoảng hợp lệ vẫn có thể rỗng

`subSet(21, 29)` của tập trên hợp lệ nhưng hiện không có phần tử. Điều đó khác với việc tham số sai.

Nếu sau này thêm `25` vào tập gốc, góc nhìn `[21, 29)` có thể thấy nó. Hai mốc vẫn giữ nguyên; nội dung hiện có thay đổi theo tập gốc.

Với `subSet(30, 30)`, khoảng là `[30, 30)`: không giá trị nào vừa từ 30 trở đi vừa đứng trước 30. Khoảng đó rỗng kể cả khi tập gốc có phần tử 30.

## 4. Chương trình 1: biên mặc định và hai đầu

Lưu tệp `SortedSetBoundsDemo.java`:

```java
import java.util.List;
import java.util.NoSuchElementException;
import java.util.SortedSet;
import java.util.TreeSet;

public class SortedSetBoundsDemo {
    public static void main(String[] args) {
        SortedSet<Integer> values =
                new TreeSet<>(List.of(10, 20, 30, 40, 50));

        System.out.println("values = " + values);
        System.out.println("first = " + values.first());
        System.out.println("last = " + values.last());
        System.out.println("after first and last = " + values);
        System.out.println("headSet 30 = " + values.headSet(30));
        System.out.println("tailSet 30 = " + values.tailSet(30));
        System.out.println("subSet 20 to 50 = " + values.subSet(20, 50));
        System.out.println("headSet 25 = " + values.headSet(25));
        System.out.println("tailSet 25 = " + values.tailSet(25));
        System.out.println("subSet 25 to 45 = " + values.subSet(25, 45));

        SortedSet<Integer> empty = values.subSet(30, 30);
        System.out.println("equal endpoints = " + empty);
        System.out.println("equal endpoints empty = " + empty.isEmpty());

        try {
            empty.first();
        } catch (NoSuchElementException ex) {
            System.out.println("empty first = "
                    + ex.getClass().getSimpleName());
        }
        try {
            empty.last();
        } catch (NoSuchElementException ex) {
            System.out.println("empty last = "
                    + ex.getClass().getSimpleName());
        }
        try {
            values.subSet(50, 20);
        } catch (IllegalArgumentException ex) {
            System.out.println("reversed endpoints = "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 SortedSetBoundsDemo.java
java SortedSetBoundsDemo
```

Kết quả của lần chạy kiểm chứng:

```text
values = [10, 20, 30, 40, 50]
first = 10
last = 50
after first and last = [10, 20, 30, 40, 50]
headSet 30 = [10, 20]
tailSet 30 = [30, 40, 50]
subSet 20 to 50 = [20, 30, 40]
headSet 25 = [10, 20]
tailSet 25 = [30, 40, 50]
subSet 25 to 45 = [30, 40]
equal endpoints = []
equal endpoints empty = true
empty first = NoSuchElementException
empty last = NoSuchElementException
reversed endpoints = IllegalArgumentException
```

Mã dùng ngôn ngữ và API có ở Java 17 trở lên. Các chương trình trong bài được biên dịch với `--release 17` và chạy kiểm chứng bằng Azul OpenJDK 24.0.2.

Những điểm cần đối chiếu từ output:

1. Sau `first` và `last`, tập vẫn giữ nguyên.
2. `headSet(30)` không chứa 30, còn `tailSet(30)` có chứa 30.
3. `subSet(20, 50)` chứa 20 nhưng không chứa 50.
4. Biên không tồn tại như 25 hoặc 45 không tự gây lỗi.
5. Hai biên bằng nhau theo overload mặc định tạo khoảng rỗng.
6. Đảo thứ tự hai biên trong thứ tự tăng dần gây `IllegalArgumentException`.

Đừng bắt tất cả các tình huống này bằng một xử lý chung “không có dữ liệu”. Khoảng rỗng, tập rỗng và tham số sai là những trạng thái có ý nghĩa khác nhau.

## 5. NavigableSet cho phép chọn biên đóng hoặc mở

Các overload có boolean cho phép biểu đạt rõ việc có lấy biên hay không:

```java
headSet(toElement, inclusive)
tailSet(fromElement, inclusive)
subSet(fromElement, fromInclusive, toElement, toInclusive)
```

Đây là chữ ký minh họa cách gọi, không phải các khai báo phương thức độc lập trong một chương trình.

Các dạng khoảng hai phía tương ứng:

| Lời gọi | Kiểu khoảng |
|---|---|
| `subSet(a, true, b, false)` | `[a, b)` |
| `subSet(a, true, b, true)` | `[a, b]` |
| `subSet(a, false, b, false)` | `(a, b)` |
| `subSet(a, false, b, true)` | `(a, b]` |

Trên tập `[10, 20, 30, 40, 50]`, khoảng `(20, 50]` là `[30, 40, 50]`.

Không cố mô phỏng biên đóng bằng cách cộng `1` vào mốc trên cho mọi kiểu dữ liệu. Cách đó có thể tràn với số nguyên, không áp dụng trực tiếp cho chuỗi và không giải quyết tổng quát các miền thời gian. Overload boolean diễn tả chính xác ý định mà không cần phát minh “giá trị kế tiếp”.

### 5.1. Các overload mặc định tương đương dạng nào?

Với một NavigableSet, có thể hiểu các lời gọi cũ như:

```text
headSet(b)       tương đương headSet(b, false)
tailSet(a)       tương đương tailSet(a, true)
subSet(a, b)     tương đương subSet(a, true, b, false)
```

Sự tương đương ở đây là về khoảng được biểu đạt. Kiểu trả về khai báo của các overload cũ trong Java 17 vẫn là `SortedSet`; các overload có cờ trả về `NavigableSet`.

Ví dụ:

```java
// Trích đoạn; cần import java.util.NavigableSet, SortedSet và TreeSet.
NavigableSet<Integer> values = new TreeSet<>();

SortedSet<Integer> defaultRange = values.subSet(20, 50);
NavigableSet<Integer> explicitRange =
        values.subSet(20, true, 50, false);
```

Nếu biến chỉ có kiểu `SortedSet`, không thể gọi trực tiếp overload boolean qua biến ấy. Hãy khai báo kiểu phù hợp với khả năng cần dùng, thay vì ép kiểu tùy tiện một SortedSet bất kỳ thành NavigableSet.

### 5.2. Hai biên tương đương không phải lúc nào cũng rỗng

Khi hai mốc tương đương theo comparator:

- Dạng `[a, a]` có thể chứa thành viên tương đương a.
- Các dạng có ít nhất một phía mở đều rỗng.

Nếu chưa có thành viên tương đương a, góc nhìn `[a, a]` ban đầu vẫn rỗng nhưng có thể cho phép thêm một thành viên tương đương ấy về sau. Ngược lại, `[a, a)` không có vị trí hợp lệ nào để thêm.

“Bằng nhau” ở đây phải đọc theo kết quả so sánh bằng 0, không chỉ theo việc hai mốc là cùng tham chiếu hoặc `equals` trả về true.

## 6. Chương trình 2: biên đóng/mở và góc nhìn lồng nhau

Lưu tệp `NavigableSetInclusiveDemo.java`:

```java
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

public class NavigableSetInclusiveDemo {
    public static void main(String[] args) {
        NavigableSet<Integer> values =
                new TreeSet<>(List.of(10, 20, 30, 40, 50));

        System.out.println("head 30 exclusive = "
                + values.headSet(30, false));
        System.out.println("head 30 inclusive = "
                + values.headSet(30, true));
        System.out.println("tail 30 exclusive = "
                + values.tailSet(30, false));
        System.out.println("tail 30 inclusive = "
                + values.tailSet(30, true));
        System.out.println("sub (20, 50] = "
                + values.subSet(20, false, 50, true));
        System.out.println("sub [30, 30] = "
                + values.subSet(30, true, 30, true));
        System.out.println("sub [30, 30) = "
                + values.subSet(30, true, 30, false));
        System.out.println("sub (30, 30) = "
                + values.subSet(30, false, 30, false));

        NavigableSet<Integer> parent = values.subSet(20, false, 50, false);
        System.out.println("parent (20, 50) = " + parent);
        System.out.println("child excludes parent endpoint = "
                + parent.headSet(50, false));
        try {
            parent.headSet(50, true);
        } catch (IllegalArgumentException ex) {
            System.out.println("child includes excluded parent endpoint = "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 NavigableSetInclusiveDemo.java
java NavigableSetInclusiveDemo
```

Kết quả của lần chạy kiểm chứng:

```text
head 30 exclusive = [10, 20]
head 30 inclusive = [10, 20, 30]
tail 30 exclusive = [40, 50]
tail 30 inclusive = [30, 40, 50]
sub (20, 50] = [30, 40, 50]
sub [30, 30] = [30]
sub [30, 30) = []
sub (30, 30) = []
parent (20, 50) = [30, 40]
child excludes parent endpoint = [30, 40]
child includes excluded parent endpoint = IllegalArgumentException
```

Bốn dòng đầu chỉ thay cờ inclusive nhưng làm thay đổi việc giữ lại phần tử đúng mốc 30. Đây là lỗi lệch biên phổ biến nếu chỉ đọc tên `headSet` hoặc `tailSet` rồi bỏ qua overload đang gọi.

Phần hai biên cùng là 30 cho thấy `[30, 30]` giữ 30, còn `[30, 30)` và `(30, 30)` rỗng.

### 6.1. Khoảng con không được mở rộng khoảng cha

Khoảng cha trong chương trình là `(20, 50)`, hiện chứa `[30, 40]`.

Lời gọi:

```java
parent.headSet(50, false)
```

giữ cùng giới hạn trên mở, nên hợp lệ. Nhưng:

```java
parent.headSet(50, true)
```

yêu cầu một biên đóng tại 50, trong khi chính 50 bị khoảng cha loại trừ. Trường hợp này bị từ chối bằng `IllegalArgumentException`.

Điều cần kiểm tra là **phạm vi được phép**, không chỉ các phần tử đang xuất hiện. Dù trong ví dụ hiện tại cả hai yêu cầu trông như sẽ in ra cùng `[30, 40]`, yêu cầu thứ hai vẫn cố thay đổi quyền bao gồm mốc mà cha không cho phép.

### 6.2. Không mặc định các khoảng lồng nhau tự lấy giao

Nếu khoảng cha là `[20, 50)`, gọi `parent.headSet(60)` không có nghĩa “cứ lấy tất cả phần tử của cha vì chúng đều nhỏ hơn 60”. Mốc mới vượt ra ngoài phạm vi cha và có thể bị từ chối.

Hãy xác định biên phù hợp trước khi gọi. Nếu mục tiêu là giao của hai điều kiện độc lập, tính biên giao theo comparator và kiểm tra đóng/mở của chúng, rồi tạo một khoảng nằm trong phạm vi hợp lệ.

Các mốc đúng tại biên mở của cha cần đặc biệt cẩn thận: việc yêu cầu bao gồm hay loại trừ mốc ấy có thể quyết định lời gọi có hợp lệ không, như chương trình vừa minh họa.

## 7. Góc nhìn liên kết: cùng dữ liệu, thêm một hàng rào phạm vi

Một mô hình dễ nhớ là:

```text
tập gốc:     10  20  30  40  50  60
                 |----------|
góc nhìn:       [20, 50)

Không có một bản sao riêng của 20, 30, 40.
Góc nhìn chỉ cho phép làm việc với vùng tương ứng trên cùng dữ liệu.
```

Theo hợp đồng các phương thức tạo khoảng của SortedSet, góc nhìn được hỗ trợ bởi tập gốc: thay đổi qua một phía được phản ánh ở phía còn lại. Điều này bao gồm dữ liệu được thêm hoặc gỡ sau lúc góc nhìn được tạo.

Với TreeSet có thể sửa:

- Thêm vào tập gốc một giá trị trong khoảng thì góc nhìn thấy giá trị ấy.
- Gỡ một giá trị trong khoảng qua góc nhìn thì tập gốc mất giá trị ấy.
- Thêm qua góc nhìn một giá trị hợp lệ trong khoảng thì tập gốc có thêm.
- Thêm qua góc nhìn một giá trị ngoài khoảng bị từ chối.
- `clear()` qua góc nhìn gỡ các thành viên hiện nằm trong khoảng khỏi tập gốc.

Một view không có nghĩa tự động chỉ đọc. Nó cũng không có nghĩa một bảng dữ liệu độc lập.

### 7.1. Biên cố định, nội dung có thể thay đổi

Tạo `window = root.subSet(20, true, 50, false)` xác lập khoảng `[20, 50)`. Nếu root được thêm 25 hoặc 35, window thay đổi nội dung nhưng không tự đổi hai biên.

Nếu gỡ mọi phần tử hiện có trong khoảng, window có thể trở thành rỗng. Sau đó, thêm lại một giá trị hợp lệ qua root hoặc window vẫn có thể làm nó có dữ liệu.

Không dùng `window.first()` và `window.last()` như cách lấy lại hai mốc khai báo. Chúng trả về phần tử hiện có, có thể khác mốc và có thể không tồn tại khi khoảng rỗng.

### 7.2. Thêm ngoài khoảng khác với không có thành viên

Trong một góc nhìn số nguyên `[20, 50)`, thêm `50` vi phạm biên mở trên và gây `IllegalArgumentException`. Việc tập gốc có sẵn 50 không làm lời gọi ấy hợp lệ.

Với một giá trị so sánh hợp lệ nhưng nằm ngoài khoảng, các phép hỏi thành viên hoặc gỡ thường đơn giản không tìm thấy nó trong góc nhìn. Đừng đánh đồng điều đó với quyền thêm ngoài khoảng.

Các lỗi kiểu dữ liệu hoặc `null` không phù hợp comparator là vấn đề riêng; không dựa vào quy tắc ngoài khoảng để bỏ qua khả năng so sánh hợp lệ.

### 7.3. clear không xóa biến view

`window.clear()` không có nghĩa “bỏ liên kết của biến window và giữ root nguyên vẹn”. Nó là một phép thay đổi collection: gỡ những phần tử thuộc window.

Sau đó, biến window vẫn biểu đạt cùng góc nhìn trên cùng root. Nếu cần bỏ tham chiếu tới view, đó là thao tác quản lý biến; nếu cần giữ dữ liệu riêng rồi xóa cục bộ, trước hết phải tạo một bản sao phù hợp.

## 8. Chương trình 3: thay đổi qua góc nhìn và qua tập gốc

Lưu tệp `BackedRangeViewDemo.java`:

```java
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

public class BackedRangeViewDemo {
    public static void main(String[] args) {
        NavigableSet<Integer> root =
                new TreeSet<>(List.of(10, 20, 30, 40, 50, 60));
        NavigableSet<Integer> window = root.subSet(20, true, 50, false);

        System.out.println("initial window = " + window);
        root.add(35);
        System.out.println("after root add 35 = " + window);

        System.out.println("window remove 30 = " + window.remove(30));
        System.out.println("root after remove = " + root);
        System.out.println("window add 25 = " + window.add(25));
        System.out.println("root after add = " + root);

        TreeSet<Integer> snapshot = new TreeSet<>(window);

        try {
            window.add(50);
        } catch (IllegalArgumentException ex) {
            System.out.println("add excluded endpoint = "
                    + ex.getClass().getSimpleName());
        }
        try {
            window.headSet(60);
        } catch (IllegalArgumentException ex) {
            System.out.println("widen child bound = "
                    + ex.getClass().getSimpleName());
        }

        root.remove(20);
        System.out.println("window after root remove 20 = " + window);
        System.out.println("snapshot after root remove = " + snapshot);

        window.clear();
        System.out.println("root after window clear = " + root);
        System.out.println("window after clear = " + window);
        System.out.println("snapshot after clear = " + snapshot);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 BackedRangeViewDemo.java
java BackedRangeViewDemo
```

Kết quả của lần chạy kiểm chứng:

```text
initial window = [20, 30, 40]
after root add 35 = [20, 30, 35, 40]
window remove 30 = true
root after remove = [10, 20, 35, 40, 50, 60]
window add 25 = true
root after add = [10, 20, 25, 35, 40, 50, 60]
add excluded endpoint = IllegalArgumentException
widen child bound = IllegalArgumentException
window after root remove 20 = [25, 35, 40]
snapshot after root remove = [20, 25, 35, 40]
root after window clear = [10, 50, 60]
window after clear = []
snapshot after clear = [20, 25, 35, 40]
```

Hãy đọc theo từng giai đoạn.

### 8.1. Thêm qua root làm window thay đổi

Ban đầu window là `[20, 30, 40]`. Sau `root.add(35)`, window thành `[20, 30, 35, 40]`. Không có lời gọi tạo lại subSet.

Đó là bằng chứng trực tiếp của tính liên kết. Nếu muốn một báo cáo giữ đúng dữ liệu tại thời điểm bắt đầu, chỉ giữ biến window là chưa đủ.

### 8.2. Xóa và thêm qua window làm root thay đổi

`window.remove(30)` làm root mất 30. `window.add(25)` làm root có 25. Cả hai thao tác đều tác động lên dữ liệu nền.

Sau đó, `window.add(50)` bị từ chối vì 50 là biên trên bị loại trừ. Lỗi này không làm khoảng tự rộng ra.

Lời gọi `window.headSet(60)` cũng bị từ chối: một góc nhìn con không được yêu cầu biên vượt ra ngoài góc nhìn cha.

### 8.3. Bản chụp có vòng đời riêng

Chương trình tạo:

```java
TreeSet<Integer> snapshot = new TreeSet<>(window);
```

Tại thời điểm ấy, snapshot có `[20, 25, 35, 40]`. Khi root gỡ 20, window mất 20 nhưng snapshot còn 20.

Sau `window.clear()`, root chỉ còn `[10, 50, 60]`: các phần tử thuộc khoảng đã bị gỡ. Snapshot vẫn là `[20, 25, 35, 40]`.

Vì phần tử là Integer bất biến, ví dụ này dễ quan sát sự độc lập của hai container mà không có thêm vấn đề chia sẻ đối tượng khả biến.

## 9. Mọi biên đều được đọc theo comparator

Giả sử `cmp(x, y)` là phép so sánh của Set. Khi không có comparator tường minh, hiểu đó là phép so sánh theo thứ tự tự nhiên.

Có thể viết quy tắc tổng quát:

```text
headSet(b):       cmp(x, b) < 0
tailSet(a):       cmp(x, a) >= 0
subSet(a, b):     cmp(x, a) >= 0 và cmp(x, b) < 0
```

Với comparator giảm dần, “x đứng trước b” có thể có nghĩa x lớn hơn b về số học.

Điều kiện hợp lệ của hai mốc cũng là a không đứng sau b theo comparator, không phải luôn là `a <= b` theo số học.

### 9.1. Đọc head và tail trên một dãy cụ thể

Với dãy theo comparator:

```text
50, 40, 30, 20, 10
```

- Head trước mốc 30 là `50, 40`.
- Tail từ mốc 30 là `30, 20, 10`.
- Khoảng từ 40 đến trước 20 là `40, 30`.

Một cách thực hành hiệu quả là viết dãy theo đúng thứ tự của Set rồi đánh dấu các mốc trên dãy ấy, thay vì luôn vẽ trục số tăng dần.

### 9.2. Biên theo đối tượng nghiệp vụ

Nếu comparator xét một thuộc tính, mốc cũng được hiểu qua thuộc tính đó. Ví dụ, comparator chỉ xét điểm số thì một đối tượng mốc có thể tương đương với nhiều đối tượng cùng điểm theo quy tắc so sánh.

Tuy nhiên, TreeSet chỉ giữ một thành viên trong mỗi lớp tương đương mà comparator xác định. Nếu muốn giữ nhiều người cùng điểm, phải thiết kế thêm tiêu chí phân biệt phù hợp hoặc dùng mô hình dữ liệu khác.

Cách comparator quyết định tương đương ảnh hưởng cả thành viên trong tập lẫn việc có nằm đúng biên hay không. Đừng giả định biên chỉ được bao gồm khi đối tượng đó có cùng tham chiếu với mốc.

## 10. Chương trình 4: khoảng trong thứ tự giảm dần

Lưu tệp `ReverseRangeBoundsDemo.java`:

```java
import java.util.Comparator;
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

public class ReverseRangeBoundsDemo {
    public static void main(String[] args) {
        NavigableSet<Integer> values =
                new TreeSet<>(Comparator.reverseOrder());
        values.addAll(List.of(10, 20, 30, 40, 50));

        System.out.println("reverse values = " + values);
        System.out.println("first = " + values.first());
        System.out.println("last = " + values.last());
        System.out.println("headSet 30 = " + values.headSet(30));
        System.out.println("tailSet 30 = " + values.tailSet(30));
        System.out.println("subSet 40 to 20 = " + values.subSet(40, 20));
        System.out.println("subSet inclusive endpoints = "
                + values.subSet(40, true, 20, true));

        NavigableSet<Integer> view = values.subSet(40, true, 20, false);
        TreeSet<Integer> snapshot = new TreeSet<>(view);
        System.out.println("snapshot preserves order = " + snapshot);
        values.remove(30);
        System.out.println("view after root remove = " + view);
        System.out.println("snapshot after root remove = " + snapshot);

        try {
            values.subSet(20, 40);
        } catch (IllegalArgumentException ex) {
            System.out.println("wrong comparator endpoint order = "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 ReverseRangeBoundsDemo.java
java ReverseRangeBoundsDemo
```

Kết quả của lần chạy kiểm chứng:

```text
reverse values = [50, 40, 30, 20, 10]
first = 50
last = 10
headSet 30 = [50, 40]
tailSet 30 = [30, 20, 10]
subSet 40 to 20 = [40, 30]
subSet inclusive endpoints = [40, 30, 20]
snapshot preserves order = [40, 30]
view after root remove = [40]
snapshot after root remove = [40, 30]
wrong comparator endpoint order = IllegalArgumentException
```

Ở đây, `first` là 50 và `last` là 10. `headSet(30)` chứa `[50, 40]`, khác hoàn toàn cách hiểu “head luôn là các số nhỏ hơn”.

Lời gọi `subSet(40, 20)` hợp lệ vì 40 đứng trước 20 theo comparator giảm dần. Ngược lại, `subSet(20, 40)` đảo thứ tự biên theo comparator và gây `IllegalArgumentException`.

Các cờ inclusive vẫn giữ đúng ý nghĩa: `subSet(40, true, 20, true)` lấy cả hai đầu, cho `[40, 30, 20]`.

Bản chụp được tạo từ một biến có kiểu NavigableSet. Constructor nhận SortedSet của TreeSet giữ lại quan hệ thứ tự, nên snapshot vẫn duyệt `[40, 30]`. Khi tập gốc gỡ 30, view chỉ còn 40 nhưng snapshot giữ nguyên.

Ví dụ này nối hai quyết định độc lập:

1. Muốn view hay bản sao?
2. Muốn giữ comparator nào?

Chọn bản sao mà vô tình đổi comparator có thể làm kết quả khác ý định, dù dữ liệu đầu vào giống nhau.

## 11. Tạo bản sao và giữ đúng thứ tự

### 11.1. Sao chép từ SortedSet

Nếu biến nguồn có kiểu SortedSet hoặc một kiểu con phù hợp:

```java
// Trích đoạn minh họa; view có kiểu SortedSet<Integer>.
SortedSet<Integer> snapshot = new TreeSet<>(view);
```

Constructor `TreeSet(SortedSet)` dùng cùng thứ tự với nguồn. Đây là lựa chọn ngắn gọn để tạo một tập riêng từ một khoảng có thứ tự.

Nhưng chú ý kiểu tĩnh tại vị trí gọi overload:

```java
// Trích đoạn minh họa khác biệt overload.
SortedSet<Integer> orderedView = view;
Collection<Integer> generalCollection = orderedView;

TreeSet<Integer> sameOrder = new TreeSet<>(orderedView);
TreeSet<Integer> naturalOrder = new TreeSet<>(generalCollection);
```

Các import được lược khỏi trích đoạn. Constructor nhận Collection sắp xếp theo thứ tự tự nhiên, trong khi constructor nhận SortedSet giữ thứ tự của SortedSet. Nếu nguồn giảm dần, hai bản sao có thể duyệt khác nhau. Nếu phần tử không có thứ tự tự nhiên phù hợp, cách gọi qua Collection còn có thể thất bại.

Không chọn overload dựa trên phỏng đoán kiểu thực tế lúc chạy. Java chọn overload từ thông tin kiểu tại lúc biên dịch.

Các constructor này được mô tả trong [tài liệu TreeSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html).

### 11.2. Truyền comparator rõ ràng

Có thể thể hiện ý định trực tiếp:

```java
// Trích đoạn; view là một SortedSet<Integer>.
TreeSet<Integer> snapshot = new TreeSet<>(view.comparator());
snapshot.addAll(view);
```

Comparator trả về `null` có nghĩa nguồn dùng thứ tự tự nhiên; constructor tương ứng chấp nhận cách biểu đạt ấy.

Nếu cung cấp một comparator khác, đó là một phép tái tổ chức có chủ đích. Cần kiểm tra xem comparator mới có gộp các phần tử mà nguồn đang phân biệt hay không.

### 11.3. Chỉ đọc không đồng nghĩa bản chụp

Một wrapper không cho sửa quanh view vẫn có thể thấy dữ liệu gốc thay đổi. Nó hạn chế thao tác qua wrapper, không tự sao chép nền dữ liệu.

Nếu cần một bản chụp không cho thêm hoặc xóa qua tham chiếu trả về, có thể kết hợp sao chép rồi bọc:

```java
// Trích đoạn; cần import java.util.Collections.
SortedSet<Integer> snapshot =
        Collections.unmodifiableSortedSet(new TreeSet<>(view));
```

Ở đây, phần tạo TreeSet mới làm nhiệm vụ tách container; wrapper làm nhiệm vụ hạn chế cập nhật qua tham chiếu này. Hai bước có mục đích khác nhau.

### 11.4. Sao chép container vẫn có thể chia sẻ phần tử

Với một kiểu phần tử khả biến, cả bản sao và tập gốc có thể giữ tham chiếu tới cùng đối tượng. Sửa thuộc tính của đối tượng có thể được quan sát ở cả hai nơi.

Đặc biệt, không sửa thuộc tính tham gia comparator khi đối tượng đang nằm trong TreeSet. Việc có thêm một bản sao container không làm khóa trở nên bất biến và còn có thể khiến nhiều cấu trúc cùng bị ảnh hưởng.

Nếu mục tiêu là một bản chụp dữ liệu nghiệp vụ ổn định, hãy xác định có cần sao chép hoặc chuyển từng phần tử thành giá trị bất biến hay không.

## 12. Áp dụng khoảng nửa mở để chia dữ liệu

Khoảng `[a, b)` hữu ích khi chia các vùng liền nhau:

```text
[a, b)    và    [b, c)
```

Mốc b chỉ thuộc vùng thứ hai, nên hai vùng không chồng nhau tại biên ấy.

Ví dụ, khi tổ chức các ngày hoặc thời điểm:

- Từ đầu kỳ đến trước đầu kỳ kế tiếp.
- Từ một ngưỡng điểm trở lên đến trước ngưỡng nhóm sau.
- Các mã đứng từ mốc bắt đầu đến trước mốc kết thúc theo comparator.

Không cần trừ một phần nhỏ khỏi biên trên để biến nó thành “thời điểm cuối cùng”. Cách diễn đạt bằng đầu kỳ kế tiếp và biên mở thường rõ hơn, nhất là khi độ phân giải của dữ liệu có thể thay đổi.

Một trích đoạn cho thời điểm:

```java
// Trích đoạn minh họa; các kiểu nằm trong java.time và java.util.
NavigableSet<Instant> times = new TreeSet<>();
Instant start = Instant.parse("2026-10-01T00:00:00Z");
Instant end = Instant.parse("2026-11-01T00:00:00Z");

NavigableSet<Instant> octoberUtc =
        times.subSet(start, true, end, false);
```

Đây là khoảng theo các mốc UTC đã nêu, không tự suy ra một tháng theo múi giờ địa phương. Nếu nghiệp vụ định nghĩa khoảng theo múi giờ khác, cần tính hai mốc thời gian đúng trước khi truy vấn Set.

Cũng cần nhớ Set loại trùng theo quan hệ thành viên: một Set các thời điểm không tự lưu được nhiều sự kiện khác nhau cùng thời điểm. Nếu cần toàn bộ sự kiện, phải chọn khóa phân biệt hoặc một cấu trúc ánh xạ thời điểm tới các sự kiện.

Nếu khoảng được dùng làm dữ liệu báo cáo cố định, tạo bản chụp vào thời điểm thích hợp. Nếu dùng làm cửa sổ thao tác trên dữ liệu đang quản lý, view liên kết có thể đúng với yêu cầu hơn.

## 13. Hiểu chi phí của khoảng và việc giữ tham chiếu

Trong TreeSet, một khoảng được xây trên cấu trúc cây có thứ tự. Việc tạo view không có nghĩa lập tức sao chép mọi phần tử đang nằm trong khoảng.

Một mô hình triển khai là: góc nhìn giữ tham chiếu tới dữ liệu nền, các mốc biên và cờ đóng/mở, rồi giới hạn các thao tác theo chúng. [Mã nguồn TreeMap OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/TreeMap.java) cho thấy các góc nhìn khoảng và cách tìm thành viên trong giới hạn.

### 13.1. Tách chi phí tạo view khỏi chi phí đọc dữ liệu

Giả sử tập gốc có n thành viên, khoảng hiện có k thành viên và phép so sánh có chi phí hằng số:

| Việc làm | Cách hiểu phù hợp |
|---|---|
| Tạo một view theo biên | Chủ yếu ghi nhận và kiểm tra biên, không phải sao chép k phần tử |
| Tìm đầu hoặc cuối của khoảng trên cây | Có thể cần đường tìm theo biên trong cây gốc |
| Duyệt toàn bộ k phần tử của khoảng | Cần xử lý những phần tử được duyệt; không thể coi là miễn phí |
| Tạo bản sao độc lập | Phải xử lý và lưu các thành viên của bản sao |
| Xóa toàn bộ khoảng | Là nhiều thay đổi dữ liệu nền, không chỉ bỏ một biến view |

Trong phân tích cây thông thường, duyệt một khoảng có thể được hiểu theo `O(log n + k)): tìm điểm bắt đầu rồi đi qua các phần tử phù hợp. Đây là cách phân tích theo cấu trúc, không phải lời hứa rằng mọi triển khai SortedSet đều có cùng chi phí.

Tương tự, không suy ra mọi phương thức trên view đều là `O(1)` chỉ vì tạo view nhẹ.

### 13.2. size của khoảng có thể cần đếm

Một TreeSet đầy đủ có thể duy trì sẵn số thành viên. Một góc nhìn khoảng không nhất thiết có một bộ đếm riêng luôn cập nhật theo mọi thay đổi của nền dữ liệu.

Trong triển khai OpenJDK 17, việc tính kích thước của một khoảng có thể phải duyệt để đếm, và kết quả có thể được lưu lại trong một số điều kiện. Đừng viết thuật toán gọi `view.size()` nhiều lần rồi mặc định mọi lần đều có chi phí hằng số.

Nếu chỉ cần biết có dữ liệu không, `isEmpty()` biểu đạt đúng ý định hơn tự lấy size rồi so với 0. Chi phí cụ thể vẫn phụ thuộc triển khai và góc nhìn.

### 13.3. Một view nhỏ có thể giữ tập gốc tồn tại

Vì góc nhìn liên kết với cấu trúc nền, giữ lâu một khoảng chỉ có ít phần tử có thể đồng thời giữ tham chiếu tới nền dữ liệu lớn hơn.

Nếu cần giữ một kết quả nhỏ lâu dài nhưng không cần nó tiếp tục thay đổi theo nguồn, bản sao riêng có thể phù hợp hơn về cả ngữ nghĩa lẫn vòng đời bộ nhớ.

Điều này không có nghĩa luôn phải sao chép. View phù hợp khi cần tính liên kết; bản sao phù hợp khi cần tách vòng đời. Chọn theo yêu cầu sử dụng, không chỉ theo số dòng mã ngắn hơn.

## 14. Ngoại lệ, iterator và các thao tác không nguyên tử

### 14.1. Phân biệt các loại lỗi

| Tình huống | Hành vi cần dự kiến |
|---|---|
| `first` hoặc `last` trên khoảng rỗng | `NoSuchElementException` |
| Hai mốc đảo thứ tự theo comparator | `IllegalArgumentException` |
| Thêm ngoài giới hạn của một khoảng TreeSet | `IllegalArgumentException` |
| Yêu cầu khoảng con vượt phạm vi cha | Có thể bị từ chối bằng `IllegalArgumentException` |
| Giá trị không so sánh được theo quy tắc của tập | Có thể có `ClassCastException` |
| `null` khi quy tắc so sánh không hỗ trợ | Có thể có `NullPointerException` |
| Cập nhật qua một collection không cho sửa | `UnsupportedOperationException` theo hợp đồng của nó |

Không dùng việc biên không có trong tập làm lý do ném lỗi riêng nếu miền dữ liệu và thứ tự vẫn hợp lệ. Một mốc so sánh không phải một yêu cầu “phần tử này phải tồn tại”.

### 14.2. Iterator không phải bản chụp

Nếu đang duyệt một góc nhìn TreeSet rồi thay đổi cấu trúc qua tập gốc hoặc một đường khác, iterator có thể phát hiện sửa đổi và ném `ConcurrentModificationException`.

Ngay cả thay đổi nằm ngoài khoảng đang duyệt cũng có thể ảnh hưởng cơ chế phát hiện sửa đổi của cùng cấu trúc nền. Không thiết kế mã dựa trên suy luận rằng “không đổi các phần tử trong view thì iterator chắc chắn không bị ảnh hưởng”.

Nếu muốn vừa duyệt vừa gỡ, dùng cách cập nhật phù hợp với hợp đồng iterator hoặc tách rõ giai đoạn xử lý. Nếu cần một danh sách kết quả ổn định để duyệt độc lập, hãy tạo bản sao.

Fail-fast là cơ chế phát hiện lỗi theo khả năng của triển khai, không phải công cụ đồng bộ hoặc bảo đảm ảnh chụp nhất quán cho nhiều luồng.

### 14.3. addAll và các chuỗi kiểm tra không tự thành giao dịch

Nếu thêm nhiều giá trị vào một khoảng, một giá trị ngoài biên có thể khiến lời gọi thất bại sau khi những giá trị hợp lệ trước đó đã được thêm. Không mặc định lỗi là toàn bộ dữ liệu đã tự hoàn tác.

Nếu nghiệp vụ đòi hỏi tất cả thành công hoặc không thay đổi gì, cần một quy trình riêng: xác thực đầy đủ, chuẩn bị dữ liệu và phối hợp cập nhật phù hợp. Chỉ bắt ngoại lệ từ `addAll` không tạo ra tính nguyên tử.

Tương tự, kiểm tra `!view.isEmpty()` rồi gọi `view.first()` là hai thao tác. Trong mã nhiều luồng không có phối hợp, dữ liệu có thể thay đổi giữa hai bước.

Các ví dụ của bài là mã đơn luồng để làm rõ ngữ nghĩa khoảng. Tính liên kết của view không tự cung cấp an toàn đồng thời.

## 15. Những lỗi phổ biến cần tránh

| Cách hiểu hoặc cách dùng | Vấn đề | Cách sửa |
|---|---|---|
| `headSet(x)` có chứa x | Overload mặc định loại biên trên | Dùng `headSet(x, true)` nếu cần |
| `tailSet(x)` loại x | Overload mặc định gồm biên dưới | Dùng `tailSet(x, false)` nếu cần |
| `subSet(a, b)` lấy cả hai đầu | Mặc định là `[a, b)` | Chọn overload boolean rõ ràng |
| Biên phải tồn tại trong tập | Nhầm mốc so sánh với thành viên | Cho phép mốc vắng nhưng hợp lệ |
| first trả về null khi rỗng | API ném ngoại lệ khi không có phần tử | Xử lý rỗng theo ngữ nghĩa cần dùng |
| first luôn là số nhỏ nhất | Bỏ qua comparator | Đọc theo thứ tự của tập |
| Khoảng là bản sao | Thay đổi có thể lan sang tập gốc | Tạo collection riêng khi cần |
| clear view chỉ xóa kết quả tạm | Thực tế gỡ dữ liệu nền trong khoảng | Xác định quyền sở hữu trước khi thay đổi |
| Khoảng con tự giao với phạm vi cha | Mốc ngoài phạm vi có thể bị từ chối | Tính và kiểm tra biên phù hợp |
| Cộng 1 để lấy biên trên đóng | Có thể tràn hoặc sai miền dữ liệu | Dùng cờ inclusive |
| Giữ một wrapper chỉ đọc để có bản chụp | Nguồn vẫn có thể thay đổi | Sao chép trước nếu cần dữ liệu cố định |
| Copy qua Collection vẫn giữ comparator | Overload Collection dùng thứ tự tự nhiên | Giữ kiểu SortedSet hoặc truyền comparator |
| Mọi size trên khoảng đều O(1) | Có thể cần duyệt đếm | Đọc hợp đồng và phân tích đúng thao tác |

Một thói quen hữu ích trước khi viết truy vấn khoảng là ghi ra ba dòng:

```text
Thứ tự đang dùng là gì?
Mỗi đầu có được bao gồm không?
Kết quả cần liên kết với nguồn hay độc lập với nguồn?
```

Ba quyết định này thường giải thích phần lớn khác biệt giữa một đoạn mã nhìn đúng và một đoạn mã đúng yêu cầu.

## 16. Bài tập áp dụng

### Bài 1: khoảng mặc định

Cho `[5, 10, 15, 20, 25]` theo thứ tự tự nhiên. Dự đoán `headSet(15)`, `tailSet(15)` và `subSet(10, 25)`.

**Gợi ý trả lời:** lần lượt là `[5, 10]`, `[15, 20, 25]` và `[10, 15, 20]`.

### Bài 2: biên vắng mặt

Trên cùng tập, `subSet(11, 24)` có hợp lệ không và chứa gì?

**Gợi ý trả lời:** hợp lệ, chứa `[15, 20]`. Hai mốc không cần là thành viên.

### Bài 3: lấy cả hai đầu

Viết khoảng chứa các thành viên từ 10 đến 20, có lấy cả 10 lẫn 20.

**Gợi ý trả lời:** với biến NavigableSet, dùng `subSet(10, true, 20, true)`.

### Bài 4: ba khái niệm rỗng khác nhau

Phân biệt tập gốc rỗng, khoảng hiện chưa có dữ liệu và khoảng `[a, a)`.

**Gợi ý trả lời:** cả ba có thể đang in ra `[]`, nhưng khác về nền dữ liệu và khả năng thêm về sau. Một khoảng có độ rộng hợp lệ có thể nhận thành viên khi nguồn thay đổi; khoảng nửa mở với hai mốc tương đương không có giá trị hợp lệ để chứa.

### Bài 5: thay đổi qua view

Tạo view `[10, 20)`, rồi gọi `view.clear()`. Điều gì xảy ra với tập gốc?

**Gợi ý trả lời:** các thành viên của tập gốc nằm trong khoảng đó bị gỡ. Những thành viên ngoài khoảng vẫn còn; view vẫn liên kết với tập gốc.

### Bài 6: thứ tự giảm dần

Cho `[25, 20, 15, 10, 5]` theo comparator giảm dần. Dự đoán `headSet(15)` và `subSet(20, 5)`.

**Gợi ý trả lời:** `[25, 20]` và `[20, 15, 10]`. Các mốc được đọc theo comparator, không theo điều kiện số học tăng dần.

### Bài 7: khoảng con ở biên mở

Khoảng cha là `(10, 25)`. So sánh yêu cầu `headSet(25, false)` với `headSet(25, true)`.

**Gợi ý trả lời:** yêu cầu thứ nhất giữ biên trên mở nên có thể hợp lệ; yêu cầu thứ hai cố bao gồm mốc cha đã loại trừ và bị từ chối. Không chỉ nhìn nội dung hiện có để quyết định tính hợp lệ.

### Bài 8: dữ liệu báo cáo ổn định

Một hàm trả về view của tập đang tiếp tục được cập nhật. Bên nhận muốn báo cáo giữ nguyên dữ liệu tại lúc gọi. Chỉ bọc view bằng wrapper chỉ đọc có đủ không?

**Gợi ý trả lời:** chưa đủ. Cần tách dữ liệu bằng một bản sao giữ đúng comparator, rồi mới hạn chế cập nhật nếu muốn. Với phần tử khả biến, còn phải xác định mức sao chép dữ liệu.

### Bài 9: đọc đầu khoảng

Khoảng `[11, 14)` hiện không chứa phần tử. Gọi `first()` có tự trả về 11 hoặc thành viên gần nhất ngoài khoảng không?

**Gợi ý trả lời:** không. First chỉ đọc thành viên đang có bên trong khoảng và ném `NoSuchElementException` khi khoảng rỗng. Nếu cần tìm phần tử lân cận một mốc trên tập gốc, xem các phương thức điều hướng phù hợp như `ceiling` hoặc `higher`.

Khi triển khai thao tác theo khoảng, hãy diễn đạt chính xác thứ tự, đóng/mở và vòng đời dữ liệu. Đó là cơ sở để dùng cùng một API cho cả đọc biên, truy vấn khoảng và cập nhật có giới hạn mà không nhầm quyền tác động lên tập gốc.
