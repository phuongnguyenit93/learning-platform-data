# NavigableSet: lower, floor, ceiling và higher

## 1. Từ kiểm tra có phần tử tới tìm phần tử sát một ngưỡng

`contains(x)` chỉ trả lời có một phần tử tương ứng với `x` trong tập hay không. Nhiều bài toán cần một câu hỏi khác:

- Phần tử gần nhất nằm trước ngưỡng là gì?
- Giá trị lớn nhất không vượt quá giới hạn là gì?
- Giá trị nhỏ nhất đạt hoặc vượt yêu cầu là gì?
- Nếu bỏ qua chính ngưỡng đang có, phần tử tiếp theo là gì?

`NavigableSet<E>` mở rộng tập sắp xếp để hỗ trợ các phép tìm theo hướng này. Bốn phương thức trung tâm là `lower`, `floor`, `ceiling`, `higher`.

Với các số nguyên sắp theo thứ tự tự nhiên tăng dần:

| Phương thức | Quan hệ cần thỏa | Chọn phần tử nào trong các ứng viên? |
| --- | --- | --- |
| `lower(x)` | Nhỏ hơn x, ký hiệu `< x` | Lớn nhất trong các phần tử nhỏ hơn x |
| `floor(x)` | Nhỏ hơn hoặc bằng x, `≤ x` | Lớn nhất trong các phần tử không vượt x |
| `ceiling(x)` | Lớn hơn hoặc bằng x, `≥ x` | Nhỏ nhất trong các phần tử đạt hoặc vượt x |
| `higher(x)` | Lớn hơn x, `> x` | Nhỏ nhất trong các phần tử lớn hơn x |

Cả bốn trả về một phần tử phù hợp đang có trong tập, hoặc `null` nếu không có ứng viên. Chúng không trả chỉ số, không tạo một giá trị mới cho vừa ngưỡng và không tự xóa phần tử đã tìm. [NavigableSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableSet.html)

Điểm khác biệt dễ nhớ:

- `lower` và `higher` là quan hệ **chặt**: loại phần tử tương đương với ngưỡng.
- `floor` và `ceiling` là quan hệ **có lấy bằng**: có thể trả về phần tử tương đương với ngưỡng.

Từ “nhỏ hơn”, “lớn hơn” trong hợp đồng là theo **thứ tự của tập**. Với số tự nhiên tăng dần, đó là quan hệ số quen thuộc. Với một `Comparator` khác hoặc một khung nhìn đảo chiều, phải đọc theo thứ tự đang sử dụng.

## 2. Khai báo kiểu phù hợp để gọi các phương thức

Một cách dùng phổ biến trên Java 17:

```java
NavigableSet<Integer> values =
        new TreeSet<>(List.of(10, 20, 30, 40));
```

Quan hệ kiểu:

```text
Set
  ↑
SortedSet
  ↑
NavigableSet
  ↑
TreeSet triển khai các khả năng tương ứng
```

`Set` nói về tập không trùng; `SortedSet` bổ sung thứ tự; `NavigableSet` bổ sung khả năng tìm các giá trị lân cận theo ngưỡng.

Nếu khai báo biến là `Set<Integer>`, giao diện đó không cung cấp `floor` hoặc `ceiling`, dù đối tượng thực tế có thể là `TreeSet`. Khi API hoặc thuật toán thực sự cần khả năng điều hướng này, dùng một kiểu khai báo thể hiện đúng yêu cầu.

Các chữ ký có dạng:

```java
E lower(E value);
E floor(E value);
E ceiling(E value);
E higher(E value);
```

Đoạn trên mô tả chữ ký phương thức, không phải một chương trình độc lập. Với `NavigableSet<Integer>`, kết quả có kiểu `Integer`, nên có thể là `null`.

`TreeSet` là triển khai dùng cây có thứ tự. Không suy ra rằng mọi `Set`, đặc biệt một `HashSet` bất kỳ, đều có bốn phương thức hoặc cùng mô hình tìm kiếm này.

## 3. Thực sự khác nhau ở đâu khi ngưỡng có mặt?

Cho tập:

```text
[10, 20, 30, 40]
```

### 3.1. Ngưỡng 20 đã thuộc tập

```text
10 -------- 20 -------- 30 -------- 40
            ↑
          ngưỡng
```

Kết quả:

| Lời gọi | Kết quả | Giải thích |
| --- | --- | --- |
| `lower(20)` | `10` | Bỏ qua chính 20, chọn phần tử lớn nhất còn nhỏ hơn |
| `floor(20)` | `20` | Có lấy bằng, nên 20 phù hợp và là ứng viên sát ngưỡng nhất phía này |
| `ceiling(20)` | `20` | Có lấy bằng, nên không cần đi tới 30 |
| `higher(20)` | `30` | Bỏ qua chính 20, chọn phần tử nhỏ nhất còn lớn hơn |

Nếu đang tìm “giá trị tiếp theo sau giá trị hiện tại”, `higher` thường diễn đạt đúng việc phải bỏ qua giá trị hiện tại. Dùng `ceiling` có thể trả lại chính giá trị đó.

Tương tự, “giá trị trước đó” theo quan hệ chặt là `lower`; “giá trị gần nhất không vượt quá hiện tại” là `floor`.

### 3.2. Ngưỡng 25 không thuộc tập

```text
10 -------- 20 ---- 25 ---- 30 -------- 40
                    ↑
                  ngưỡng
```

Kết quả:

```text
lower(25)   = 20
floor(25)   = 20
ceiling(25) = 30
higher(25)  = 30
```

Vì không có phần tử tương đương với `25`, việc cho phép hay loại dấu bằng không làm khác tập ứng viên ở ví dụ này.

Điều đó không làm các cặp phương thức đồng nghĩa. Chúng chỉ tình cờ có cùng kết quả khi không có phần tử bằng ngưỡng theo thứ tự của tập.

Ngưỡng không cần có sẵn trong tập. Không thêm `25` vào trước để gọi tìm lân cận rồi xóa nó đi; cách đó sửa dữ liệu không cần thiết và có thể làm thay đổi ý nghĩa tập.

### 3.3. Vì sao floor(25) không phải 10?

Cả `10` và `20` đều không vượt `25`, nhưng `floor` chọn **phần tử lớn nhất** trong các ứng viên. Tương tự, cả `30` và `40` đều vượt `25`, nhưng `ceiling` chọn **phần tử nhỏ nhất** trong các ứng viên phía đó.

Các phương thức không trả về một phần tử bất kỳ chỉ vì nó thỏa dấu so sánh.

## 4. Biên, tập rỗng và ý nghĩa của null

Vẫn với `[10, 20, 30, 40]`:

| Ngưỡng | lower | floor | ceiling | higher |
| --- | --- | --- | --- | --- |
| `5` | `null` | `null` | `10` | `10` |
| `10` | `null` | `10` | `10` | `20` |
| `20` | `10` | `20` | `20` | `30` |
| `25` | `20` | `20` | `30` | `30` |
| `40` | `30` | `40` | `40` | `null` |
| `45` | `40` | `40` | `null` | `null` |

`null` không có nghĩa tập nhất thiết rỗng. Với ngưỡng `5`, tập có bốn phần tử nhưng không phần tử nào nằm ở phía thấp hơn.

Với một tập rỗng và ngưỡng truy vấn hợp lệ, cả bốn đều không có ứng viên và trả về `null`.

### 4.1. Kiểm tra null trước khi mở hộp sang kiểu nguyên thủy

Cách xử lý rõ ràng:

```java
// Đoạn minh họa: values là NavigableSet<Integer> không chứa null.
Integer previous = values.floor(5);
if (previous == null) {
    System.out.println("Không có giá trị không vượt quá 5");
} else {
    int usableValue = previous;
    System.out.println("Giá trị được chọn: " + usableValue);
}
```

Cách dễ gây lỗi:

```java
// Có thể ném NullPointerException khi floor không tìm thấy kết quả.
int previous = values.floor(5);
```

Lỗi xảy ra khi Java tự mở hộp `Integer` là `null` thành `int`. Không phải `floor` đang ném một ngoại lệ “không tìm thấy phần tử” cho truy vấn hợp lệ đó.

Không mặc định dùng `0` hay `-1` làm giá trị thay thế nếu các số đó có thể là dữ liệu hợp lệ. Chính sách khi không tìm thấy phải được quyết định theo yêu cầu ứng dụng.

### 4.2. null trong kết quả và null làm phần tử là hai chuyện khác nhau

Các ví dụ số tự nhiên trong bài không lưu phần tử `null`, nên `null` từ phép điều hướng được hiểu rõ là không có ứng viên.

Một `Comparator` có thể được thiết kế để cho phép `null`, chẳng hạn thông qua `Comparator.nullsFirst`. Khi đó, chính phần tử `null` cũng có thể là một kết quả hợp lệ theo thứ tự, làm giá trị trả về trở nên khó phân biệt.

Ví dụ với thứ tự đặt `null` trước mọi chuỗi và tập `[null, b]`, `lower("b")` có thể trả về phần tử `null` đang được lưu. Kết quả đơn lẻ giống trường hợp không có ứng viên.

Nếu phải dùng kiểu dữ liệu này, cần xét cả việc tập có `null` và quan hệ của nó với ngưỡng. Khi không có yêu cầu lưu `null`, giữ miền phần tử không chứa `null` giúp API điều hướng dễ sử dụng hơn. Tài liệu `NavigableSet` cũng nêu sự mơ hồ này. [NavigableSet: giá trị null](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableSet.html)

Không dùng `null` làm “ngưỡng mặc định” cho một tập không hỗ trợ nó. Đối số không so sánh được hoặc `null` không được chấp nhận có thể dẫn tới ngoại lệ; đây là lỗi miền đầu vào, khác với truy vấn hợp lệ không có kết quả.

## 5. Chương trình đầy đủ: đủ bốn phép tìm và xử lý không có kết quả

Lưu toàn bộ mã vào **NavigableNeighborsDemo.java**:

```java
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

public class NavigableNeighborsDemo {
    private static void show(NavigableSet<Integer> values, int target) {
        System.out.println("target " + target
                + ": lower=" + values.lower(target)
                + ", floor=" + values.floor(target)
                + ", ceiling=" + values.ceiling(target)
                + ", higher=" + values.higher(target));
    }

    public static void main(String[] args) {
        NavigableSet<Integer> values =
                new TreeSet<>(List.of(10, 20, 30, 40));
        System.out.println("values: " + values);
        show(values, 20);
        show(values, 25);
        show(values, 5);
        show(values, 45);
        System.out.println("after queries: " + values);
        System.out.println("size: " + values.size());

        NavigableSet<Integer> empty = new TreeSet<>();
        System.out.println("empty set:");
        show(empty, 20);

        Integer previous = values.floor(5);
        if (previous == null) {
            System.out.println("no value at or below 5");
        }
        try {
            int unsafe = values.floor(5);
            System.out.println("unsafe value: " + unsafe);
        } catch (NullPointerException ex) {
            System.out.println("unboxing absent result: NullPointerException");
        }

        NavigableSet<Integer> widths =
                new TreeSet<>(List.of(320, 640, 960, 1280));
        System.out.println("smallest width at least 700: " + widths.ceiling(700));
        System.out.println("largest width at most 700: " + widths.floor(700));
        System.out.println("next above 640: " + widths.higher(640));
        System.out.println("previous below 640: " + widths.lower(640));
    }
}
```

Biên dịch theo mức Java 17 và chạy:

```shell
javac --release 17 -encoding UTF-8 NavigableNeighborsDemo.java
java NavigableNeighborsDemo
```

Stdout:

```text
values: [10, 20, 30, 40]
target 20: lower=10, floor=20, ceiling=20, higher=30
target 25: lower=20, floor=20, ceiling=30, higher=30
target 5: lower=null, floor=null, ceiling=10, higher=10
target 45: lower=40, floor=40, ceiling=null, higher=null
after queries: [10, 20, 30, 40]
size: 4
empty set:
target 20: lower=null, floor=null, ceiling=null, higher=null
no value at or below 5
unboxing absent result: NullPointerException
smallest width at least 700: 960
largest width at most 700: 640
next above 640: 960
previous below 640: 320
```

Cách đọc kết quả:

1. Ngưỡng có sẵn `20` cho thấy khác biệt giữa quan hệ chặt và có lấy bằng.
2. Ngưỡng vắng mặt `25` vẫn truy vấn bình thường.
3. Ngưỡng ngoài hai phía cho thấy không có ứng viên ở một phía không làm tập rỗng.
4. Tập và kích thước giữ nguyên sau các truy vấn.
5. Tập rỗng trả về `null` cho các truy vấn hợp lệ.
6. Đoạn mở hộp không an toàn chủ động bắt `NullPointerException` để minh họa lỗi cần tránh.
7. Ví dụ độ rộng dùng `ceiling` để chọn cỡ nhỏ nhất đáp ứng yêu cầu, dùng `floor` để chọn cỡ lớn nhất không vượt giới hạn.

Bốn phương thức chỉ tìm và trả phần tử; chúng không có tác dụng lấy rồi xóa. Đừng nhầm với các thao tác như `pollFirst` hoặc `pollLast`, vốn có tác dụng sửa tập theo hợp đồng riêng.

## 6. “Nhỏ hơn” và “bằng” phụ thuộc vào thứ tự của tập

### 6.1. Quan hệ được xác định bởi Comparator hoặc Comparable

Với thứ tự `c`, có thể đọc các điều kiện:

```text
lower(target):   c.compare(candidate, target) < 0
floor(target):   c.compare(candidate, target) <= 0
ceiling(target): c.compare(candidate, target) >= 0
higher(target):  c.compare(candidate, target) > 0
```

Sau khi chọn phía thỏa điều kiện, phương thức trả ứng viên sát ngưỡng nhất theo thứ tự đó.

Khi dùng thứ tự tự nhiên, `compareTo` đảm nhiệm vai trò tương ứng. Không tự thay tất cả quan hệ bằng phép so số thông thường nếu tập đang chứa chuỗi, đối tượng miền hoặc có bộ so sánh riêng.

### 6.2. Có lấy bằng là lấy trường hợp compare bằng 0

Nếu một tập chuỗi dùng bộ so sánh không phân biệt hoa thường và đang giữ `"Bee"`, thì truy vấn `"BEE"` có thể cho:

```text
floor("BEE")   → "Bee"
ceiling("BEE") → "Bee"
```

Phần tử trả về là đại diện đang lưu trong tập. Nó không bắt buộc là chính tham chiếu đối số hoặc chuỗi bằng đối số theo `String.equals`.

Bộ so sánh không phân biệt hoa thường của chuỗi không nhất quán với `String.equals`; dùng nó trong `TreeSet` cần hiểu rằng nó không đáp ứng đầy đủ hợp đồng chung của `Set`. Ví dụ này phục vụ việc thấy rõ cơ chế so sánh, không phải khuyến nghị bỏ qua sự nhất quán đó trong thiết kế. [TreeSet: thứ tự và equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)

`lower` và `higher` bỏ qua toàn bộ trường hợp tương đương theo thứ tự, không chỉ bỏ qua một đối tượng có cùng tham chiếu.

### 6.3. Không sửa dữ liệu dùng để sắp thứ tự khi phần tử đang trong tập

Nếu phép so sánh dùng một trường có thể thay đổi, vị trí của phần tử trong cấu trúc có thể không còn phù hợp sau khi trường đó bị sửa.

Kết quả điều hướng khi ấy không còn được suy luận như với tập có quy tắc ổn định. Ưu tiên khóa so sánh bất biến và một bộ so sánh có hành vi ổn định trong thời gian tập được sử dụng.

## 7. descendingSet đảo cả hướng tìm

`descendingSet()` trả về một khung nhìn có thứ tự ngược với tập gốc. Nó không chỉ đổi cách in `for-each`; các phép điều hướng cũng được hiểu theo thứ tự ngược.

Cho tập gốc tăng dần:

```text
ascending:  [10, 20, 30, 40]
descending: [40, 30, 20, 10]
```

Trong thứ tự giảm dần, `30` đứng trước `25`, còn `20` đứng sau `25`. Vì thế:

```text
descending.lower(25)   = 30
descending.floor(25)   = 30
descending.ceiling(25) = 20
descending.higher(25)  = 20
```

Không có mâu thuẫn với bảng định nghĩa: các từ trước/sau, nhỏ/lớn đang được đọc theo bộ thứ tự của khung nhìn.

Nếu `d = s.descendingSet()`, quan hệ đối ngẫu là:

| Truy vấn trên d | Tương ứng trên s |
| --- | --- |
| `d.lower(x)` | `s.higher(x)` |
| `d.floor(x)` | `s.ceiling(x)` |
| `d.ceiling(x)` | `s.floor(x)` |
| `d.higher(x)` | `s.lower(x)` |

Dấu bằng vẫn giữ tính chất có lấy bằng; chỉ hướng quan hệ bị đảo.

Khung nhìn dùng dữ liệu nền của tập gốc. Khi dữ liệu gốc thay đổi, các kết quả truy vấn sau đó cũng có thể thay đổi. Nó không phải một bản sao dữ liệu đóng băng tại thời điểm gọi. [NavigableSet.descendingSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableSet.html#descendingSet())

## 8. Truy vấn trên một khung nhìn chỉ tìm trong miền của khung nhìn

Giả sử tập gốc là `[10, 20, 30, 40]`, nhưng biến hiện tại là khung nhìn chỉ chứa các phần tử trong đoạn từ `20` có lấy bằng tới `40` không lấy bằng:

```java
NavigableSet<Integer> window = ascending.subSet(20, true, 40, false);
```

Nội dung quan sát qua `window` là `[20, 30]`.

Khi gọi:

```text
ascending.lower(20)   → 10
window.lower(20)      → null

ascending.ceiling(35) → 40
window.ceiling(35)    → null
```

`10` và `40` có trong tập gốc, nhưng không thuộc miền mà `window` cung cấp. Phép điều hướng không tự đi ra ngoài miền đó để trả một ứng viên từ tập gốc.

Khi gặp `null` bất ngờ, hãy kiểm tra đối tượng đang nhận lời gọi là toàn bộ tập, khung nhìn đảo chiều hay khung nhìn giới hạn. Tên biến hoặc kiểu `NavigableSet` chưa đủ để biết miền dữ liệu thực tế.

Phần này chỉ minh họa phạm vi ứng viên của truy vấn; việc tạo và sửa các khung nhìn có những hợp đồng riêng. [NavigableSet: các khung nhìn giới hạn](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableSet.html)

## 9. Chương trình đầy đủ: thứ tự đảo, miền giới hạn và Comparator riêng

Lưu mã vào **NavigableOrderDemo.java**:

```java
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

public class NavigableOrderDemo {
    public static void main(String[] args) {
        NavigableSet<Integer> ascending =
                new TreeSet<>(List.of(10, 20, 30, 40));
        NavigableSet<Integer> descending = ascending.descendingSet();

        System.out.println("ascending: " + ascending);
        System.out.println("descending: " + descending);
        System.out.println("descending lower 25: " + descending.lower(25));
        System.out.println("descending floor 25: " + descending.floor(25));
        System.out.println("descending ceiling 25: " + descending.ceiling(25));
        System.out.println("descending higher 25: " + descending.higher(25));
        System.out.println("descending floor 20: " + descending.floor(20));
        System.out.println("descending ceiling 20: " + descending.ceiling(20));
        System.out.println("lower/higher dual: "
                + descending.lower(25).equals(ascending.higher(25)));

        NavigableSet<Integer> window = ascending.subSet(20, true, 40, false);
        System.out.println("window: " + window);
        System.out.println("ascending lower 20: " + ascending.lower(20));
        System.out.println("window lower 20: " + window.lower(20));
        System.out.println("ascending ceiling 35: " + ascending.ceiling(35));
        System.out.println("window ceiling 35: " + window.ceiling(35));

        NavigableSet<String> words =
                new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        words.addAll(List.of("ant", "Bee", "dog"));
        String target = "BEE";
        System.out.println("words: " + words);
        System.out.println("word lower: " + words.lower(target));
        System.out.println("word floor: " + words.floor(target));
        System.out.println("word ceiling: " + words.ceiling(target));
        System.out.println("word higher: " + words.higher(target));
        System.out.println("floor equals query text: "
                + words.floor(target).equals(target));
        System.out.println("words after queries: " + words);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 NavigableOrderDemo.java
java NavigableOrderDemo
```

Stdout:

```text
ascending: [10, 20, 30, 40]
descending: [40, 30, 20, 10]
descending lower 25: 30
descending floor 25: 30
descending ceiling 25: 20
descending higher 25: 20
descending floor 20: 20
descending ceiling 20: 20
lower/higher dual: true
window: [20, 30]
ascending lower 20: 10
window lower 20: null
ascending ceiling 35: 40
window ceiling 35: null
words: [ant, Bee, dog]
word lower: ant
word floor: Bee
word ceiling: Bee
word higher: dog
floor equals query text: false
words after queries: [ant, Bee, dog]
```

Cách đọc kết quả:

1. Khung nhìn giảm dần đảo hướng của bốn phép tìm.
2. Khi ngưỡng `20` có phần tử tương đương, `floor` và `ceiling` vẫn có thể trả về `20` ở cả hai chiều.
3. Dòng `lower/higher dual` kiểm tra một trường hợp cụ thể mà hai kết quả đều có mặt; trong mã tổng quát vẫn cần xử lý kết quả `null`.
4. Khung nhìn giới hạn không trả ứng viên nằm ngoài miền của nó.
5. Bộ so sánh riêng khiến `floor("BEE")` và `ceiling("BEE")` trả đại diện `"Bee"`.
6. Các truy vấn chuỗi không sửa tập.

Hai chương trình độc lập trong bài đã được biên dịch bằng `--release 17` và chạy đối chiếu đúng stdout. Tùy chọn này kiểm tra mức ngôn ngữ/API và tạo bytecode tương thích Java 17; nó không khẳng định JVM thực thi chính là JDK 17.

## 10. Chọn phương thức bằng cách viết rõ yêu cầu

Thay vì học thuộc tên rời rạc, hãy chuyển câu hỏi thành một bất đẳng thức và xác định phía cần chọn.

| Câu hỏi trên các số tăng dần | Điều kiện | Phương thức |
| --- | --- | --- |
| Giá trị trước đó, bỏ qua giá trị hiện tại | `candidate < target`, chọn lớn nhất | `lower` |
| Giá trị lớn nhất không vượt mức giới hạn | `candidate <= limit`, chọn lớn nhất | `floor` |
| Cỡ nhỏ nhất đủ đáp ứng yêu cầu | `candidate >= request`, chọn nhỏ nhất | `ceiling` |
| Giá trị tiếp theo phải lớn hơn hiện tại | `candidate > current`, chọn nhỏ nhất | `higher` |

Ví dụ tập độ rộng hỗ trợ `[320, 640, 960, 1280]`:

- Yêu cầu tối thiểu `700`: `ceiling(700)` chọn `960`.
- Giới hạn tối đa `700`: `floor(700)` chọn `640`.
- Cỡ lớn hơn hẳn `640`: `higher(640)` chọn `960`.
- Cỡ nhỏ hơn hẳn `640`: `lower(640)` chọn `320`.

Nếu không có cỡ đáp ứng, kết quả là `null`; chương trình cần một nhánh xử lý yêu cầu không được đáp ứng, không tự giả định phần tử lớn nhất luôn đủ.

### 10.1. Không mô phỏng quan hệ chặt bằng cộng hoặc trừ 1

Đừng mặc định thay `lower(x)` bằng `floor(x - 1)` hoặc `higher(x)` bằng `ceiling(x + 1)`.

Cách đó phụ thuộc miền số nguyên rời rạc, có thể gặp biên tràn số, và không áp dụng cho chuỗi hoặc một bộ so sánh miền khác. Các phương thức chặt đã biểu đạt đúng ý nghĩa mà không cần chế tạo một ngưỡng khác.

### 10.2. Đây không phải phép làm tròn Math.floor

`floor(25)` trên tập `[10, 20, 30, 40]` trả về phần tử `20` đã tồn tại. Nó không thực hiện phép làm tròn số học để tạo ra một số nguyên từ giá trị thực.

Tương tự, `ceiling` của tập không sinh một phần tử mới. Nó chọn một đại diện đang có đáp ứng quan hệ.

### 10.3. Không phương thức nào tự chọn gần nhất theo khoảng cách tuyệt đối

Với tập `[20, 30]`, ngưỡng `29`:

```text
floor(29)   = 20
ceiling(29) = 30
```

`30` gần `29` hơn theo khoảng cách số học, nhưng `floor` vẫn phải trả phía không vượt ngưỡng.

Nếu yêu cầu là gần nhất theo khoảng cách, thường cần lấy ứng viên hai phía rồi so khoảng cách, xử lý thiếu một phía và quy tắc khi bằng khoảng cách. Đó là một thuật toán bổ sung, không phải nghĩa mặc định của `floor` hoặc `ceiling`.

Với các kiểu không có thước đo khoảng cách tự nhiên như mã chuỗi, “gần nhất” cần được định nghĩa theo yêu cầu, không suy ra chỉ từ việc đã có một thứ tự.

## 11. Cơ chế tìm và chi phí cần hiểu tới đâu?

`TreeSet` dựa trên cây có thứ tự từ `TreeMap`. Có thể hiểu phép tìm `floor` như việc thu hẹp dần vùng tìm, đồng thời giữ ứng viên tốt nhất đã thấy ở phía không vượt ngưỡng.

Nếu gặp giá trị bằng ngưỡng theo so sánh, một phép có lấy bằng có thể trả ứng viên đó. Với phép chặt, vẫn phải tìm phía trước hoặc sau thay vì nhận trường hợp bằng.

Phân tích triển khai cây cân bằng của `TreeSet` cho các phép tìm lân cận có số bước theo chiều cao cây, thường được mô tả là O(log n) phép so sánh. Đây là phân tích gắn với cấu trúc triển khai, không phải cam kết một thời gian tuyệt đối hoặc điều kiện bắt buộc cho mọi lớp có giao diện `NavigableSet`. Chi phí của từng phép so sánh cũng cần được xét nếu khóa phức tạp. [TreeMap: cấu trúc cây nền](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html), [Mã nguồn TreeMap OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/TreeMap.java)

Khi đã có một `NavigableSet` phù hợp, không cần chuyển cả tập thành danh sách rồi quét toàn bộ cho từng lần tìm ngưỡng. Cũng không thêm thử đối số để suy ra phần tử cạnh nó, vì bốn phương thức đã là phép đọc trực tiếp.

Các kết quả phụ thuộc vào trạng thái hiện tại của tập. Nhiều lời gọi riêng biệt không tự tạo thành một ảnh chụp nguyên tử nếu chương trình cho phép bên khác sửa dữ liệu xen giữa. Các ví dụ trong bài xét một tập ổn định trong lúc truy vấn.

## 12. Những lỗi thường gặp

| Cách hiểu hoặc cách viết | Vấn đề | Cách sửa |
| --- | --- | --- |
| Nghĩ lower và floor luôn giống nhau | Bỏ qua trường hợp ngưỡng đã có phần tử tương đương | Kiểm tra dấu bằng có được lấy không |
| Dùng ceiling để tìm phần tử sau hiện tại | Có thể nhận lại chính phần tử hiện tại | Dùng higher nếu cần quan hệ chặt |
| Chỉ truy vấn ngưỡng sau khi contains trả true | Ngưỡng không bắt buộc thuộc tập | Gọi trực tiếp phương thức điều hướng |
| Mong floor trả một phần tử bất kỳ nhỏ hơn | Bỏ qua yêu cầu chọn ứng viên lớn nhất ở phía đó | Xác định cả điều kiện và cực trị |
| Gán kết quả trực tiếp vào int | Có thể tự mở hộp null và ném ngoại lệ | Nhận Integer, xử lý trường hợp không có |
| Thấy null rồi kết luận tập rỗng | Có thể chỉ thiếu ứng viên ở một phía hoặc trong một view | Kiểm tra miền và hướng truy vấn |
| Giữ suy nghĩ số tăng dần khi dùng descendingSet | Hướng quan hệ đã đảo | Đọc theo thứ tự của khung nhìn |
| Nghĩ floor trả đúng đối tượng truy vấn | Nó trả đại diện đang lưu theo quy tắc so sánh | Xét Comparator và compare bằng 0 |
| Mong khung nhìn giới hạn tìm ra ngoài phạm vi | Ứng viên phải thuộc miền khung nhìn | Gọi đúng tập nhận truy vấn |
| Dùng floor để chọn gần nhất tuyệt đối | Chỉ chọn phía không vượt ngưỡng | Lấy hai phía rồi áp dụng thước đo nếu cần |
| Cộng/trừ 1 để thay lower/higher | Không tổng quát và có thể gặp biên số | Dùng đúng phương thức |
| Tưởng truy vấn đã lấy và xóa phần tử | Bốn phương thức này là phép đọc | Dùng thao tác sửa đổi riêng khi thực sự cần |

Trước một kết quả bất ngờ, hãy kiểm tra: tập nào đang nhận lời gọi, thứ tự nào đang dùng, ngưỡng có trường hợp tương đương không, phía cần tìm có lấy bằng không, và ứng viên có bị loại bởi miền của một khung nhìn không.

## 13. Tự luyện và đối chiếu

### Bài 1: phân biệt dấu bằng

Cho `NavigableSet<Integer>` theo thứ tự tự nhiên chứa `[5, 12, 18, 27]`.

Điền kết quả:

| Ngưỡng | lower | floor | ceiling | higher |
| --- | --- | --- | --- | --- |
| `12` | ? | ? | ? | ? |
| `15` | ? | ? | ? | ? |
| `4` | ? | ? | ? | ? |
| `30` | ? | ? | ? | ? |

Đối chiếu:

| Ngưỡng | lower | floor | ceiling | higher |
| --- | --- | --- | --- | --- |
| `12` | `5` | `12` | `12` | `18` |
| `15` | `12` | `12` | `18` | `18` |
| `4` | `null` | `null` | `5` | `5` |
| `30` | `27` | `27` | `null` | `null` |

### Bài 2: đảo thứ tự

Lấy khung nhìn giảm dần của tập bài 1. Dự đoán bốn kết quả với ngưỡng `15`.

Đối chiếu:

```text
lower(15)   = 18
floor(15)   = 18
ceiling(15) = 12
higher(15)  = 12
```

Giải thích bằng thứ tự giảm dần, không chỉ nhớ máy móc bốn con số.

### Bài 3: chọn theo yêu cầu

Tập cỡ hỗ trợ là `[100, 250, 500]`:

1. Cỡ nhỏ nhất ít nhất bằng `200`: `ceiling(200)` → `250`.
2. Cỡ lớn nhất không vượt `200`: `floor(200)` → `100`.
3. Cỡ tiếp theo lớn hơn hẳn `250`: `higher(250)` → `500`.
4. Cỡ nhỏ hơn hẳn `100`: `lower(100)` → `null`.

Câu cuối cần một nhánh không có kết quả, không phải một giá trị số thay thế ngầm định.

### Bài 4: giải thích một lỗi mở hộp

Với tập bài 1, đoạn:

```java
int result = values.ceiling(30);
```

có thể ném `NullPointerException` vì `ceiling(30)` không có ứng viên và trả `null`. Hãy sửa bằng một biến `Integer` và một nhánh kiểm tra trước khi sử dụng như `int`.

### Bài 5: phân biệt phạm vi tìm

Tập gốc là `[5, 12, 18, 27]`, khung nhìn chỉ chứa `[12, 18]`.

`floor(25)` trên hai đối tượng đều là `18`, nhưng `ceiling(20)` trên tập gốc là `27`, còn trên khung nhìn không có ứng viên nên là `null`.

Điều cần giải thích là miền ứng viên, không phải nói ngưỡng ngoài tập luôn làm phương thức lỗi.

## 14. Tài liệu tra cứu

- [NavigableSet Java 17 — bốn phép tìm, khung nhìn và giá trị null](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableSet.html)
- [TreeSet Java 17 — triển khai tập có thứ tự và Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)
- [Comparator — quy tắc thứ tự và tính nhất quán với equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)
- [TreeMap — cấu trúc cây nền để hiểu cơ chế tìm](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html)
