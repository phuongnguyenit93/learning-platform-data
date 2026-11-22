# Tạo EnumSet bằng noneOf, allOf, of và range

## 1. Chọn tập ban đầu theo ý nghĩa cần biểu đạt

`EnumSet<E>` là một implementation của `Set` chuyên dùng cho các hằng thuộc **cùng một kiểu enum**. Nó không giữ phần tử trùng lặp, không cho thêm `null` và duyệt theo thứ tự khai báo của các hằng enum.

Khi tạo tập, bốn factory sau mô tả bốn ý định khác nhau:

| Factory | Tập ban đầu | Khi nên dùng |
| --- | --- | --- |
| `noneOf(Day.class)` | Không có phần tử, nhưng biết kiểu enum là `Day` | Bắt đầu rỗng rồi bổ sung theo điều kiện |
| `allOf(Day.class)` | Có mọi hằng của `Day` | Thực sự muốn toàn bộ miền giá trị enum |
| `of(Day.MONDAY, Day.FRIDAY)` | Có các hằng được chỉ định | Chọn một nhóm cụ thể, có thể không liền nhau |
| `range(Day.MONDAY, Day.FRIDAY)` | Có mọi hằng từ đầu đến cuối theo thứ tự khai báo, gồm cả hai đầu | Chọn một đoạn liên tiếp có ý nghĩa trong enum |

Bài dùng enum mẫu:

```java
enum Day {
    MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY
}
```

Các đoạn ngắn cần được đặt trong một phương thức có thể dùng enum này và import `java.util.EnumSet`. Chương trình đầy đủ bên dưới chạy với Java 17 trở lên; các factory này đều là API còn áp dụng trong Java hiện hành.

## 2. noneOf: tập rỗng có kiểu, không phải null

```java
EnumSet<Day> selected = EnumSet.noneOf(Day.class);
System.out.println(selected.isEmpty()); // true
selected.add(Day.WEDNESDAY);
System.out.println(selected); // [WEDNESDAY]
```

`noneOf` trả về một tập rỗng thật sự. Có thể gọi `size`, `contains`, `add` hoặc duyệt nó mà không cần xử lý như một tham chiếu null.

`Day.class` chỉ rõ kiểu phần tử ngay cả khi tập chưa có hằng nào để suy ra kiểu. Tập rỗng vẫn chỉ cho phép thêm các hằng của `Day`; không thể thêm một enum khác chỉ vì tập chưa có dữ liệu.

Khai báo `<Day>` ở biến là thông tin kiểm tra kiểu, còn đối số `Day.class` cũng cung cấp thông tin kiểu enum cho factory lúc chạy. Không thay đối số ấy bằng chuỗi `"Day"` hoặc bằng một hằng enum đơn lẻ.

Không gọi `new EnumSet<Day>()`: lớp này được thiết kế để tạo qua các factory phù hợp, không phải bằng một constructor công khai thông thường.

`noneOf` phù hợp khi các phần tử phụ thuộc điều kiện:

```java
EnumSet<Day> meetingDays = EnumSet.noneOf(Day.class);
boolean includeMonday = true;
boolean includeFriday = false;
if (includeMonday) {
    meetingDays.add(Day.MONDAY);
}
if (includeFriday) {
    meetingDays.add(Day.FRIDAY);
}
```

Cách tạo này diễn đạt rõ rằng không ngày nào được chọn mặc định; từng điều kiện bổ sung lựa chọn của mình.

## 3. allOf: toàn bộ hằng của một kiểu enum

```java
EnumSet<Day> everyDay = EnumSet.allOf(Day.class);
System.out.println(everyDay.size()); // 7
```

`allOf` tạo tập ban đầu chứa mọi hằng của kiểu enum được cung cấp. Nó không thêm `null`, không tạo các giá trị enum mới và không yêu cầu một giá trị cụ thể làm mẫu.

Tập kết quả vẫn có thể thay đổi:

```java
everyDay.remove(Day.SUNDAY);
System.out.println(everyDay.contains(Day.SUNDAY)); // false
```

Lệnh xóa làm thay đổi tập `everyDay`, không xóa hằng `SUNDAY` khỏi định nghĩa enum. Một lời gọi `EnumSet.allOf(Day.class)` mới vẫn tạo được tập đầy đủ.

Vì `allOf` diễn đạt “mọi hằng”, khi mã nguồn enum được bổ sung một hằng mới và chương trình dùng định nghĩa enum mới, tập tạo bằng `allOf` bao gồm hằng ấy. Nếu yêu cầu thật sự là một nhóm cố định đã duyệt, dùng `of` liệt kê nhóm đó sẽ thể hiện hợp đồng khác rõ ràng hơn.

Đối với một enum không khai báo hằng nào, `allOf` cho một tập rỗng hợp lệ. “Toàn bộ” có thể là không có phần tử; nó không có nghĩa factory trả về null.

## 4. of: liệt kê các hằng cần có

```java
EnumSet<Day> selected = EnumSet.of(Day.FRIDAY, Day.MONDAY, Day.FRIDAY);
System.out.println(selected); // [MONDAY, FRIDAY]
System.out.println(selected.size()); // 2
```

Hai chi tiết được thể hiện cùng lúc:

1. `FRIDAY` được truyền hai lần nhưng chỉ xuất hiện một lần vì đây là `Set`.
2. Thứ tự duyệt là thứ tự khai báo enum, nên `MONDAY` đứng trước `FRIDAY`, không theo thứ tự đối số của `of`.

Dùng `of` cho một hằng hoặc nhiều hằng:

```java
EnumSet<Day> oneDay = EnumSet.of(Day.TUESDAY);
EnumSet<Day> weekend = EnumSet.of(Day.SATURDAY, Day.SUNDAY);
```

API có các overload với số đối số cố định và một dạng varargs nhận phần còn lại, nên không có giới hạn chỉ được chọn tối đa năm hằng. Tuy nhiên, không có lời gọi `EnumSet.of()` không đối số để tạo tập rỗng; dùng `noneOf(Day.class)` cho trường hợp ấy.

Một hằng được truyền vào giúp xác định kiểu enum cho factory. Không trộn hằng từ hai enum khác nhau trong lời gọi có kiểu đúng; chúng không cùng thỏa một kiểu phần tử `E` của `EnumSet<E>`.

Tên `of` không có nghĩa kết quả bất biến. `EnumSet.of(...)` tạo một tập có thể thay đổi, khác với hợp đồng không cho sửa của các factory như `Set.of(...)` trong thư viện hiện hành. Đọc đúng lớp sở hữu factory, không suy ra hành vi chỉ từ cùng một tên phương thức.

## 5. range: đoạn liên tiếp, gồm cả hai đầu

```java
EnumSet<Day> workweek = EnumSet.range(Day.MONDAY, Day.FRIDAY);
System.out.println(workweek);
// [MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY]
```

`range(from, to)` dùng **thứ tự khai báo enum**, không dùng thứ tự chữ cái của tên hằng. Nó bao gồm `from`, `to` và mọi hằng nằm giữa hai vị trí ấy.

Nếu hai đầu giống nhau, tập có một phần tử:

```java
EnumSet<Day> midpoint = EnumSet.range(Day.WEDNESDAY, Day.WEDNESDAY);
System.out.println(midpoint); // [WEDNESDAY]
```

Không có yêu cầu phải thêm từng phần tử bằng tay. Factory xác định đoạn theo kiểu enum mà hai đầu mút thuộc về.

### Đầu và cuối không được đảo ngược

```java
// Chạy sẽ ném IllegalArgumentException:
// EnumSet<Day> invalid = EnumSet.range(Day.FRIDAY, Day.MONDAY);
```

Trong enum mẫu, `FRIDAY` được khai báo sau `MONDAY`, nên không tạo được một đoạn tăng từ `FRIDAY` đến `MONDAY`. `range` không tự vòng qua cuối tuần để đi về đầu tuần.

Nếu yêu cầu là tập gồm thứ Sáu, thứ Bảy, Chủ nhật và thứ Hai, liệt kê rõ:

```java
EnumSet<Day> longWeekend = EnumSet.of(
        Day.FRIDAY, Day.SATURDAY, Day.SUNDAY, Day.MONDAY);
```

Tập ấy chứa đúng các ngày đã chọn, nhưng khi duyệt vẫn theo thứ tự enum: `MONDAY` rồi `FRIDAY`, `SATURDAY`, `SUNDAY`. Nếu cần một lịch trình bắt đầu từ thứ Sáu theo trình tự vòng tuần, một tập hợp thành viên không tự biểu đạt đầy đủ thứ tự lịch trình đó.

### Thứ tự enum là một phần ý nghĩa của range

Nếu chèn thêm hằng vào giữa hai đầu mút hoặc sắp xếp lại enum, kết quả của `range` có thể đổi. Chỉ dùng nó khi tính liên tiếp trong thứ tự khai báo thật sự mang ý nghĩa của nhóm cần chọn.

Với một nhóm rời rạc hoặc một quy tắc không nên tự mở rộng khi chèn hằng mới, dùng `of` có thể dễ kiểm tra hơn. Không dùng `range` chỉ để giảm số ký tự mà làm ẩn phụ thuộc vào thứ tự khai báo.

## 6. Chương trình chạy đầy đủ

Lưu thành **`EnumSetFactoriesDemo.java`**:

```java
import java.util.EnumSet;

public class EnumSetFactoriesDemo {
    enum Day {
        MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY
    }

    public static void main(String[] args) {
        EnumSet<Day> empty = EnumSet.noneOf(Day.class);
        System.out.println("none=" + empty);
        empty.add(Day.WEDNESDAY);
        System.out.println("after add=" + empty);

        EnumSet<Day> all = EnumSet.allOf(Day.class);
        System.out.println("all=" + all);

        EnumSet<Day> chosen = EnumSet.of(Day.FRIDAY, Day.MONDAY, Day.FRIDAY);
        System.out.println("of=" + chosen + ", size=" + chosen.size());

        EnumSet<Day> workweek = EnumSet.range(Day.MONDAY, Day.FRIDAY);
        System.out.println("range=" + workweek);
        System.out.println("single="
                + EnumSet.range(Day.WEDNESDAY, Day.WEDNESDAY));

        all.remove(Day.SUNDAY);
        System.out.println("modified all=" + all);
        System.out.println("fresh all contains Sunday="
                + EnumSet.allOf(Day.class).contains(Day.SUNDAY));

        try {
            EnumSet.range(Day.FRIDAY, Day.MONDAY);
        } catch (IllegalArgumentException ex) {
            System.out.println("reversed range rejected");
        }

        try {
            empty.add(null);
        } catch (NullPointerException ex) {
            System.out.println("null element rejected");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all EnumSetFactoriesDemo.java
java EnumSetFactoriesDemo
```

Stdout chính xác:

```text
none=[]
after add=[WEDNESDAY]
all=[MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY]
of=[MONDAY, FRIDAY], size=2
range=[MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY]
single=[WEDNESDAY]
modified all=[MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY]
fresh all contains Sunday=true
reversed range rejected
null element rejected
```

Các lần tạo tập là độc lập. Xóa `SUNDAY` khỏi biến `all` không làm thay đổi miền giá trị của enum hoặc một tập mới do factory khác trả về.

Kết quả in có thứ tự ổn định theo khai báo enum. Không cần tự sort theo tên hằng để thu được thứ tự ấy, và việc đổi thứ tự đối số `of` không đổi thứ tự duyệt đã được API quy định.

## 7. Các điều kiện đầu vào cần nắm

| Trường hợp | Hành vi cần dự kiến |
| --- | --- |
| `noneOf(Day.class)` | Tập rỗng kiểu `Day` |
| `allOf(Day.class)` | Tập chứa mọi hằng `Day` hiện có trong định nghĩa được dùng |
| `of` có phần tử trùng | Không tạo bản sao trùng trong tập |
| `range(a, a)` với hằng hợp lệ | Tập một phần tử |
| `range(from, to)` đảo thứ tự | `IllegalArgumentException` |
| Đầu mút range hoặc hằng đưa vào of là null | `NullPointerException` |
| Đối số Class của noneOf/allOf là null | `NullPointerException` |
| Thêm null vào tập | `NullPointerException` |

Đừng gom mọi thao tác có null thành một quy tắc duy nhất. `EnumSet` không cho chèn phần tử null, nhưng `contains(null)` và `remove(null)` vẫn thực hiện truy vấn hợp lệ và không tìm được một phần tử null để xử lý.

Với mã có kiểu đúng, giới hạn generic yêu cầu phần tử là hằng thuộc một enum phù hợp. Truyền một Class không phải enum bằng cách phá kiểm tra kiểu không phải cách sử dụng các factory được khuyến nghị; không cần bỏ thông tin generic để làm việc với các trường hợp trong bài.

## 8. Tập có thể thay đổi và quyền sở hữu

Cả bốn factory tạo các tập có thể dùng các thao tác thêm/xóa thích hợp. Nếu một đối tượng dịch vụ giữ một tập mặc định rồi trả lại chính tham chiếu ấy, bên gọi có thể làm thay đổi tập đang được chia sẻ.

Ví dụ minh họa một khai báo trường:

```java
private static final EnumSet<Day> DEFAULT_DAYS =
        EnumSet.of(Day.MONDAY, Day.FRIDAY);
```

`final` ngăn gán lại biến trường, không ngăn `DEFAULT_DAYS.clear()`. Vì vậy, khi thiết kế API, quyết định rõ trả bản sao, trả góc nhìn không cho sửa hay chia sẻ tập có thể thay đổi theo hợp đồng nào. Không nghĩ tên factory hoặc từ khóa `final` tự tạo ra bất biến của dữ liệu.

Trong phạm vi chỉ cần tạo một tập mới cho một lần xử lý, gọi factory theo ý định là cách trực tiếp và rõ ràng. Chỉ đưa cache hoặc chia sẻ tập vào thiết kế khi có yêu cầu cụ thể và hợp đồng quyền sở hữu phù hợp.

## 9. Chọn đúng factory qua các tình huống

- **Tập ngày họp được xây dựng dần:** `noneOf` rồi thêm các ngày đáp ứng điều kiện.
- **Một bộ xử lý cần chạy qua mọi ngày đã khai báo:** `allOf`.
- **Chỉ thứ Hai và thứ Sáu:** `of`, vì hai ngày không tạo thành một đoạn liên tiếp hai phần tử trong enum mẫu.
- **Mọi ngày từ thứ Hai đến thứ Sáu:** `range`, vì muốn toàn bộ các hằng nằm giữa.
- **Khoảng vòng từ thứ Sáu sang thứ Hai:** không có cơ chế vòng tự động trong `range`; xác định tập rõ hoặc dùng một mô hình lịch trình có thứ tự thích hợp.

Một kiểm tra nhanh hữu ích là hỏi “nếu ngày mai thêm hoặc đổi vị trí một hằng, tôi có muốn tập này tự thay đổi theo không?”. Câu trả lời giúp phân biệt ý định “mọi hằng”, “một đoạn theo thứ tự” và “đúng các hằng đã liệt kê”.

## 10. Tự thực hành

1. Tạo một `EnumSet<Day>` rỗng, thêm `FRIDAY` trước rồi `MONDAY` sau. Xác nhận thứ tự in vẫn theo khai báo enum.
2. Dùng `of` với ba đối số nhưng chỉ hai hằng khác nhau, rồi kiểm tra `size` và `contains`.
3. So sánh `of(MONDAY, FRIDAY)` với `range(MONDAY, FRIDAY)`. Liệt kê những ngày chỉ có ở tập thứ hai.
4. Thử hai đầu range giống nhau, đảo ngược và có null; phân biệt kết quả một phần tử với hai loại ngoại lệ.
5. Xóa một phần tử khỏi tập tạo bằng `allOf`, rồi tạo tập `allOf` mới. Giải thích vì sao định nghĩa enum không bị thay đổi.

Các factory của `EnumSet` diễn đạt tập khởi đầu chứ không chỉ là những cách viết thay thế cho nhau. Chọn theo thành viên, thứ tự khai báo và quyền thay đổi mong muốn giúp mã ngắn nhưng vẫn rõ ý nghĩa.

## Tài liệu đối chiếu

- [EnumSet — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumSet.html): kiểu phần tử, thứ tự duyệt và quy tắc null.
- [EnumSet.noneOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumSet.html#noneOf(java.lang.Class)), [EnumSet.allOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumSet.html#allOf(java.lang.Class)): tạo tập rỗng hoặc đầy đủ theo kiểu enum.
- [EnumSet.of](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumSet.html#of(E)): tạo tập từ các hằng được chỉ định.
- [EnumSet.range](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumSet.html#range(E,E)): đoạn có cả hai đầu và điều kiện thứ tự.
