# subSet, headSet, tailSet và cờ bao gồm biên

## 1. Lấy một khoảng theo thứ tự của NavigableSet

`NavigableSet<E>` duy trì phần tử theo thứ tự tự nhiên hoặc theo một `Comparator`. Khi chỉ cần làm việc với một đoạn của tập hợp, ba phương thức sau diễn đạt trực tiếp phạm vi cần dùng:

- `subSet`: phần nằm giữa hai mốc.
- `headSet`: phần đứng trước một mốc.
- `tailSet`: phần đứng sau một mốc.

Ví dụ một tập mã số có thứ tự `[20, 40, 60, 80, 100]`. Nếu muốn xem mã từ 40 đến 80, cần quyết định rõ: **có lấy 40 không, có lấy 80 không?** Hai cờ boolean trong overload của `NavigableSet` trả lời chính xác hai câu hỏi đó.

Kết quả là một **khung nhìn theo khoảng** (range view) của tập hợp gốc. Hiểu cả điều kiện biên và việc dùng chung dữ liệu là cần thiết trước khi thêm, xóa hoặc truyền kết quả cho nơi khác. Các API này vẫn được dùng trong Java hiện hành; xem [NavigableSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableSet.html).

## 2. Chữ ký và cách đọc từng đối số

```java
NavigableSet<E> subSet(E fromElement, boolean fromInclusive,
                       E toElement, boolean toInclusive);

NavigableSet<E> headSet(E toElement, boolean inclusive);

NavigableSet<E> tailSet(E fromElement, boolean inclusive);
```

Đây là chữ ký minh họa API, không phải chương trình độc lập.

`true` nghĩa là **cho phép phần tử bằng mốc tham gia khoảng**; `false` nghĩa là **loại điểm bằng mốc**. Nó không có nghĩa là đảo thứ tự hoặc bắt đầu/kết thúc việc lọc.

Với thứ tự tự nhiên của số nguyên:

| Lời gọi | Điều kiện phần tử x |
| --- | --- |
| `subSet(a, true, b, true)` | `a <= x && x <= b` |
| `subSet(a, true, b, false)` | `a <= x && x < b` |
| `subSet(a, false, b, true)` | `a < x && x <= b` |
| `subSet(a, false, b, false)` | `a < x && x < b` |
| `headSet(b, true)` | `x <= b` |
| `headSet(b, false)` | `x < b` |
| `tailSet(a, true)` | `x >= a` |
| `tailSet(a, false)` | `x > a` |

Dấu `[` hoặc `]` biểu thị có bao gồm biên; dấu `(` hoặc `)` biểu thị không bao gồm. Ví dụ `[40, 80)` tương ứng `subSet(40, true, 80, false)`.

Các điều kiện này phải hiểu theo comparator nếu tập hợp dùng thứ tự riêng. Hợp đồng và ý nghĩa tham số được mô tả tại [NavigableSet.subSet/headSet/tailSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableSet.html).

### Mốc không cần tồn tại trong tập hợp

Với dữ liệu `[20, 40, 60, 80, 100]`, `subSet(25, true, 75, true)` trả về `[40, 60]`. Mốc chỉ định điều kiện phạm vi, không yêu cầu có sẵn 25 hay 75.

Cờ `true` cũng không tự thêm một giá trị biên còn thiếu. Nếu cần thêm giá trị, đó là một thao tác sửa dữ liệu riêng.

## 3. Overload không có cờ dùng quy ước nào?

Các overload kế thừa từ `SortedSet` vẫn hợp lệ và có quy ước cố định:

| Lời gọi ngắn | Tương đương |
| --- | --- |
| `subSet(a, b)` | `subSet(a, true, b, false)` |
| `headSet(b)` | `headSet(b, false)` |
| `tailSet(a)` | `tailSet(a, true)` |

Như vậy `subSet(a, b)` là khoảng nửa mở `[a, b)`; `headSet` mặc định loại biên, còn `tailSet` mặc định gồm biên. Không nên nhớ rằng tất cả overload ngắn đều có chung một giá trị boolean mặc định. Xem [SortedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html).

Qua kiểu biến `NavigableSet<E>`, các overload không có cờ được khai báo trả về `SortedSet<E>`. Nếu cần giữ các phương thức điều hướng trên kết quả trong mã gọi, dùng overload có cờ:

```java
// set la NavigableSet<Integer>.
NavigableSet<Integer> range = set.subSet(40, true, 80, false);
```

Không cần ép kiểu chỉ để khôi phục khả năng điều hướng.

## 4. Ví dụ đầy đủ chạy trên Java 17+

Lưu tệp `NavigableSetRangeDemo.java`:

```java
import java.util.List;
import java.util.NavigableSet;
import java.util.SortedSet;
import java.util.TreeSet;

public class NavigableSetRangeDemo {
    private static void expectRangeError(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + ": missing exception");
        } catch (IllegalArgumentException expected) {
            System.out.println(label + "=IllegalArgumentException");
        }
    }

    public static void main(String[] args) {
        NavigableSet<Integer> set =
                new TreeSet<>(List.of(20, 40, 60, 80, 100));

        System.out.println("[40,80]=" + set.subSet(40, true, 80, true));
        System.out.println("[40,80)=" + set.subSet(40, true, 80, false));
        System.out.println("(40,80]=" + set.subSet(40, false, 80, true));
        System.out.println("(40,80)=" + set.subSet(40, false, 80, false));
        System.out.println("<60=" + set.headSet(60, false));
        System.out.println("<=60=" + set.headSet(60, true));
        System.out.println(">60=" + set.tailSet(60, false));
        System.out.println(">=60=" + set.tailSet(60, true));
        System.out.println("[25,75]=" + set.subSet(25, true, 75, true));
        System.out.println("[40,40]=" + set.subSet(40, true, 40, true));
        System.out.println("[40,40)=" + set.subSet(40, true, 40, false));

        SortedSet<Integer> defaultRange = set.subSet(40, 80);
        System.out.println("default subset=" + defaultRange);
        System.out.println("default head=" + set.headSet(60));
        System.out.println("default tail=" + set.tailSet(60));

        NavigableSet<Integer> live = set.subSet(40, true, 80, false);
        live.add(50);
        System.out.println("base after view add=" + set);
        set.add(70);
        System.out.println("view after base add=" + live);
        System.out.println("remove outside view=" + live.remove(100));
        expectRangeError("add excluded upper", () -> live.add(80));
        expectRangeError("reversed bounds",
                () -> set.subSet(80, true, 40, true));
        expectRangeError("nested outside bounds",
                () -> live.subSet(20, true, 60, true));

        NavigableSet<Integer> copy = new TreeSet<>(live);
        live.clear();
        System.out.println("base after view clear=" + set);
        System.out.println("copy after view clear=" + copy);
        set.add(55);
        System.out.println("view after later add=" + live);

        NavigableSet<Integer> descending = set.descendingSet();
        System.out.println("descending=" + descending);
        System.out.println("descending [100,20)="
                + descending.subSet(100, true, 20, false));
        System.out.println("descending head(80,true)="
                + descending.headSet(80, true));
        System.out.println("descending tail(80,false)="
                + descending.tailSet(80, false));
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```shell
javac -encoding UTF-8 NavigableSetRangeDemo.java
java NavigableSetRangeDemo
```

Kết quả chính xác:

```text
[40,80]=[40, 60, 80]
[40,80)=[40, 60]
(40,80]=[60, 80]
(40,80)=[60]
<60=[20, 40]
<=60=[20, 40, 60]
>60=[80, 100]
>=60=[60, 80, 100]
[25,75]=[40, 60]
[40,40]=[40]
[40,40)=[]
default subset=[40, 60]
default head=[20, 40]
default tail=[60, 80, 100]
base after view add=[20, 40, 50, 60, 80, 100]
view after base add=[40, 50, 60, 70]
remove outside view=false
add excluded upper=IllegalArgumentException
reversed bounds=IllegalArgumentException
nested outside bounds=IllegalArgumentException
base after view clear=[20, 80, 100]
copy after view clear=[40, 50, 60, 70]
view after later add=[55]
descending=[100, 80, 55, 20]
descending [100,20)=[100, 80, 55]
descending head(80,true)=[100, 80]
descending tail(80,false)=[55, 20]
```

## 5. Khung nhìn đang hoạt động, không phải bản sao

Trong chương trình:

```java
NavigableSet<Integer> live = set.subSet(40, true, 80, false);
```

`live` đại diện cho khoảng `[40, 80)` trong cùng dữ liệu nền với `set`.

- `live.add(50)` thêm 50 vào cả tập gốc.
- `set.add(70)` làm 70 xuất hiện trong khung nhìn vì nằm trong khoảng.
- `live.remove(100)` trả `false` trong ví dụ `TreeSet`: 100 có trong tập gốc nhưng nằm ngoài phạm vi mà khung nhìn thấy.
- `live.clear()` xóa các phần tử thuộc khoảng khỏi tập gốc. Nó không xóa 20, 80 và 100.
- Sau khi đã clear, `set.add(55)` khiến `live` lại chứa 55. Khung nhìn vẫn giữ phạm vi `[40, 80)`.

Đây là quan hệ dữ liệu hai chiều, không phải thao tác chạy lại một bộ lọc và lưu kết quả cũ. Hợp đồng dùng chung dữ liệu và các giới hạn thêm phần tử được xác nhận tại [TreeSet: các khung nhìn theo khoảng](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html).

### Khi cần dữ liệu độc lập

Chương trình tạo bản sao trước khi xóa:

```java
NavigableSet<Integer> copy = new TreeSet<>(live);
```

Constructor nhận `SortedSet` giữ cùng thứ tự với nguồn. Khi `live.clear()` thay đổi tập gốc, `copy` vẫn giữ `[40, 50, 60, 70]`. Tập sao chép độc lập về cấu trúc, nhưng nếu phần tử là đối tượng có thể thay đổi thì các tham chiếu phần tử vẫn có thể dùng chung. Xem [constructor TreeSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html).

Bản sao này không tự giữ lại ràng buộc khoảng của `live`: nó là một `TreeSet` mới gồm các phần tử đã sao chép. Nếu sau đó thêm một giá trị ngoài khoảng cũ nhưng hợp lệ với comparator, tập sao chép không từ chối chỉ vì giá trị ấy từng nằm ngoài khoảng.

## 6. Phạm vi hợp lệ và lỗi biên

### Thêm vào điểm bị loại không chỉ “không hiện ra”

Với `live = set.subSet(40, true, 80, false)`, 80 là biên trên bị loại. `live.add(80)` ném `IllegalArgumentException`. Nó không âm thầm thêm vào tập gốc rồi ẩn khỏi khung nhìn.

Tương tự, `live.add(30)` nằm dưới biên và cũng không hợp lệ. Hãy phân biệt thao tác **thêm qua khung nhìn bị giới hạn** với thao tác thêm trực tiếp vào tập gốc: `set.add(30)` có thể hợp lệ, nhưng 30 không xuất hiện trong `live`.

### from phải đứng trước hoặc bằng to theo thứ tự tập hợp

Với thứ tự tự nhiên, `subSet(80, true, 40, true)` ném `IllegalArgumentException`. Hai cờ boolean không sửa được việc đảo hai mốc.

Khi lấy tiếp một khoảng từ khung nhìn đã bị giới hạn, không được mở rộng ra ngoài phạm vi cha. Ví dụ `live.subSet(20, true, 60, true)` vượt dưới biên 40 nên lỗi. Đây không phải phép tự động lấy giao rồi bỏ qua phần ngoài.

Nếu mốc trùng với biên bị loại của khoảng cha, còn phải xét cờ có yêu cầu bao gồm điểm ấy hay không. Khi lồng nhiều khoảng, hãy viết rõ điều kiện của từng tầng thay vì chỉ nhìn giá trị số của hai mốc.

### Hai mốc bằng nhau

Nếu hai mốc bằng nhau theo phép so sánh:

- Cả hai cờ đều `true`: khoảng cho phép các phần tử so sánh bằng mốc đó. Với một set hợp lệ, có tối đa một đại diện.
- Có ít nhất một cờ `false`: khoảng rỗng.

Trong ví dụ, `subSet(40, true, 40, true)` là `[40]`; `subSet(40, true, 40, false)` là `[]`. Nếu tập gốc chưa có 40, ngay cả khoảng đóng `[40, 40]` cũng chưa có phần tử; nó không tự tạo 40.

Các điều kiện về mốc, khoảng lồng nhau và ngoại lệ được mô tả tại [NavigableSet.subSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableSet.html).

## 7. Comparator đảo làm đổi cách hiểu head và tail

Sau các thay đổi trong ví dụ, tập gốc là `[20, 55, 80, 100]`. Khung nhìn ngược thấy `[100, 80, 55, 20]`.

Trong thứ tự này:

- `subSet(100, true, 20, false)` đi từ 100 đến trước 20, nhận `[100, 80, 55]`.
- `headSet(80, true)` lấy phần đứng trước hoặc bằng 80 theo thứ tự đảo, nhận `[100, 80]`.
- `tailSet(80, false)` lấy phần đứng sau 80 theo thứ tự đảo, nhận `[55, 20]`.

Không áp dụng máy móc điều kiện số học `x < 80` cho `headSet(80, false)` khi comparator đã đảo. “Nhỏ hơn”, “lớn hơn”, “trước” và “sau” của API đều gắn với thứ tự đang dùng. Xem [NavigableSet.descendingSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableSet.html).

Một cách tự kiểm tra dễ hiểu là viết ra thứ tự duyệt của set trước, rồi đánh dấu hai mốc theo thứ tự ấy. Với tập ngược, lời gọi `subSet(20, true, 100, true)` lại bị đảo mốc theo comparator, dù 20 nhỏ hơn 100 theo số học.

## 8. Áp dụng vào yêu cầu thực tế

### Chia các khoảng liền nhau

Khoảng nửa mở `[a, b)` hữu ích khi chia dữ liệu thành nhiều đoạn: `[0, 100)`, `[100, 200)`, `[200, 300)`. Giá trị 100 thuộc đoạn thứ hai, không bị tính hai lần.

Đối với ngày tháng, có thể dùng `NavigableSet<LocalDate>` và lấy dữ liệu từ ngày đầu đến trước ngày cuối bằng `subSet(start, true, end, false)`. Cần hiểu đúng yêu cầu “đến hết ngày” hay “trước ngày” trước khi chọn cờ.

### Xóa theo khoảng

Khi chủ động muốn xóa dữ liệu trong một khoảng, `set.subSet(...).clear()` diễn đạt trực tiếp mục tiêu. Nhưng nếu chỉ đang tính toán hoặc hiển thị dữ liệu, không gọi `clear()` trên kết quả với suy nghĩ đó là một tập tạm.

### Mốc không phải chỉ số

`subSet(20, true, 80, false)` không có nghĩa “phần tử từ vị trí 20 đến vị trí 79”. Hai mốc là **giá trị được so sánh**. `NavigableSet` không cung cấp truy cập chỉ số như `List`.

## 9. Lưu ý và cách kiểm thử

- Biên phải so sánh được với dữ liệu theo comparator. Mốc không hợp lệ về kiểu hoặc `null` không được hỗ trợ có thể gây ngoại lệ; ví dụ `TreeSet` theo thứ tự tự nhiên không dùng `null` làm mốc.
- Khung nhìn của `TreeSet` không tạo cơ chế an toàn đa luồng mới. Không sửa qua tập gốc trong lúc iterator trên khung nhìn đang duyệt rồi dựa vào may mắn.
- Một phương thức nhận khung nhìn và xóa phần tử có thể làm thay đổi dữ liệu của nơi gọi. Khi truyền dữ liệu qua ranh giới thành phần, cần xác định rõ có cho phép sửa dữ liệu gốc không.
- Không giả định mọi thao tác trên khoảng đều có cùng độ phức tạp hoặc chi phí như đọc một biến. Việc tạo khung nhìn và việc duyệt toàn bộ phần tử là hai loại công việc khác nhau.

Các ca kiểm thử nên gồm: bốn tổ hợp cờ; mốc có sẵn và chưa có sẵn; hai mốc bằng nhau; khoảng không chứa phần tử; thêm trong/ngoài khoảng; thay đổi qua tập gốc; `clear()`; và comparator đảo. Với thao tác sửa, kiểm tra cả khung nhìn lẫn tập gốc, không chỉ giá trị trả về.

## 10. Thực hành

1. Với `[10, 20, 30, 40, 50]`, dự đoán bốn kết quả `subSet(20, ..., 40, ...)` trước khi chạy.
2. Tạo hai khung nhìn `headSet(30, false)` và `tailSet(30, true)`. Chứng minh rằng 30 chỉ thuộc phía sau và hai phạm vi không chồng nhau.
3. Tạo `subSet(20, false, 40, false)`, thêm 25 qua khung nhìn rồi thêm 35 qua tập gốc. Đối chiếu dữ liệu ở cả hai biến.
4. Sao chép khoảng bằng `new TreeSet<>(range)`, xóa khoảng gốc, rồi xác nhận bản sao còn dữ liệu. Thử thêm một giá trị ngoài khoảng cũ vào bản sao và giải thích kết quả.
5. Đổi sang `descendingSet()`, viết lại các mốc sao cho hợp lệ theo thứ tự đảo và dự đoán kết quả `headSet/tailSet` bằng thứ tự duyệt.
