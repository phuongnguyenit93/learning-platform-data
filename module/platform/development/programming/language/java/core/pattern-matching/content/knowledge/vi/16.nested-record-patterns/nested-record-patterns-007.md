# Scope của biến trong nested pattern (Java 21+)

## 1. Vì sao cần hiểu phạm vi biến mẫu?

Khi so khớp một record lồng nhau (*nested record pattern*), Java có thể tạo nhiều **biến mẫu** (*pattern variables*) chỉ bằng một biểu thức. Nhưng các biến này chỉ sử dụng được ở những đường thực thi mà trình biên dịch biết chắc **mẫu đã khớp**. Đây là cơ chế **phạm vi theo luồng điều khiển** (*flow scoping*), khác với việc một biến cục bộ thông thường xuất hiện trong cả khối lệnh sau điểm khai báo.

Xét hai kiểu dữ liệu:

~~~java
record Point(int x, int y) {}
record Segment(Point start, Point end) {}
~~~

Với:

~~~java
Object input = new Segment(new Point(1, 2), new Point(6, 8));

if (input instanceof Segment(
        Point(int sx, int sy),
        Point(int ex, int ey))) {
    System.out.println(ex - sx); // 5
}
~~~

- `Segment(...)` là record pattern ngoài cùng.
- Hai `Point(...)` là **record pattern lồng bên trong**, mỗi mẫu nhận một component `start` hoặc `end` của `Segment`.
- `sx`, `sy`, `ex`, `ey` là bốn **biến mẫu** được khai báo bởi các component pattern kiểu `int` trong hai mẫu `Point`.
- Các biến chỉ sử dụng được trong nhánh `if` khi **cả mẫu `Segment` và hai mẫu `Point` đều khớp**.

Tên `sx`, `sy` không cần trùng tên `x`, `y` của record: Java ghép các component **theo vị trí khai báo**, không theo tên biến mẫu. Record pattern được chuẩn hóa trong Java **21**, nên các ví dụ trong bài dùng JDK 21+.

## 2. Một mẫu lồng chỉ thành công khi toàn bộ mẫu con khớp

Biểu thức sau phải kiểm tra được record ngoài cùng và tất cả giá trị component liên quan:

~~~java
input instanceof Segment(
        Point(int sx, int sy),
        Point(int ex, int ey))
~~~

Nếu `input` là `null`, không phải `Segment`, hoặc `Segment` có `start` hay `end` bằng `null`, các mẫu `Point(...)` tương ứng sẽ không khớp; toàn bộ record pattern thất bại. Không có nhánh thực thi hợp lệ nào được dùng `sx`, `sy`, `ex`, `ey` khi mẫu ngoài cùng chưa khớp hoàn toàn.

Ngược lại, khi toàn bộ mẫu khớp, Java biết tất cả bốn biến có giá trị và kiểu phù hợp. Với `Point(var sx, var sy)`, kiểu suy ra của `sx` và `sy` vẫn là `int` vì các record component có kiểu `int`. Từ khóa `var` ở đây không tạo kiểu động.

Lưu ý: đây là **phạm vi sử dụng biến**, không phải tuổi thọ của record hay dữ liệu mà biến tham chiếu đến. Giá trị record vẫn có thể được giữ ở biến khác sau khi khối `if` kết thúc; tên biến mẫu thì chịu quy tắc phạm vi riêng.

## 3. Trong điều kiện `if`: nhánh đúng có biến, nhánh sai thì không

~~~java
if (input instanceof Segment(
        Point(int sx, int sy),
        Point(int ex, int ey))) {
    int dx = ex - sx;           // HỢP LỆ: mẫu đã khớp
    System.out.println(dx);
} else {
    System.out.println("Không khớp");
    // System.out.println(sx);  // LỖI: sx không thuộc phạm vi nhánh else
}
// System.out.println(ex);      // LỖI: các biến mẫu không còn thuộc phạm vi ở đây
~~~

Đây là **đoạn minh họa** dùng `input` và hai kiểu record đã định nghĩa ở trên. Những dòng chú thích “LỖI” minh họa cách dùng không được biên dịch; chúng được đặt trong comment để không ảnh hưởng mã hợp lệ.

Lý do: phía `else` có thể được chọn do đối tượng không phải `Segment` hoặc một mẫu `Point` con không khớp. Java không thể bảo đảm `sx` và `ex` đã được gán trên đường đi đó.

Không nên diễn giải rằng mọi tên được khai báo bên trong dấu ngoặc record pattern đều có phạm vi kéo dài đến hết phương thức. **Vị trí biểu thức mẫu và đường đi điều khiển** quyết định nơi tên đó có hiệu lực.

## 4. Toán tử `&&`: biến có thể dùng ở vế phải và trong nhánh đúng

Java đánh giá `a && b` từ trái sang phải và chỉ đánh giá `b` khi `a` đúng. Do đó, nếu `a` kiểm tra thành công nested record pattern, biến mẫu được dùng trong `b`:

~~~java
if (input instanceof Segment(
        Point(int sx, int sy),
        Point(int ex, int ey))
        && ex > sx) {
    System.out.println("Độ dịch chuyển ngang: " + (ex - sx));
}
~~~

`ex` và `sx` hợp lệ tại `ex > sx` vì Java chỉ tới vế phải sau khi mẫu bên trái đã khớp. Khi chạy với `input` ở ví dụ đầu, chương trình in `Độ dịch chuyển ngang: 5`.

Có thể dùng đồng thời nhiều biến từ các tầng lồng nhau:

~~~java
if (input instanceof Segment(
        Point(var sx, var sy),
        Point(var ex, var ey))
        && ex > sx
        && ey > sy) {
    System.out.println("Đi sang phải và lên trên");
}
~~~

Cả hai điều kiện phụ đều chỉ được xét khi record pattern khớp. Nhánh `if` chỉ chạy khi mẫu khớp và các điều kiện đi kèm đều đúng.

Đừng thay `&&` bằng `||` một cách máy móc:

~~~java
// SAI, không biên dịch: nếu mẫu bên trái thất bại,
// ex và sx không được bảo đảm đã gán ở vế phải.
if (input instanceof Segment(
        Point(int sx, int sy),
        Point(int ex, int ey))
        || ex > sx) {
    System.out.println("...");
}
~~~

Với `||`, vế phải được đánh giá khi vế trái **sai**, đúng vào lúc ta không biết các biến mẫu có được gán hay không. Đoạn này chỉ nhằm chỉ ra lỗi và **không nằm trong chương trình chạy được** ở phần sau.

## 5. Phủ định `!` và điều kiện thoát sớm

Phủ định có thể đảo nhánh được bảo đảm khớp. Một kỹ thuật rất hữu ích là **guard clause**: thoát khỏi phương thức ngay khi mẫu không khớp.

~~~java
static int horizontalDistanceOrMinusOne(Object input) {
    if (!(input instanceof Segment(
            Point(int sx, int sy),
            Point(int ex, int ey)))) {
        return -1;
    }

    // Tới đây, nhánh không khớp đã return,
    // nên compiler biết mẫu bắt buộc phải khớp.
    return ex - sx;
}
~~~

Đây là một **phương thức minh họa** đặt trong lớp có khai báo `Point` và `Segment`. Khác với ví dụ `if` đầu tiên, `sx` và `ex` **vẫn dùng được sau khối `if`**, vì mọi đường đi tới lệnh `return ex - sx` đều có điều kiện record pattern đã đúng. Nếu phương thức không thoát ở nhánh không khớp, không thể tự suy ra bảo đảm này.

Phủ định cũng có thể kết hợp `||` một cách hợp lệ:

~~~java
static int positiveDistanceOrMinusOne(Object input) {
    if (!(input instanceof Segment(
            Point(int sx, int sy),
            Point(int ex, int ey)))
            || ex <= sx) {
        return -1;
    }
    return ex - sx;
}
~~~

Ở đây, vế phải `ex <= sx` chỉ được đánh giá khi điều kiện phủ định bên trái **sai**, tức record pattern **đã khớp**. Vì vậy `ex` và `sx` có phạm vi hợp lệ ở vế phải. Sau `if`, những đường đi chưa khớp hoặc có `ex <= sx` đều đã trả về `-1`.

Đừng nhầm “có dấu `!` là biến bị mất” với quy tắc thật: Java phân tích **đường đi khiến điều kiện đúng hoặc sai**, kể cả khả năng thoát sớm khỏi hàm.

## 6. Nested pattern trong `switch`: biến của từng nhánh

Khi dùng record pattern trong `switch`, các biến con thuộc phạm vi của **nhánh `case` tương ứng**, gồm biểu thức điều kiện `when` và phần xử lý của nhánh đó:

~~~java
static String describe(Object input) {
    return switch (input) {
        case Segment(Point(var sx, var sy), Point(var ex, var ey))
                when ex > sx ->
                "right: " + (ex - sx);
        case Segment(Point(var sx, var sy), Point(var ex, var ey)) ->
                "not right: " + (ex - sx);
        case null -> "null input";
        default -> "other";
    };
}
~~~

- Ở nhánh thứ nhất, biến `sx` và `ex` đã được tạo bởi mẫu `Segment(... Point(...), Point(...))`. Vì thế điều kiện `when ex > sx` có thể tham chiếu chúng.
- Nếu `when` sai, `switch` có thể thử nhánh tiếp theo. Nhánh thứ hai có **các khai báo `sx`, `sy`, `ex`, `ey` riêng**, không dùng biến được tạo từ nhánh thứ nhất.
- Sau khi ra khỏi `switch`, không thể dùng các biến mẫu đó ở câu lệnh ngoài `switch` chỉ bằng tên của chúng.
- `case null` xử lý **chính giá trị `input == null`**. Một `Segment` có `end == null` sẽ không khớp hai mẫu `Point(...)`, và trong ví dụ này chuyển xuống `default` để trả về `"other"`.

Có thể lặp lại tên biến mẫu ở **hai nhánh `case` khác nhau** như ví dụ vì các khai báo thuộc những phạm vi khác nhau. Tuy nhiên, **không được khai báo trùng tên trong cùng một mẫu** (ví dụ dùng `sx` cho cả hai component của `Point`).

Khi cần truyền các giá trị đã phân rã ra bên ngoài `switch`, hãy trả về kết quả từ `switch expression`, gọi phương thức xử lý ở từng nhánh hoặc gán vào biến được khai báo ở phạm vi ngoài. Đừng dựa vào tên biến mẫu của riêng một `case`.

## 7. Chương trình Java 21 hoàn chỉnh

Tạo tệp `NestedPatternScopeDemo.java`:

~~~java
public class NestedPatternScopeDemo {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}

    static int horizontalDistanceOrMinusOne(Object input) {
        if (!(input instanceof Segment(
                Point(int startX, var startY),
                Point(int endX, var endY)))) {
            return -1;
        }
        return endX - startX;
    }

    static String describe(Object input) {
        return switch (input) {
            case Segment(Point(var sx, var sy), Point(var ex, var ey))
                    when ex > sx -> "right: " + (ex - sx);
            case Segment(Point(var sx, var sy), Point(var ex, var ey)) ->
                    "not right: " + (ex - sx);
            case null -> "null input";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        Object candidate = new Segment(
                new Point(1, 2),
                new Point(6, 8)
        );

        if (candidate instanceof Segment(
                Point(var sx, var sy),
                Point(var ex, var ey))
                && ex > sx) {
            System.out.println("start=" + sx + "," + sy);
            System.out.println("end=" + ex + "," + ey);
        }

        System.out.println(horizontalDistanceOrMinusOne(candidate));
        System.out.println(horizontalDistanceOrMinusOne(
                new Segment(new Point(4, 4), null)));

        System.out.println(describe(candidate));
        System.out.println(describe(new Segment(
                new Point(9, 1),
                new Point(3, 1))));
        System.out.println(describe(null));
    }
}
~~~

Biên dịch và chạy bằng JDK 21+ (không cần `--enable-preview`):

~~~bash
javac --release 21 NestedPatternScopeDemo.java
java NestedPatternScopeDemo
~~~

Kết quả chính xác:

~~~text
start=1,2
end=6,8
5
-1
right: 5
not right: -6
null input
~~~

Giải thích theo phạm vi:

1. Nhánh `if` đầu khớp thành công `Segment(Point(...), Point(...))` và điều kiện `ex > sx` đúng, nên in hai điểm.
2. `horizontalDistanceOrMinusOne(candidate)` trả về `6 - 1 = 5`. Các biến `startX`, `endX` còn thuộc phạm vi sau guard clause vì đường đi không khớp đã thoát khỏi hàm.
3. Với `end == null`, mẫu lồng `Point(int endX, var endY)` không khớp nên hàm trả `-1` mà không sử dụng biến mẫu chưa được tạo.
4. Hai nhánh `switch` có cùng tên `sx`/`ex` nhưng phạm vi riêng. Điều kiện `when ex > sx` dẫn tới `"right: 5"` cho đoạn đầu; đoạn ngược chiều lấy nhánh thứ hai `"not right: -6"`.
5. Đối tượng `null` khớp `case null`. Không có biến mẫu record nào được sử dụng ở nhánh này.

Đây là chương trình độc lập: các khai báo record, phương thức và `main` đều nằm trong cùng tệp. Các ví dụ không biên dịch ở các mục trước được chú thích riêng và **không xuất hiện** trong tệp này.

## 8. Bảng tra nhanh phạm vi biến mẫu

| Vị trí | Có dùng được `sx`, `ex` từ mẫu lồng không? | Lý do |
| --- | --- | --- |
| Thân `if (obj instanceof Segment(...))` | Có | Điều kiện đúng xác nhận toàn bộ mẫu khớp. |
| Thân `else` của điều kiện `instanceof` không phủ định | Không | Nhánh sai không bảo đảm mẫu khớp. |
| Vế phải của `instanceof ... && ex > sx` | Có | `&&` chỉ đánh giá vế phải khi mẫu trái đúng. |
| Vế phải của `instanceof ... || ex > sx` | Không | `||` đánh giá vế phải khi mẫu trái sai. |
| Vế phải của `!(instanceof ...) || ex <= sx` | Có | Phủ định sai đồng nghĩa mẫu `instanceof` đúng. |
| Sau `if (!(obj instanceof ...)) return;` | Có, trong phần đường đi tiếp tục | Đường đi không khớp đã kết thúc. |
| Điều kiện `when` của `case Segment(...)` | Có | Guard được đánh giá sau khi mẫu trong `case` khớp. |
| Biểu thức sau `->` của cùng `case` | Có | Nhánh đã khớp và thỏa guard (nếu có). |
| `case` khác hoặc sau `switch` | Không dùng chung khai báo đó | Mỗi nhánh có phạm vi riêng. |

## 9. Sai sót thường gặp và cách sửa

**Sai 1 — dùng biến sau điều kiện có thể thất bại.**

~~~java
// Minh họa SAI: nếu mẫu không khớp, sx không có giá trị được bảo đảm.
if (input instanceof Segment(
        Point(int sx, int sy),
        Point(int ex, int ey))) {
    System.out.println("matched");
}
// System.out.println(sx); // LỖI nếu bỏ comment
~~~

**Sửa:** chuyển logic sử dụng `sx` vào nhánh `if`, hoặc dùng guard clause với `return`/`throw` ở đường đi không khớp.

**Sai 2 — lấy nhầm biến của mẫu cấp ngoài và cấp trong.** `Segment` có các component `start`, `end` kiểu `Point`; `sx` được tạo từ component `x` của `Point` nằm trong `start`. Một record pattern lồng nhiều tầng *không* làm tên biến tự động trở thành trường hay thuộc tính của record ngoài.

**Sai 3 — dùng cùng tên trong một mẫu.**

~~~java
// SAI: khai báo sx hai lần trong cùng mẫu.
if (input instanceof Segment(
        Point(int sx, int sy),
        Point(int sx, int ey))) {
    // ...
}
~~~

**Sửa:** đặt tên duy nhất cho mỗi biến mẫu đang cùng tồn tại trong một phạm vi, chẳng hạn `startX` và `endX`.

**Sai 4 — nghĩ rằng biến ở guard `when` dùng được trong mọi `case`.** Khi một nhánh thất bại ở `when`, biến mẫu của nhánh ấy không được mang sang nhánh kế tiếp; nhánh kế tiếp phải khai báo mẫu của chính nó.

**Sai 5 — bỏ qua null của record lồng.** `Segment(new Point(1, 2), null)` là một đối tượng `Segment` hợp lệ, nhưng **không** khớp `Segment(Point(...), Point(...))` vì `end` không khớp mẫu `Point`. Chỉ sử dụng biến mẫu khi phép khớp thành công; nếu dữ liệu cho phép `null` thì cần đường xử lý dự phòng.

**Sai 6 — cho rằng `var` cho phép truy cập bất kỳ phương thức nào.** `var` suy ra kiểu theo **khai báo component** (ví dụ `Point` trả về `int`); kiểu ấy vẫn được trình biên dịch kiểm tra. `var` không làm biến trở thành kiểu tùy ý theo giá trị runtime.

## 10. Cách tự kiểm tra một vị trí sử dụng biến

Khi nhìn một nested record pattern phức tạp, hãy đặt ba câu hỏi:

1. **Biến được khai báo ở đâu?** Chỉ rõ component pattern tạo tên đó, ví dụ `Point(int sx, int sy)`.
2. **Đến vị trí dùng biến có chắc mẫu ngoài cùng và mọi mẫu con đã khớp không?** Xét đường đi thật của `if`, `&&`, `||`, phủ định và guard clause.
3. **Có còn nằm trong nhánh `case` tương ứng không?** Với `switch`, điều kiện `when` và thân của chính nhánh đó có thể dùng biến; nhánh khác phải có khai báo riêng.

**Ghi nhớ:** Phạm vi của biến trong nested pattern được quyết định bởi **luồng điều khiển chứng minh mẫu khớp**, không chỉ bởi cặp dấu ngoặc ôm lấy bản khai báo. Các biến ở nhiều tầng của record pattern chỉ được dùng tại những điểm mà Java chắc chắn phép khớp tổng thể đã thành công.