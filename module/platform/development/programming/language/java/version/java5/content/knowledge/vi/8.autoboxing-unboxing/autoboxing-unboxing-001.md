# Chuyển đổi tự động giữa kiểu nguyên thủy và lớp bao

## 1. Khái niệm: boxing và unboxing

Java có hai nhóm kiểu cần phân biệt:

- **Kiểu nguyên thủy**, như `int`, `double`, `boolean`.
- **Kiểu tham chiếu**, trong đó có các lớp bao tương ứng như `Integer`, `Double`, `Boolean`.

**Boxing** chuyển một giá trị nguyên thủy sang dạng lớp bao tương ứng. **Unboxing** chuyển theo chiều ngược lại, từ lớp bao sang giá trị nguyên thủy.

Trong những ngữ cảnh được ngôn ngữ cho phép, trình biên dịch áp dụng chuyển đổi này tự động; ta thường gọi là autoboxing và auto-unboxing:

```java
// Minh họa trong một phương thức.
int primitive = 42;
Integer boxed = primitive;  // int -> Integer: boxing.
int restored = boxed;       // Integer -> int: unboxing.
```

Không cần tự gọi phương thức lấy giá trị ở hai câu lệnh gán trên, nhưng sự khác nhau giữa kiểu nguyên thủy và kiểu tham chiếu vẫn tồn tại.

`Integer` không phải một tên khác của `int`. Biến `Integer` có thể chứa `null`; biến `int` thì không. Một đối tượng lớp bao cũng có danh tính tham chiếu và các phương thức của lớp.

Các quy tắc trong bài vẫn áp dụng trong Java hiện đại. Chương trình thực hành dùng Java 17 trở lên và không cần thư viện ngoài.

## 2. Vì sao Java cung cấp chuyển đổi tự động?

Nhiều API làm việc với đối tượng, đặc biệt là các cấu trúc generic như `List<Integer>`. Trong khi đó, phép tính thông thường lại phù hợp với kiểu nguyên thủy.

Ví dụ:

```java
// Minh họa trong một phương thức; cần import ArrayList và List.
List<Integer> values = new ArrayList<>();
values.add(10);
int first = values.get(0);
```

`add` cần một giá trị tương thích với `Integer`, nên `10` được boxing. `get(0)` trả về `Integer`; gán kết quả cho `int` cần unboxing.

Cơ chế này giảm phần mã chuyển đổi lặp lại, nhưng không xóa bỏ hợp đồng kiểu của API. `List<int>` vẫn không hợp lệ: đối số kiểu generic phải là kiểu tham chiếu phù hợp.

Cách đọc an toàn là luôn xác định:

1. Biểu thức ban đầu có kiểu gì?
2. Vị trí nhận cần kiểu gì?
3. Chuyển đổi nào được cho phép ở ngữ cảnh đó?
4. Giá trị tham chiếu có thể là `null` hay không?

## 3. Tám cặp kiểu tương ứng

| Kiểu nguyên thủy | Lớp bao | Lấy giá trị nguyên thủy bằng phương thức |
| --- | --- | --- |
| `boolean` | `Boolean` | `booleanValue()` |
| `byte` | `Byte` | `byteValue()` |
| `short` | `Short` | `shortValue()` |
| `char` | `Character` | `charValue()` |
| `int` | `Integer` | `intValue()` |
| `long` | `Long` | `longValue()` |
| `float` | `Float` | `floatValue()` |
| `double` | `Double` | `doubleValue()` |

Tên lớp bao là một phần của API Java; lưu ý `Integer` và `Character`, không phải `Int` và `Char`.

Để hiểu cơ chế, có thể đối chiếu:

```java
// Minh họa trong một phương thức.
Integer automatic = 42;
Integer explicit = Integer.valueOf(42);

int automaticValue = automatic;
int explicitValue = explicit.intValue();
```

Hai cặp có cùng ý định chuyển đổi giá trị ở ví dụ. Không suy ra rằng boxing luôn tạo một đối tượng mới: các phương thức tạo giá trị của lớp bao có thể tái sử dụng đối tượng và JVM có thể tối ưu.

Không cần tự tạo đối tượng bằng các constructor lớp bao đã lỗi thời. Khi cần viết bước tạo lớp bao tường minh, dùng API `valueOf` phù hợp.

## 4. Các ngữ cảnh thường gặp

### 4.1. Phép gán

```java
// Minh họa trong một phương thức.
Integer count = 7;
int current = count;

Boolean enabled = true;
boolean active = enabled;
```

Kiểu của biến nhận quyết định cần boxing hay unboxing, với điều kiện ngữ cảnh gán cho phép chuyển đổi và giá trị hợp lệ.

### 4.2. Đối số và kết quả phương thức

```java
// Các phương thức minh họa, đặt bên trong một lớp.
static int increment(Integer value) {
    return value + 1;
}

static Integer boxedResult(int value) {
    return value;
}
```

Với `increment(4)`:

- Đối số `4` có kiểu `int`.
- Tham số cần `Integer`, nên lời gọi có thể dùng boxing.
- Phép cộng trong thân phương thức cần giá trị số; `value` được unboxing.

Với `boxedResult(5)`, câu lệnh `return` cần kết quả `Integer`, nên giá trị `int` được boxing.

Nếu một tên phương thức có nhiều overload, việc chọn phương thức còn tuân theo quy tắc nạp chồng; không thể chỉ thấy có boxing rồi kết luận một overload bất kỳ sẽ được chọn.

### 4.3. Phép toán số và tăng giảm

```java
// Minh họa trong một phương thức.
Integer left = 10;
Integer right = 20;

int total = left + right;
```

Phép cộng lấy giá trị nguyên thủy từ hai lớp bao rồi thực hiện phép tính. Đây không phải cơ chế định nghĩa lại toán tử `+` cho mọi đối tượng.

Với:

```java
// Minh họa trong một phương thức.
Integer count = 1;
Integer old = count;
count++;
```

Về mặt ý nghĩa, chương trình lấy giá trị số, tăng nó, rồi gán một kết quả lớp bao vào biến `count`. Đối tượng `Integer` cũ không bị biến đổi thành giá trị mới. Vì lớp bao bất biến, `old` vẫn biểu diễn `1`; `count` biểu diễn `2`.

### 4.4. Điều kiện boolean

```java
// Minh họa trong một phương thức.
Boolean ready = true;

if (ready) {
    System.out.println("ready");
}
```

Điều kiện `if` cần giá trị `boolean`, nên `Boolean` được unboxing. Việc này rất tiện nhưng cũng tạo rủi ro khi `ready` có thể là `null`.

## 5. Unboxing null gây NullPointerException

```java
// Minh họa lỗi khi chạy.
Integer missing = null;
int value = missing;
```

Không có giá trị số để lấy ra từ tham chiếu `null`, nên unboxing ném `NullPointerException`.

Lỗi có thể ẩn trong các thao tác ngắn:

```java
// Các tình huống minh họa, không phải chương trình cần chạy cùng lúc.
Integer count = null;
// int next = count + 1;
// count++;

Boolean ready = null;
// if (ready) { ... }
```

Các câu lệnh bị chú thích đều sẽ cần unboxing nếu thực thi với giá trị tương ứng là `null`.

Không tự coi `null` là `0` hoặc `false`. Chính sách phải theo ý nghĩa dữ liệu:

- Nếu thiếu giá trị là lỗi, kiểm tra và từ chối ở ranh giới nhận dữ liệu.
- Nếu thiếu là một trạng thái hợp lệ, giữ và xử lý trạng thái đó rõ ràng.
- Chỉ dùng giá trị mặc định nếu nghiệp vụ thật sự quy định như vậy.

Ví dụ với giá trị số:

```java
// Minh họa trong một phương thức có biến Integer candidate.
if (candidate != null) {
    int value = candidate;
    System.out.println(value);
} else {
    System.out.println("missing");
}
```

Với một cờ có quy ước “chỉ true mới bật”, `Boolean.TRUE.equals(flag)` kiểm tra được cả trường hợp `flag == null` mà không unboxing. Cách này chỉ phù hợp nếu việc coi `null` như “không bật” đúng với hợp đồng ứng dụng.

## 6. Chuyển đổi kết hợp có giới hạn

Boxing không phải một cơ chế tự nối mọi phép chuyển kiểu số có vẻ hợp lý.

### 6.1. Boxing rồi mở rộng tham chiếu

```java
// Minh họa trong một phương thức.
Number number = 10;
Object object = 20;
```

`10` được boxing thành `Integer`, rồi dùng qua kiểu cha `Number`. Tương tự, một `Integer` dùng được qua `Object`.

Đối tượng không tự trở thành một lớp bao khác chỉ vì biến nhận có kiểu cha.

### 6.2. Unboxing rồi mở rộng kiểu nguyên thủy

```java
// Minh họa trong một phương thức.
Integer boxed = 10;
long widened = boxed;
```

Giá trị `Integer` được unboxing thành `int`, rồi mở rộng sang `long`. Nếu `boxed` là `null`, bước unboxing vẫn gây lỗi trước khi có giá trị `long`.

### 6.3. Không tự mở rộng int rồi boxing thành Long

```java
// Minh họa lỗi; không biên dịch.
Long wrong = 10;
```

Literal `10` có kiểu `int`. Ngữ cảnh này không tự nối phép mở rộng `int -> long` rồi boxing `long -> Long`.

Cách phù hợp:

```java
// Minh họa trong một phương thức.
Long correct = 10L;

int count = 20;
Long converted = (long) count;
```

Ở đây biểu thức đầu vào của bước boxing đã có kiểu `long`.

Tương tự, không gán một `Integer` trực tiếp cho `Long` chỉ vì cả hai cùng là các lớp con của `Number`.

### 6.4. Trường hợp hằng số khi gán không giống mọi lời gọi phương thức

Phép gán cho một số lớp bao nhỏ có quy tắc bổ sung đối với hằng số nguyên nằm trong phạm vi biểu diễn:

```java
// Minh họa trong một phương thức.
Byte small = 1;
```

Literal `1` là hằng `int` biểu diễn được trong `byte`; ngữ cảnh gán này cho phép thu hẹp hằng số rồi boxing.

Đừng áp dụng điều đó máy móc cho lời gọi:

```java
// Phương thức minh họa, đặt bên trong một lớp.
static int readByte(Byte value) {
    return value;
}
```

`readByte((byte) 1)` hợp lệ, còn `readByte(1)` không hợp lệ với riêng chữ ký trên. Ngữ cảnh lời gọi không cung cấp cùng phép thu hẹp hằng số như phép gán `Byte small = 1`.

Bài học là xét đúng ngữ cảnh; không dùng khẩu quyết “mọi kiểu số tự đổi được cho nhau”.

## 7. Lưu ý về so sánh và dữ liệu generic

### So sánh lớp bao

Khi cả hai toán hạng là tham chiếu lớp bao, `==` có thể kiểm tra danh tính tham chiếu, không phải giá trị số.

```java
// Minh họa trong một phương thức.
Integer left = Integer.valueOf(1000);
Integer right = Integer.valueOf(1000);

boolean sameValue = left.equals(right);
```

`sameValue` là `true`. Không lấy kết quả `left == right` ở một giá trị cụ thể để suy ra quy tắc so sánh mọi lớp bao, vì việc tái sử dụng đối tượng không đồng nhất với so sánh giá trị.

Nếu tham chiếu có thể `null`, `Objects.equals(left, right)` là một cách so sánh giá trị có xử lý `null`. Cần lưu ý `equals` của lớp bao vẫn xét kiểu tương ứng; nó không biến mọi biểu diễn số khác kiểu thành cùng một giá trị nghiệp vụ.

Nếu một vế của phép so sánh cần kiểu nguyên thủy, Java có thể unboxing vế lớp bao. Ví dụ `boxed == 0` vẫn có thể ném `NullPointerException` khi `boxed` là `null`.

### Mảng không được boxing toàn bộ theo từng phần tử

`int[]` và `Integer[]` là hai kiểu mảng khác nhau. Boxing một giá trị `int` không có nghĩa Java tự chuyển một `int[]` thành `Integer[]` khi gán hoặc truyền đối số.

Nếu cần chuyển toàn bộ dữ liệu, phải viết một bước chuyển đổi phần tử rõ ràng.

### Collection vẫn chứa các tham chiếu lớp bao

`List<Integer>` có thể hoạt động trông giống một danh sách số nguyên vì boxing/unboxing được chèn ở những nơi phù hợp. Nó vẫn có hợp đồng của collection đối tượng, bao gồm khả năng hoặc giới hạn về `null` tùy bản triển khai.

Không giả định rằng mọi lần `get` từ một collection lớp bao đều unboxing an toàn.

## 8. Chương trình đầy đủ

Lưu vào `AutomaticBoxingDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class AutomaticBoxingDemo {
    static int increment(Integer value) {
        return value + 1;
    }

    static Integer boxedResult(int value) {
        return value;
    }

    static int readByte(Byte value) {
        return value;
    }

    public static void main(String[] args) {
        int primitive = 42;
        Integer boxed = primitive;
        int restored = boxed;
        System.out.println("boxed=" + boxed + ", unboxed=" + restored);

        System.out.println(increment(42));
        System.out.println(boxedResult(5).getClass().getSimpleName());

        List<Integer> values = new ArrayList<>();
        values.add(10);
        values.add(20);
        int total = values.get(0) + values.get(1);
        System.out.println(total);

        Integer count = 1;
        Integer old = count;
        count++;
        System.out.println(old + " -> " + count);

        Boolean ready = true;
        if (ready) {
            System.out.println("ready");
        }

        Number number = 10;
        System.out.println(number.getClass().getSimpleName());

        long widened = boxed;
        System.out.println("widened=" + widened);

        Long longBoxed = 42L;
        System.out.println("longBoxed=" + longBoxed);

        Byte small = 1;
        System.out.println(readByte(small));

        Integer missing = null;
        try {
            System.out.println(increment(missing));
        } catch (NullPointerException ex) {
            System.out.println("null cannot unbox");
        }

        Boolean absentFlag = null;
        System.out.println(Boolean.TRUE.equals(absentFlag));

        Integer left = Integer.valueOf(1000);
        Integer right = Integer.valueOf(1000);
        System.out.println(Objects.equals(left, right));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 AutomaticBoxingDemo.java
java AutomaticBoxingDemo
```

Stdout chính xác:

```text
boxed=42, unboxed=42
43
Integer
30
1 -> 2
ready
Integer
widened=42
longBoxed=42
1
null cannot unbox
false
true
```

Các điểm cần đối chiếu:

1. Phép gán thực hiện hai chiều chuyển đổi tương ứng.
2. Lời gọi `increment(42)` boxing đối số, rồi phép cộng trong thân hàm unboxing nó.
3. `boxedResult` trả về lớp bao dù tham số đầu vào là `int`.
4. Collection nhận các lớp bao và phép tính lấy lại giá trị nguyên thủy.
5. Tăng biến lớp bao không sửa đối tượng cũ mà biến `old` đang tham chiếu.
6. `if` dùng giá trị `Boolean` qua unboxing.
7. Gán `10` cho `Number` không đổi lớp bao thực tế thành một kiểu khác ngoài `Integer`.
8. Unboxing rồi mở rộng sang `long` là một chuỗi chuyển đổi được phép.
9. Literal `42L` đã có kiểu `long` trước khi boxing thành `Long`.
10. Hằng số phù hợp được gán cho `Byte`; truyền biến `Byte` cho `readByte` hợp lệ.
11. Unboxing `null` được bắt chỉ để tiếp tục minh họa.
12. So sánh với `Boolean.TRUE` không cần unboxing giá trị thiếu.
13. Hai lớp bao cùng giá trị được so sánh bằng `Objects.equals`, không dựa vào danh tính tham chiếu.

Trong mã ứng dụng, nên xử lý giá trị thiếu theo hợp đồng trước khi tính toán, thay vì dùng việc bắt `NullPointerException` làm luồng xử lý thông thường.

## 9. Cách áp dụng và lỗi thường gặp

Ưu tiên kiểu nguyên thủy khi dữ liệu luôn có giá trị và thuật toán trực tiếp tính toán trên giá trị ấy. Dùng lớp bao khi cần tương tác với API tham chiếu/generic hoặc khi việc biểu diễn trạng thái thiếu bằng `null` là một lựa chọn đã được thiết kế rõ.

Boxing có thể liên quan đến đối tượng, lưu tham chiếu và công việc unboxing. Chi phí thực tế còn phụ thuộc việc tái sử dụng đối tượng và tối ưu của JVM. Không khẳng định mỗi phép gán lớp bao luôn cấp phát một đối tượng mới, cũng không tối ưu dựa trên một con số bộ nhớ cố định cho mọi JVM.

Những lỗi cần tránh:

- Nghĩ `Integer` và `int` là cùng một kiểu.
- Quên unboxing trong phép cộng, tăng giảm, điều kiện hoặc so sánh với số nguyên thủy.
- Tưởng `null` tự trở thành `0` hoặc `false`.
- Mong mọi lớp bao số tự chuyển qua lại.
- Dùng `==` để kiểm tra giá trị của hai tham chiếu lớp bao.
- Mong Java tự boxing toàn bộ mảng.
- Dựa vào boxing để bỏ qua các ràng buộc của generic hoặc overload.

## 10. Tự kiểm tra

1. Đánh dấu các bước boxing/unboxing trong `Integer x = 7; int y = x + 1;`.
2. Vì sao `Integer old = count; count++;` không làm `old` tăng theo?
3. Viết một hàm nhận `Boolean` có thể thiếu và xử lý rõ ba trạng thái `true`, `false`, `null` mà không unboxing nhầm.
4. So sánh `Number n = 10;`, `long x = Integer.valueOf(10);` và `Long y = 10;`. Hai câu đầu có những bước chuyển đổi nào, câu cuối sai ở đâu?
5. Vì sao `Byte small = 1` có thể hợp lệ, nhưng `readByte(1)` không hợp lệ với chữ ký trong bài?
6. Tạo một danh sách `Integer` chứa `null`, rồi phân biệt đọc vào biến `Integer` và đọc vào biến `int`.
7. Giải thích vì sao kết quả so sánh tham chiếu của một vài số nhỏ không phải cơ sở để dùng `==` cho mọi lớp bao.

## Tài liệu đối chiếu

- [Java Language Specification — Boxing Conversion (§5.1.7)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.7): chuyển từ kiểu nguyên thủy sang lớp bao.
- [Java Language Specification — Unboxing Conversion (§5.1.8)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.8): chiều chuyển ngược và lỗi khi tham chiếu là `null`.
- [Java Language Specification — Assignment Contexts (§5.2)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.2): các chuỗi chuyển đổi trong phép gán, bao gồm hằng số phù hợp.
- [Java Language Specification — Invocation Contexts (§5.3)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.3): chuyển đổi khi truyền đối số.
- [Java API — Integer.valueOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Integer.html#valueOf(int)): tạo hoặc tái sử dụng giá trị lớp bao.
- [Java API — Boolean](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Boolean.html): lớp bao của `boolean`.
