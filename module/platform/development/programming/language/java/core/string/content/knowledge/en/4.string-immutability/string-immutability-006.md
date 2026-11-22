# Sao chép đầu vào `char[]` và tính độc lập của `String.toCharArray()` trong Java

## 1. Hai chiều chuyển đổi, cùng một nguyên tắc: bảo vệ tính bất biến của `String`

Trong Java, `char[]` là mảng **có thể thay đổi**: phần tử `array[i]` có thể được gán lại. Ngược lại, `String` biểu diễn **giá trị văn bản bất biến**. Để hai kiểu này làm việc với nhau an toàn, API Java duy trì ranh giới sao chép dữ liệu ở cả hai chiều:

1. **`char[]` → `String`:** `new String(charArray)` lấy nội dung các phần tử mảng tại thời điểm tạo chuỗi. Sửa mảng nguồn **sau khi constructor hoàn tất** không làm thay đổi chuỗi đã tạo.
2. **`String` → `char[]`:** `string.toCharArray()` trả một **mảng mới** chứa các đơn vị ký tự của chuỗi. Sửa mảng nhận về không làm thay đổi `String` nguồn.
3. Các API như `String.valueOf(char[])`, `String.copyValueOf(char[])`, `new String(char[], offset, count)` và `String.getChars(...)` cũng có hợp đồng chuyển/copy dữ liệu tương ứng; cần phân biệt rõ nơi nào chứa bản sao và nơi nào vẫn chia sẻ mảng.

Hình dung theo quan hệ sở hữu nội dung, sau khi đã tạo `String`:

```text
char[] input = {'J','a','v','a'}  [MẢNG THAY ĐỔI ĐƯỢC]
        │
        │ new String(input): chụp giá trị các phần tử
        ▼
String text = "Java"             [GIÁ TRỊ BẤT BIẾN]
        │
        │ text.toCharArray(): tạo mảng mới
        ▼
char[] output = {'J','a','v','a'} [MẢNG THAY ĐỔI ĐƯỢC, ĐỘC LẬP]

input[0] = 'K'  → text vẫn "Java", output vẫn "Java"
output[0] = 'X' → text vẫn "Java", input vẫn "Kava"
```

Sơ đồ chỉ mô tả **hợp đồng về dữ liệu**. Nó không khẳng định `String` phải dùng `char[]` làm cấu trúc lưu trữ bên trong. Chi tiết biểu diễn bộ nhớ của `String` có thể thay đổi theo phiên bản hoặc triển khai JDK; điều đáng tin cậy là tính bất biến và sự độc lập quan sát được qua API.

## 2. `char[]` mutable; phép gán mảng thông thường không tạo bản sao

Một biến kiểu `char[]` giữ **tham chiếu tới một đối tượng mảng**. Gán tham chiếu sang biến khác không nhân đôi phần tử:

```java
char[] input = {'J', 'a', 'v', 'a'};
char[] alias = input; // Hai biến trỏ cùng một mảng.
alias[0] = 'K';

System.out.println(new String(input)); // Kava
System.out.println(input == alias);     // true
```

Đây là **snippet minh họa**, các dòng `System.out.println` đặt trong phương thức như `main`. `alias[0] = 'K'` thay đổi chính mảng mà `input` đang tham chiếu. Khác biệt cốt lõi là:

| Biểu thức | Có tạo bản sao dữ liệu? | Sau khi sửa mảng nguồn |
| --- | --- | --- |
| `char[] b = a;` | Không, chỉ sao chép tham chiếu | `b` quan sát thay đổi ở `a` |
| `char[] b = a.clone();` | Có, tạo mảng mới với các phần tử được sao chép | `b` giữ nội dung riêng |
| `char[] b = Arrays.copyOf(a, a.length);` | Có, tạo mảng mới | `b` giữ nội dung riêng |
| `String s = new String(a);` | Có, tạo giá trị chuỗi từ nội dung mảng | `s` không đổi |
| `char[] b = s.toCharArray();` | Có, trả mảng mới từ chuỗi | Sửa `b` không đổi `s` |

Đối với `char[]`, clone là sao chép đủ sâu để độc lập về **phần tử**, vì mỗi phần tử `char` là giá trị nguyên thủy, không phải tham chiếu tới đối tượng có thể thay đổi bên trong.

## 3. Constructor `new String(char[])` sao chép nội dung đầu vào

Cách trực tiếp để tạo chuỗi bất biến từ mảng ký tự là:

```java
char[] source = {'H', 'e', 'l', 'l', 'o'};
String text = new String(source);
source[0] = 'Y';

System.out.println(new String(source)); // Yello
System.out.println(text);               // Hello
```

Cách đọc đúng:
- Khi `new String(source)` hoàn tất, `text` có nội dung `"Hello"` và nội dung đó được bảo vệ trước sửa đổi tiếp theo của mảng nguồn.
- `source[0] = 'Y'` thay đổi phần tử thứ nhất của mảng nguồn; `text` không giữ một view mutable trỏ ngược tới mảng.
- Không cần `source.clone()` trước `new String(source)` chỉ để bảo vệ `String` khỏi thay đổi *sau đó*: constructor đã đáp ứng hợp đồng độc lập cần thiết. Việc chủ động clone chỉ có ý nghĩa khi ứng dụng còn cần sở hữu riêng **một mảng khác**.

Các overload có ý nghĩa tương tự:

```java
char[] chars = {'J', 'a', 'v', 'a'};

String a = new String(chars);
String b = String.valueOf(chars);
String c = String.copyValueOf(chars);
```

Cả ba đều tạo nội dung `"Java"` độc lập với các thay đổi tiếp theo của `chars`. `String.copyValueOf(char[])` có tác dụng tương đương `String.valueOf(char[])`; tên `copyValueOf` không có nghĩa rằng `valueOf(char[])` sẽ giữ mảng bằng tham chiếu.

**Điểm dễ nhầm về overload:** `String.valueOf(char[])` và `String.valueOf(Object)` là hai overload khác nhau. Ép mảng thành `Object` làm Java chọn overload `Object`, vốn dùng cách biểu diễn đối tượng của mảng:

```java
char[] chars = {'O', 'K'};
System.out.println(String.valueOf(chars));          // OK
System.out.println(String.valueOf((Object) chars)); // Dạng [C@..., không phải "OK"
```

Đoạn này là snippet minh họa, không phải file lớp độc lập. Dạng `[C@...` gồm ký hiệu kiểu mảng `char[]` và phần định danh không ổn định; không được dựa vào nội dung đầy đủ của nó.

## 4. `toCharArray()` luôn trao một mảng ký tự để người gọi sở hữu và sửa

Phương thức `String.toCharArray()` trả một `char[]` **mới** có nội dung tại thời điểm gọi. Người gọi có thể sửa, sắp xếp, điền lại hoặc chuyển mảng đi mà không thể sửa `String` nguồn qua mảng đó.

```java
String text = "Java";
char[] first = text.toCharArray();
char[] second = text.toCharArray();

first[0] = 'K';
second[1] = 'O';

System.out.println(text);               // Java
System.out.println(new String(first));  // Kava
System.out.println(new String(second)); // JOva
System.out.println(first == second);    // false
```

Hai lệnh `toCharArray()` trả hai mảng khác nhau. Cả hai đều không phải “cửa hậu” để thay đổi chuỗi gốc. Khi cần nội dung của `String` ở dạng `char[]`, đây là cách chuẩn để **chủ động tạo dữ liệu mutable**.

Không nên hiểu nhầm rằng `String` luôn chứa sẵn một `char[]` mà `toCharArray()` chỉ trả lại; giả định đó sẽ khiến người học viết code lệ thuộc cấu trúc nội bộ và đi ngược hợp đồng API.

### Chương trình chạy đầy đủ: hai chiều sao chép

Lưu dưới tên `CharArrayCopyDemo.java`:

```java
public class CharArrayCopyDemo {
    public static void main(String[] args) {
        char[] input = {'J', 'a', 'v', 'a'};
        char[] alias = input;

        String byConstructor = new String(input);
        String byValueOf = String.valueOf(input);
        String byCopyValueOf = String.copyValueOf(input);

        alias[0] = 'K'; // input cũng đổi: alias và input là một mảng.
        System.out.println(new String(input));
        System.out.println(byConstructor);
        System.out.println(byValueOf);
        System.out.println(byCopyValueOf);

        char[] extracted = byConstructor.toCharArray();
        extracted[0] = 'X';
        System.out.println(new String(extracted));
        System.out.println(byConstructor);

        char[] extractedAgain = byConstructor.toCharArray();
        System.out.println(extracted == extractedAgain);
        System.out.println(new String(extractedAgain));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 CharArrayCopyDemo.java
java CharArrayCopyDemo
```

Kết quả chuẩn:

```text
Kava
Java
Java
Java
Xava
Java
false
Java
```

Giải thích từ kết quả:
- `alias[0]` sửa mảng gốc; cả ba chuỗi đã tạo từ mảng vẫn là `Java`.
- `extracted[0]` chỉ sửa mảng đầu tiên do `toCharArray()` trả về.
- `byConstructor` không đổi và lần gọi `toCharArray()` tiếp theo mang lại nội dung gốc.
- `extracted == extractedAgain` là `false` vì đây là **hai mảng** được tạo bởi hai lần gọi riêng biệt.

## 5. Chỉ sao chép một đoạn mảng: `new String(char[], offset, count)`

Không phải lúc nào cả mảng nguồn cũng thuộc về phần văn bản cần lưu. Constructor `new String(char[] value, int offset, int count)` dùng **đoạn liên tiếp** bắt đầu tại chỉ số `offset` và gồm `count` phần tử `char`:

```java
char[] frame = {'[', 'J', 'a', 'v', 'a', ']'};
String inner = new String(frame, 1, 4);
frame[1] = 'X';

System.out.println(inner);              // Java
System.out.println(new String(frame));  // [Xava]
```

Khoảng được sao chép là `[offset, offset + count)`: điểm đầu tính, điểm cuối loại trừ. Với mảng ví dụ, phần tử ở chỉ số 1, 2, 3, 4 tạo nội dung `Java`, không chứa hai dấu ngoặc. Dữ liệu trong `inner` độc lập với cả mảng `frame`, kể cả các vị trí nằm trong đoạn đã copy.

Điều kiện hợp lệ: `offset >= 0`, `count >= 0` và `offset + count <= value.length` (diễn đạt theo điều kiện giới hạn chỉ số; triển khai kiểm tra theo cách tránh tràn số). Giá trị `count == 0` hợp lệ nếu `offset` ở phạm vi phù hợp, kể cả `offset == value.length`. Offset/count sai gây `IndexOutOfBoundsException`; truyền mảng `null` gây `NullPointerException`.

Phân biệt với `Arrays.copyOfRange(array, from, to)`:
- `new String(array, offset, count)` trả **`String`**, tham số thứ ba là **số lượng** phần tử.
- `Arrays.copyOfRange(array, from, to)` trả **`char[]`**, tham số thứ ba là **chỉ số kết thúc loại trừ**; với một số đầu vào có `to` vượt chiều dài mảng, phương thức còn có quy tắc đệm phần tử mặc định. Không đổi chỗ hai quy tắc.

## 6. Sao chép từ `String` vào mảng có sẵn: `getChars`

Nếu đã có mảng đích, `String.getChars(srcBegin, srcEnd, dst, dstBegin)` sao chép ký tự của chuỗi sang **mảng đó**. Phương thức không trả một mảng mới; `dst` là đối tượng mà người gọi cấp. Nó vẫn không tạo đường sửa ngược lại vào `String`.

Định nghĩa các tham số:
- `srcBegin`: chỉ số bắt đầu của chuỗi, tính vào đoạn.
- `srcEnd`: chỉ số kết thúc chuỗi, không tính vào đoạn.
- `dst`: mảng nhận dữ liệu.
- `dstBegin`: chỉ số bắt đầu ghi vào mảng đích.

Ví dụ đầy đủ, lưu `SliceCopyDemo.java`:

```java
public class SliceCopyDemo {
    public static void main(String[] args) {
        char[] frame = {'[', 'J', 'a', 'v', 'a', ']'};
        String inner = new String(frame, 1, 4);

        char[] destination = {'_', '_', '_', '_', '_', '_'};
        inner.getChars(1, 3, destination, 2); // Sao chép "av" vào vị trí 2, 3.

        frame[1] = 'X';
        destination[2] = 'Z';

        System.out.println(inner);
        System.out.println(new String(frame));
        System.out.println(new String(destination));
        System.out.println(new String(inner.toCharArray()));
    }
}
```

```bash
javac -encoding UTF-8 SliceCopyDemo.java
java SliceCopyDemo
```

```text
Java
[Xava]
__Zv__
Java
```

Vì `srcEnd` là chỉ số **loại trừ**, `getChars(1,3,...)` sao chép hai ký tự `a` và `v`, đặt vào `destination[2]` và `destination[3]`. Sau khi sửa đích thành `Z`, mảng `destination` in ra `__Zv__`; chuỗi `inner` vẫn là `Java`. Phải cấp mảng đích đủ lớn và sử dụng chỉ số hợp lệ, nếu không sẽ có ngoại lệ biên; `dst == null` cũng không hợp lệ.

Dùng `getChars` khi cần điền một phần dữ liệu vào một mảng do người gọi quản lý; dùng `toCharArray()` khi muốn nhận mảng mới chứa **toàn bộ** chuỗi.

## 7. Tính bất biến, bản chụp nội dung và thiết kế API phòng thủ

Giả sử một lớp nhận dữ liệu `char[]` của người gọi để lưu thành giá trị văn bản. Nếu lớp giữ thẳng tham chiếu mảng vào một trường `char[]`, bên gọi vẫn có thể sửa dữ liệu từ bên ngoài. Nếu lớp chỉ cần dữ liệu chuỗi, chuyển sang `String` trong constructor sẽ tạo giá trị văn bản bất biến; khi cần trả mảng mutable, hãy tạo mảng qua `toCharArray()`.

Lưu `ImmutableLabel.java`:

```java
import java.util.Objects;

public final class ImmutableLabel {
    private final String value;

    public ImmutableLabel(char[] input) {
        Objects.requireNonNull(input, "input");
        this.value = new String(input);
    }

    public String text() {
        return value;
    }

    public char[] characters() {
        return value.toCharArray();
    }

    public static void main(String[] args) {
        char[] source = {'H', 'e', 'l', 'l', 'o'};
        ImmutableLabel label = new ImmutableLabel(source);

        source[0] = 'Y';
        char[] exported = label.characters();
        exported[1] = 'X';

        System.out.println(new String(source));
        System.out.println(new String(exported));
        System.out.println(label.text());
    }
}
```

```bash
javac -encoding UTF-8 ImmutableLabel.java
java ImmutableLabel
```

```text
Yello
HXllo
Hello
```

Trường `value` là `final`, tức không thể gán lại tham chiếu sau constructor, đồng thời giá trị `String` mà nó tham chiếu bất biến. Dù người gọi sửa `source` hoặc mảng `exported`, nội dung `label.text()` vẫn là `Hello`. Đây là một dạng **defensive copy** tại ranh giới nhận/trả dữ liệu; trong ví dụ, hai thao tác sao chép do chính API `String` bảo đảm.

Nếu cần tiếp tục giữ mảng mutable ở bên trong một lớp (ví dụ vì thuật toán đòi hỏi sửa ký tự tại chỗ), có thể nhận `input.clone()` và khi trả mảng thì trả bản sao. Nhưng trường mảng `private final char[]` **không tự biến nội dung mảng thành bất biến**: `final` chỉ khóa tham chiếu của trường, không khóa `array[i]`.

### Vì sao thời điểm copy có ý nghĩa?

Một `String` được tạo từ mảng là **bản chụp giá trị vào thời điểm constructor đọc mảng**, không phải liên kết động. Sau thời điểm đó, việc sửa mảng không tác động chuỗi. Ngược lại, nếu một luồng khác đang **đồng thời thay đổi mảng trong lúc chương trình sao chép**, không nên giả định lần copy cho ra ảnh chụp nhất quán theo một thời điểm duy nhất: cần kiểm soát đồng bộ, quyền sở hữu dữ liệu hoặc tránh cập nhật chồng lấn. Tính bất biến của chuỗi sau khi tạo **không thay thế** cơ chế đồng bộ khi dữ liệu đầu vào đang bị sửa.

## 8. UTF-16: sao chép `char[]` không đồng nghĩa sao chép “ký tự hiển thị”

`char` là một **đơn vị mã UTF-16** (16 bit). `String.length()` và độ dài mảng `string.toCharArray().length` đều đo số đơn vị mã UTF-16, không nhất thiết là số Unicode code point hay số ký tự hiển thị (*grapheme cluster*).

Ví dụ, emoji `🙂` nằm ngoài BMP và được biểu diễn bằng **hai** phần tử `char` (cặp surrogate). `toCharArray()` giữ nguyên hai đơn vị mã đó theo đúng thứ tự; `new String(array)` xây dựng lại nội dung chuỗi tương ứng.

Lưu `UnicodeCopyDemo.java` ở mã hóa UTF-8:

```java
public class UnicodeCopyDemo {
    public static void main(String[] args) {
        String original = "A🙂B";
        char[] units = original.toCharArray();
        String roundTrip = new String(units);

        System.out.println(original.length());
        System.out.println(units.length);
        System.out.println(original.codePointCount(0, original.length()));
        System.out.println(roundTrip.equals(original));

        units[0] = 'X';
        System.out.println(original);
        System.out.println(new String(units));
    }
}
```

```bash
javac -encoding UTF-8 UnicodeCopyDemo.java
java UnicodeCopyDemo
```

```text
4
4
3
true
A🙂B
X🙂B
```

Ba Unicode code point (`A`, `🙂`, `B`) chiếm bốn `char`. Sao chép sang mảng và ngược lại bảo toàn chuỗi, nhưng nếu sửa riêng **một nửa** cặp surrogate, có thể tạo dãy UTF-16 không hợp lệ. Khi muốn xử lý Unicode theo code point, cần xem `codePoints()`, `codePointAt()`, `offsetByCodePoints()` hoặc API thích hợp; việc dùng `char[]` không tự giải quyết được ranh giới code point.

## 9. Chi phí sao chép, hiệu năng và dữ liệu nhạy cảm

Hai chiều chuyển đổi có chi phí tỉ lệ với kích thước dữ liệu về mặt thao tác sao chép. Nếu vòng lặp liên tục đổi `String` ↔ `char[]`, có thể tạo thêm đối tượng, tăng cấp phát và gây áp lực bộ thu gom rác. Trước khi tối ưu, hãy chọn mô hình dữ liệu theo công việc thực tế:
- Nếu chỉ cần đọc và lưu chuỗi, tiếp tục sử dụng `String`; đừng gọi `toCharArray()` chỉ vì muốn duyệt từng ký tự khi `charAt`/`codePoints` có thể phù hợp.
- Nếu cần biến đổi hàng loạt ký tự, tạo mảng một lần, xử lý rồi tạo `String` một lần khi xong (hoặc xem xét `StringBuilder` tùy thao tác).
- Nếu một API nhận `char[]` nhưng người gọi chỉ có `String`, `toCharArray()` là chuyển đổi chuẩn; nhận thức rằng nó tạo dữ liệu mới cần được quản lý.
- Nếu một API nhận `String` nhưng người gọi sở hữu `char[]`, `new String(chars)` thể hiện rõ ý định tạo giá trị văn bản độc lập.

Trong một số bối cảnh bảo mật, mật khẩu hoặc dữ liệu bí mật được giữ ở `char[]` nhằm cho phép ghi đè **mảng mà ứng dụng sở hữu** sau khi sử dụng, ví dụ `Arrays.fill(secret, '\0')`. Khi chuyển sang `String`, ứng dụng không có cơ chế API tương đương để xóa nội dung chuỗi bất biến theo yêu cầu; vì vậy không tạo `String` chỉ để tiện xử lý nếu cần kiểm soát vòng đời dữ liệu nhạy cảm. Ngay cả khi ghi đè mảng, cũng không thể khẳng định mọi bản sao trong JVM/hệ thống đã được xóa sạch.

## 10. Lỗi phổ biến và cách tự kiểm tra

| Nhầm lẫn | Hậu quả | Cách sửa |
| --- | --- | --- |
| `char[] alias = source` là sao chép nội dung | Sửa qua `alias` đổi `source` | Dùng `clone`/`Arrays.copyOf` khi muốn mảng mới |
| `new String(source)` còn chia sẻ `char[]` nguồn | Lo lắng sai về biến đổi chuỗi | Tin vào hợp đồng copy của constructor |
| `toCharArray()` trả mảng lưu trữ bên trong `String` | Cố dùng mảng để sửa chuỗi gốc | Hiểu đây là mảng mới, sửa độc lập |
| `String.valueOf(char[])` giữ nguyên mảng | Nhầm với một dạng view | Đây là chuyển đổi thành chuỗi độc lập |
| `String.valueOf((Object) chars)` giống `String.valueOf(chars)` | Nhận văn bản dạng `[C@...` | Truyền đúng kiểu `char[]` |
| `new String(arr, from, to)` xem `to` là chỉ số cuối | Chép sai phạm vi | Tham số thứ ba là `count` |
| `getChars` tạo mảng mới | Hiểu sai nơi dữ liệu được ghi | Tự cung cấp `dst` đủ dung lượng |
| `final char[]` là mảng bất biến | Lộ thay đổi phần tử qua alias | Sao chép mảng khi nhận/trả hoặc dùng `String` |
| `toCharArray().length` bằng số ký tự người dùng nhìn thấy | Cắt sai cặp surrogate hoặc grapheme | Xem đơn vị UTF-16/code point/grapheme |

### Tự kiểm tra bằng dự đoán output

Hãy dự đoán kết quả trước khi đọc giải thích:

```java
char[] data = {'a', 'b'};
String text = new String(data);
char[] out = text.toCharArray();
data[0] = 'x';
out[1] = 'y';

System.out.println(new String(data));
System.out.println(text);
System.out.println(new String(out));
```

Đây là snippet đặt trong `main`, không phải lớp độc lập. Kết quả là:

```text
xb
ab
ay
```

Ba giá trị khác nhau vì mảng nguồn, đối tượng `String` và mảng trả về từ `toCharArray()` giữ nội dung riêng. Sửa một trong hai mảng sau khi tạo chuỗi không lan truyền sang chuỗi hay mảng còn lại.

## 11. Ghi nhớ khi lập trình

- `new String(char[])`, `String.valueOf(char[])` và `String.copyValueOf(char[])` tạo chuỗi có nội dung **độc lập** với các thay đổi tiếp theo của mảng nguồn.
- `String.toCharArray()` tạo mảng **mới**; người gọi sửa mảng thoải mái mà không sửa chuỗi nguồn.
- `char[] b = a` chỉ là **alias**, không phải sao chép; `a.clone()` hoặc `Arrays.copyOf` mới tạo mảng riêng.
- `new String(chars, offset, count)` sao chép một đoạn theo **offset và số phần tử**; `getChars(begin, end, dst, dstBegin)` sao chép vào **mảng đích sẵn có** với điểm cuối loại trừ.
- Sao chép bảo toàn các đơn vị UTF-16, nhưng không biến một `char` thành khái niệm Unicode code point hay ký tự hiển thị.
- Tính độc lập của bản sao đặc biệt hữu ích khi xây dựng API bất biến, nhưng phải cân nhắc chi phí sao chép, thời điểm đồng bộ và dữ liệu nhạy cảm theo ngữ cảnh.

## Tài liệu API Java SE 17

- [`String(char[])`, `String(char[], int, int)`, `toCharArray()` và `getChars()` — Oracle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [`Arrays.copyOf` — Oracle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html)
- [`Character` và mã Unicode — Oracle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html)
