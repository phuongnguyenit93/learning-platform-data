# Type pattern cho class, interface, record và array

## Mục tiêu

Trong Java 21, pattern matching for `switch` đã trở thành tính năng ổn định của ngôn ngữ và không cần bật preview để sử dụng. Một nhãn `case` có thể dùng **type pattern** để kiểm tra kiểu thực tế của giá trị selector và gắn giá trị đó vào một biến có kiểu cụ thể. Cách viết này giúp xử lý nhiều kiểu dữ liệu mà không cần chuỗi `instanceof`, ép kiểu thủ công và các nhánh `if` lồng nhau.

Type pattern dùng được với kiểu lớp, kiểu interface, kiểu record và kiểu mảng. Mỗi loại có một số điểm cần chú ý về quan hệ kế thừa, khả năng một đối tượng khớp nhiều pattern, generic, thứ tự nhãn `case` và xử lý `null`.

## 1. Cú pháp cơ bản của type pattern trong switch

Cú pháp tổng quát của một nhãn type pattern là:

```java
case Type variable -> expression;
```

`Type` là kiểu tham chiếu cần kiểm tra, còn `variable` là pattern variable nhận chính giá trị selector sau khi matching thành công. Ví dụ:

```java
class BasicTypeSwitch {
    static String describe(Object value) {
        return switch (value) {
            case String text -> "Chuỗi: " + text;
            case Number number -> "Số: " + number;
            case null -> "Không có giá trị";
            default -> "Kiểu dữ liệu khác";
        };
    }
}
```

Khi `value` là một `String`, nhãn `case String text` khớp và biến `text` có kiểu tĩnh `String`. Khi giá trị là một đối tượng thuộc `Number` như `Integer` hoặc `Double`, nhãn `case Number number` khớp và biến `number` có kiểu tĩnh `Number`.

Sau khi một nhãn khớp, switch thực thi đúng rule tương ứng. Với switch expression, mỗi nhánh thường trả về một giá trị bằng `->`; với switch statement, nhánh có thể thực hiện một hoặc nhiều câu lệnh. Pattern variable chỉ được dùng trong guard và phần thân của rule đã khai báo nó.

## 2. Type pattern cho class

Type pattern với class khớp khi đối tượng có kiểu thực tế tương thích với class được chỉ định. Quan hệ kế thừa được tính đến: một đối tượng của class con cũng khớp với pattern của class cha.

```java
class ClassPatternExample {
    static String describe(Object value) {
        return switch (value) {
            case Integer integer -> "Số nguyên: " + integer;
            case Number number -> "Một kiểu số: " + number;
            case String text -> "Văn bản: " + text;
            default -> "Đối tượng khác";
        };
    }
}
```

`Integer` là lớp con của `Number`, vì vậy một đối tượng `Integer` có thể khớp với cả hai pattern. Nhãn `Integer` được đặt trước `Number` để xử lý trường hợp cụ thể trước. Nếu đặt `case Number number` trước `case Integer integer`, nhãn `Integer` phía sau sẽ bị compiler báo lỗi vì mọi `Integer` đều đã khớp với `Number`.

Pattern variable có kiểu tĩnh đúng bằng kiểu được ghi trong pattern. Trong ví dụ, `integer` có kiểu `Integer`, còn `number` có kiểu `Number`. Có thể gọi các phương thức được khai báo trên kiểu đó mà không cần ép kiểu thêm.

## 3. Type pattern cho interface

Interface cũng là một kiểu tham chiếu nên có thể dùng trực tiếp trong type pattern. Pattern khớp với đối tượng có class thực tế triển khai interface đó:

```java
class InterfacePatternExample {
    static String describe(Object value) {
        return switch (value) {
            case CharSequence text -> "Độ dài văn bản: " + text.length();
            case Runnable task -> "Một tác vụ có thể chạy";
            default -> "Không thuộc các kiểu đã hỗ trợ";
        };
    }
}
```

`String`, `StringBuilder` và nhiều kiểu khác triển khai `CharSequence`, nên đều có thể khớp với `case CharSequence text`. Biến `text` được nhìn nhận qua hợp đồng của interface; mã trong rule có thể gọi `length()` và những phương thức khác được khai báo trong `CharSequence`.

### Một đối tượng có thể triển khai nhiều interface

Một class có thể triển khai nhiều interface không có quan hệ kế thừa với nhau. Vì vậy, một đối tượng đôi khi khớp với nhiều type pattern interface:

```java
import java.io.Serializable;

class OverlappingInterfacePatterns {
    static String classify(Object value) {
        return switch (value) {
            case Serializable serializable -> "Serializable";
            case Comparable<?> comparable -> "Comparable";
            default -> "Không thuộc hai interface trên";
        };
    }
}
```

`String` triển khai cả `Serializable` và `Comparable<String>`. Hai interface trong ví dụ không phải quan hệ cha-con, nên compiler không thể kết luận một pattern luôn bao phủ pattern kia. Nếu một đối tượng khớp cả hai, nhãn xuất hiện trước sẽ được chọn. Hãy đặt thứ tự theo hành vi mà ứng dụng muốn ưu tiên.

### Generic interface và kiểu có thể reify

Do generic của Java sử dụng type erasure, chương trình không thể kiểm tra trực tiếp mọi tham số kiểu ở runtime. Vì vậy, type pattern phải dùng kiểu có thể reify. Ví dụ `List<?>` hợp lệ, còn `List<String>` không phải kiểu reifiable và không thể dùng làm type pattern thông thường:

```java
import java.util.List;

class GenericInterfacePattern {
    static String describe(Object value) {
        return switch (value) {
            case List<?> items -> "Số phần tử: " + items.size();
            default -> "Không phải List";
        };
    }
}
```

`List<?>` chỉ khẳng định đối tượng là một `List` với kiểu phần tử chưa biết. Nếu nghiệp vụ cần xác nhận tất cả phần tử đều là `String`, hãy kiểm tra từng phần tử sau khi matching, hoặc chuyển đổi dữ liệu qua một bước xác thực rõ ràng. Không nên giả định `List<?>` chứng minh được danh sách chứa riêng `String`.

## 4. Type pattern cho record

Record là một dạng class, vì vậy có thể dùng type pattern để nhận toàn bộ đối tượng record vào một biến:

```java
record Point(int x, int y) {
}

class RecordTypePatternExample {
    static String describe(Object value) {
        return switch (value) {
            case Point point -> "Point(" + point.x() + ", " + point.y() + ")";
            default -> "Không phải Point";
        };
    }
}
```

Trong `case Point point`, compiler chỉ kiểm tra giá trị là một `Point` phù hợp và gán toàn bộ tham chiếu cho biến `point`. Muốn đọc component, mã gọi accessor như `point.x()` và `point.y()`.

Nếu muốn lấy component ngay trong nhãn `case`, có thể dùng **record pattern**:

```java
class RecordPatternInSwitchExample {
    static String describe(Object value) {
        return switch (value) {
            case Point(int x, int y) -> "Tọa độ: " + x + ", " + y;
            default -> "Không phải Point";
        };
    }
}
```

Hai cách có mục đích khác nhau:

| Cách viết | Kết quả matching |
|---|---|
| `case Point point` | Nhận toàn bộ đối tượng record qua biến `point` |
| `case Point(int x, int y)` | Deconstruct record và lấy các component vào `x`, `y` |

Record pattern có thể lồng thêm pattern cho component. Ví dụ `case Rectangle(Point(int x1, int y1), Point(int x2, int y2))` kiểm tra cả record ngoài và các record con. Nếu chỉ cần xử lý toàn bộ record như một đối tượng, type pattern `Point point` thường đơn giản và dễ đọc hơn.

## 5. Type pattern cho array

Mảng trong Java là đối tượng, do đó có thể dùng kiểu mảng trong type pattern. Pattern kiểm tra kiểu runtime của mảng và gắn toàn bộ mảng vào biến:

```java
import java.util.Arrays;

class ArrayTypePatternExample {
    static String describe(Object value) {
        return switch (value) {
            case String[] strings -> "Mảng String: " + Arrays.toString(strings);
            case int[] numbers -> "Mảng int: " + Arrays.toString(numbers);
            case Object[] objects -> "Mảng tham chiếu: " + Arrays.toString(objects);
            case null -> "Không có mảng";
            default -> "Không phải các kiểu mảng được hỗ trợ";
        };
    }
}
```

Các pattern trong ví dụ có ý nghĩa như sau:

- `String[] strings` khớp với mảng có kiểu runtime là `String[]`.
- `int[] numbers` khớp với mảng nguyên thủy `int[]`.
- `Object[] objects` khớp với mảng có kiểu phần tử tham chiếu tương thích với `Object`.

### Quan hệ giữa `String[]`, `Object[]` và mảng nguyên thủy

Mảng tham chiếu có tính hiệp biến (covariant): `String[]` là subtype của `Object[]`. Vì vậy, `Object[]` có thể khớp với một đối tượng mảng `String[]`. Trong ví dụ, `String[]` được đặt trước `Object[]` để giữ nhánh xử lý riêng cho chuỗi; nếu đảo thứ tự, pattern `String[]` phía sau sẽ bị pattern `Object[]` bao phủ.

Mảng nguyên thủy như `int[]` không phải subtype của `Object[]`, dù bản thân mọi mảng đều là một đối tượng và có thể được gán cho biến `Object`. Do đó, `int[]` cần một pattern riêng nếu muốn xử lý trực tiếp các phần tử kiểu `int`.

Một pattern mảng chỉ kiểm tra kiểu runtime của toàn bộ mảng và bind tham chiếu mảng vào biến. Nó **không phải array destructuring pattern** và không tự lấy từng phần tử như record pattern lấy component. Sau matching, có thể truy cập phần tử bằng chỉ số, dùng vòng lặp hoặc các tiện ích trong `java.util.Arrays`.

Ví dụ, một biến có kiểu khai báo `Object[]` vẫn có thể tham chiếu đến mảng `String[]`:

```java
Object[] values = new String[] {"Java", "21"};

if (values instanceof String[] strings) {
    System.out.println(strings[0]); // Java
}
```

Ngược lại, nếu `values` tham chiếu đến một mảng được tạo với kiểu runtime là `Object[]`, việc các phần tử hiện tại đều là chuỗi không làm cho mảng đó khớp với `String[]`.

## 6. Thứ tự nhãn `case` và quy tắc dominance

Trong pattern switch, thứ tự các nhãn rất quan trọng. Một pattern rộng hơn có thể bao phủ pattern hẹp hơn. Nếu một nhãn đứng trước chắc chắn khớp với mọi giá trị mà nhãn phía sau có thể khớp, nhãn phía sau bị **dominated** và compiler từ chối switch.

Ví dụ đúng:

```java
class DominanceExample {
    static String describe(Object value) {
        return switch (value) {
            case null -> "null";
            case Integer integer -> "Integer: " + integer;
            case Number number -> "Number: " + number;
            case String text -> "String: " + text;
            case Object object -> "Object: " + object;
        };
    }
}
```

`Integer` được đặt trước `Number`, bởi mọi `Integer` đều là `Number`. `Object` nằm cuối vì mọi giá trị không-null đều là một đối tượng và có thể khớp với `Object`.

Ví dụ sai do pattern rộng đứng trước:

```java
// Không hợp lệ: Integer bị Number đứng trước bao phủ.
case Number number -> "Number";
case Integer integer -> "Integer";
```

Tương tự, `case CharSequence text` đứng trước `case String value` sẽ khiến pattern `String` phía sau bị dominated vì `String` triển khai `CharSequence`.

Với các interface không có quan hệ subtype, compiler có thể không phát hiện chúng cùng khớp với một class cụ thể. Khi đó, thứ tự nhãn quyết định rule nào được chọn. Hãy đọc cả quan hệ kiểu lẫn các class thực tế trong miền dữ liệu để sắp xếp nhãn có chủ đích.

### Dùng guard `when` để phân nhánh trong cùng một kiểu

Nếu cần phân biệt các giá trị cùng kiểu, có thể dùng guard `when`:

```java
class GuardedTypePatternExample {
    static String classify(Object value) {
        return switch (value) {
            case String text when text.isBlank() -> "Chuỗi rỗng hoặc chỉ có khoảng trắng";
            case String text -> "Chuỗi có nội dung: " + text;
            default -> "Kiểu khác";
        };
    }
}
```

Guard được đánh giá sau khi type pattern khớp, nên biến `text` có thể được sử dụng trong biểu thức `when`. Nếu guard trả về `false`, switch tiếp tục xét nhãn sau. Vì vậy, guarded pattern ở trên không bao phủ mọi `String`; nhãn `case String text` tiếp theo vẫn có thể được dùng.

## 7. Xử lý `null` trong pattern switch

Type pattern không khớp với `null`. Nếu selector có thể là `null`, hãy xử lý tường minh bằng `case null`:

```java
class NullPatternSwitchExample {
    static String describe(Object value) {
        return switch (value) {
            case null -> "Giá trị null";
            case String text -> "Chuỗi: " + text;
            case Object object -> "Đối tượng khác: " + object;
        };
    }
}
```

`default` không tự động thay thế cho `case null`. Nếu selector là `null` và switch không có nhãn xử lý null, việc thực thi switch sẽ ném `NullPointerException`, kể cả khi switch có `default` hoặc một type pattern rộng. Điều này khác với việc một giá trị không-null không khớp bất kỳ pattern cụ thể nào.

Với switch expression, hãy bảo đảm các trường hợp hợp lệ của nghiệp vụ được xử lý. Có thể dùng `case null` khi null là một trạng thái cần biểu diễn; nếu null là đầu vào không được phép, có thể chủ động kiểm tra và từ chối nó trước switch.

## 8. Tổng hợp lựa chọn pattern theo loại dữ liệu

| Loại dữ liệu | Ví dụ pattern | Điều cần nhớ |
|---|---|---|
| Class | `case Number number` | Đối tượng của class con cũng khớp với class cha |
| Interface | `case CharSequence text` | Mọi class triển khai interface đều có thể khớp |
| Generic interface | `case List<?> items` | Dùng kiểu reifiable; không kiểm tra được tham số generic cụ thể sau type erasure |
| Record như một class | `case Point point` | Bind toàn bộ record vào một biến |
| Record deconstruction | `case Point(int x, int y)` | Lấy component trực tiếp bằng record pattern |
| Mảng tham chiếu | `case String[] strings` | Mảng tham chiếu có covariance; cần chú ý quan hệ subtype với `Object[]` |
| Mảng nguyên thủy | `case int[] numbers` | Mỗi kiểu mảng nguyên thủy cần pattern tương ứng; không khớp `Object[]` |

Pattern switch trong Java 21 làm việc với các kiểu tham chiếu. Một mảng như `int[]` là kiểu tham chiếu nên có thể dùng type pattern, trong khi `int` là kiểu nguyên thủy và không phải type pattern để khớp một selector `Object`.

## 9. Checklist khi viết type pattern trong switch

Trước khi hoàn thành một pattern switch, hãy kiểm tra:

1. Selector có kiểu tham chiếu và các kiểu pattern có tương thích với kiểu selector không?
2. Với class, các subtype cụ thể đã được đặt trước supertype tổng quát chưa?
3. Với interface, có class nào trong miền dữ liệu triển khai đồng thời nhiều interface được kiểm tra không, và thứ tự ưu tiên đã rõ chưa?
4. Với generic, kiểu pattern có reifiable không, và có cần xác thực phần tử sau matching không?
5. Với record, cần bind toàn bộ record hay cần deconstruct component bằng record pattern?
6. Với array, đã phân biệt mảng tham chiếu với mảng nguyên thủy và sắp xếp `String[]` trước `Object[]` khi cần chưa?
7. Các guarded pattern có đứng trước pattern không guard cùng kiểu không?
8. Nếu selector có thể null, switch đã có `case null` hoặc có bước kiểm tra null trước đó chưa?

## Kết luận

Type pattern trong pattern switch Java 21 có thể kiểm tra class, interface, record và array, đồng thời bind giá trị đã khớp vào biến có kiểu tĩnh rõ ràng. Khi thiết kế switch, hãy xét quan hệ subtype để tránh dominance, chú ý các interface có thể giao nhau, dùng kiểu generic reifiable, phân biệt type pattern của record với record pattern deconstruction, và nhớ rằng array pattern chỉ bind toàn bộ mảng. Xử lý `null` tường minh khi đầu vào có thể chứa null để switch thể hiện đúng hợp đồng dữ liệu.
