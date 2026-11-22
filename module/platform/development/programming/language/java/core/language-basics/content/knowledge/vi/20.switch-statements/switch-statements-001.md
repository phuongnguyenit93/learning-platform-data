# Switch statement và các kiểu dữ liệu lựa chọn được hỗ trợ — Java 17+

## 1. Switch statement dùng để làm gì?

`switch` chọn cách xử lý dựa trên **một giá trị** (*selector*). Nó hữu ích khi nhiều nhánh cùng so một mã lệnh, ký tự, trạng thái enum hoặc giá trị rời rạc.

~~~java
int option = 2;

switch (option) {
    case 1:
        System.out.println("Create");
        break;
    case 2:
        System.out.println("Update");
        break;
    default:
        System.out.println("Unknown");
}
~~~

**Exact output:**

~~~text
Update
~~~

Trong Java 17, cần phân biệt:

- **Switch statement**: thực thi câu lệnh hoặc khối lệnh; **không tự trả một giá trị** cho phép gán.
- **Switch expression**: tạo một giá trị bằng `switch` ở vị trí biểu thức; có quy tắc khác về tính đầy đủ của các nhánh và `yield`. Bài này tập trung vào **switch statement**.

Có thể viết switch statement bằng cú pháp truyền thống `case ...:` hoặc cú pháp nhánh mũi tên `case ... ->` (đã ổn định trước Java 17).

## 2. Các kiểu selector được hỗ trợ trong Java 17

Trong cú pháp switch thông thường, ổn định của Java 17, biểu thức `switch (selector)` có thể thuộc các kiểu:

| Nhóm | Kiểu selector hợp lệ | Ví dụ |
|---|---|---|
| Số nguyên nguyên thủy | `byte`, `short`, `char`, `int` | `switch (code)` với `int code` |
| Lớp bao tương ứng | `Byte`, `Short`, `Character`, `Integer` | `switch (boxedCode)` |
| Chuỗi | `String` | `switch (command)` |
| Liệt kê | Một kiểu `enum` cụ thể | `switch (status)` với `Status status` |

**Không được dùng trực tiếp**: `long`/`Long`, `float`/`Float`, `double`/`Double`, `boolean`/`Boolean`, `Object`, mảng hoặc một class tùy ý.

~~~java
long bigId = 10L;
// switch (bigId) { case 10 -> System.out.println("ten"); }
// LỖI BIÊN DỊCH ở Java 17: long không phải kiểu selector hợp lệ.

boolean enabled = true;
// switch (enabled) { case true -> System.out.println("enabled"); }
// LỖI BIÊN DỊCH ở Java 17: boolean không được hỗ trợ.
~~~

Một trường hợp đặc biệt: nếu selector có **kiểu tĩnh `Object`**, việc object ở runtime tình cờ chứa một `Integer` không biến `switch (object)` thành switch hợp lệ. Compiler kiểm tra **kiểu biểu thức**, không suy từ giá trị runtime.

**Phạm vi phiên bản:** Java 17 có tính năng *pattern matching for switch* ở trạng thái preview, phải bật tùy chọn preview và có các quy tắc khác. Ví dụ trong bài dùng **switch Java 17 ổn định**, biên dịch bằng `--release 17`, **không bật preview**.

## 3. Nhận diện dấu hai chấm và fall-through

Ở dạng truyền thống, `case VALUE:` đánh dấu điểm bắt đầu thực thi. Nếu không có `break`, `return` hay `throw`, Java có thể chạy các câu lệnh sau nhãn kế tiếp mà không kiểm tra lại selector. Đây là *fall-through*, không có nghĩa nhiều giá trị cùng khớp. Bài về dạng dấu hai chấm và bài `break` phân tích luồng này đầy đủ.

## 4. Nhận diện switch statement dạng mũi tên `->`

Java 17 cho phép `case 2, 3 -> System.out.println("two or three");`. Khi thực hiện xong nhánh mũi tên, chương trình không rơi xuống nhánh sau. Vế phải có thể là statement expression, khối `{ ... }` hoặc `throw`.

Mũi tên không tự biến switch thành **expression**: ví dụ trên vẫn là statement thực hiện thao tác. Bài về khối nhánh mũi tên trình bày riêng cú pháp và phạm vi biến.

## 5. Selector số nguyên nhỏ: `byte`, `short`, `char`, `int`

Các kiểu nguyên thủy được hỗ trợ trực tiếp:

~~~java
byte byteCode = 1;
short shortCode = 300;
char letter = 'A';
int action = 2;

switch (byteCode) {
    case 1 -> System.out.println("byte one");
    default -> System.out.println("byte other");
}

switch (shortCode) {
    case 300 -> System.out.println("short 300");
    default -> System.out.println("short other");
}

switch (letter) {
    case 'A' -> System.out.println("letter A");
    default -> System.out.println("other letter");
}

switch (action) {
    case 2 -> System.out.println("action two");
    default -> System.out.println("other action");
}
~~~

Java kiểm tra **giá trị nhãn `case` có tương thích miền kiểu selector**:

~~~java
byte small = 10;
// switch (small) {
//     case 128 -> System.out.println("impossible");
// }
// LỖI BIÊN DỊCH: 128 vượt giới hạn byte (-128..127).
~~~

Với `char`, nhãn có thể dùng ký tự như `'A'` hoặc biểu thức hằng số nguyên phù hợp. `'A'` và `65` cùng một giá trị, nên không được đặt thành hai nhãn case trùng nhau.

## 6. Nhãn `case` số nguyên phải là hằng tại compile time

Trong switch dùng nhãn hằng truyền thống, `case` số nguyên phải là **biểu thức hằng** phù hợp; một biến thông thường không hợp lệ chỉ vì đang chứa đúng số.

~~~java
static final int OPEN = 1; // constant variable hợp lệ

int option = 1;
switch (option) {
    case OPEN -> System.out.println("open");
    default -> System.out.println("unknown");
}
~~~

Một lỗi thường gặp:

~~~java
int dynamicCode = 1;
// switch (option) {
//     case dynamicCode -> System.out.println("open");
// }
// LỖI BIÊN DỊCH: dynamicCode không phải constant expression.
~~~

`final int` được khởi tạo bằng biểu thức hằng phù hợp có thể dùng làm nhãn. Nhưng `final` đơn thuần **không biến mọi giá trị tính ở runtime thành hằng compile time**.

Ví dụ `final int code = Integer.parseInt("1")` không dùng được làm nhãn `case code` dù code không bị gán lại.

**Nhãn trùng giá trị** là lỗi biên dịch:

~~~java
// case 1 -> ...;
// case 1 -> ...; // LỖI: duplicate case label.
~~~

## 7. Selector `String`: so nội dung, phân biệt hoa/thường

`switch` trên `String` lựa chọn theo **nội dung chuỗi**, không yêu cầu hai biến `String` cùng tham chiếu object.

~~~java
String command = new String("start");

switch (command) {
    case "start" -> System.out.println("starting");
    case "stop" -> System.out.println("stopping");
    default -> System.out.println("unknown");
}
~~~

**Exact output:**

~~~text
starting
~~~

Nhãn `case "start"` phải là hằng `String` tại compile time. Java so nội dung cho mục đích chọn case, tương ứng với nguyên tắc `String.equals`, **không dựa vào `==` tham chiếu**.

**Phân biệt hoa/thường:** `"start"` và `"START"` không khớp như nhau. Nếu muốn không phân biệt hoa/thường, chuẩn hóa đầu vào **theo quy tắc rõ ràng** trước khi switch, ví dụ `command.toLowerCase(Locale.ROOT)` đối với một tập lệnh ASCII không phân biệt chữ hoa/thường.

Không tự gọi `toLowerCase()` trên input chưa được kiểm tra null.

## 8. Selector `enum`: nhãn là tên hằng enum

~~~java
enum Status {
    NEW, RUNNING, DONE
}

Status status = Status.RUNNING;
switch (status) {
    case NEW -> System.out.println("created");
    case RUNNING -> System.out.println("working");
    case DONE -> System.out.println("finished");
}
~~~

**Exact output:**

~~~text
working
~~~

Trong một switch có selector kiểu `Status`, nhãn enum viết dạng **`case RUNNING`**, không viết `case Status.RUNNING` trong cú pháp switch enum thông thường của Java 17. Các nhãn enum phải thuộc kiểu enum đang dùng.

**Switch statement không bắt buộc luôn có `default`**. Tuy nhiên, nếu muốn xử lý một enum value chưa liệt kê hoặc giúp code rõ ràng khi enum thay đổi, hãy quyết định chính sách `default` phù hợp. Với switch expression, tính đầy đủ của các nhánh có yêu cầu riêng.

## 9. Các wrapper `Byte`, `Short`, `Character`, `Integer`

Bốn lớp bao sau đều được dùng làm selector Java 17 ổn định:

~~~java
Byte boxedByte = 1;
Short boxedShort = 300;
Character boxedChar = 'A';
Integer boxedInt = 7;

switch (boxedByte) {
    case 1 -> System.out.println("Byte one");
    default -> System.out.println("Byte other");
}
switch (boxedShort) {
    case 300 -> System.out.println("Short 300");
    default -> System.out.println("Short other");
}
switch (boxedChar) {
    case 'A' -> System.out.println("Character A");
    default -> System.out.println("Character other");
}
switch (boxedInt) {
    case 7 -> System.out.println("Integer seven");
    default -> System.out.println("Integer other");
}
~~~

Wrapper là tham chiếu đối tượng nhưng selector kiểu này được xử lý theo các giá trị nguyên tương ứng; cần lưu ý **unboxing** khi selector nullable.

Không mở rộng kết luận này thành “mọi wrapper đều được hỗ trợ”: **`Long`**, **`Float`**, **`Double`** và **`Boolean`** không phải selector hợp lệ trong switch Java 17 thông thường.

## 10. Selector kiểu tham chiếu là `null`

Với `String`, enum hoặc wrapper được phép làm selector, Java 17 tiêu chuẩn ném `NullPointerException` nếu selector là `null`; `default` chỉ xử lý **giá trị không khớp case**. Kiểm tra null trước khi switch nếu đầu vào có thể thiếu:

~~~java
if (command == null) {
    System.out.println("missing command");
} else {
    switch (command) {
        case "start" -> System.out.println("start");
        default -> System.out.println("unknown");
    }
}
~~~

Chính sách trả kết quả hoặc ném lỗi với đầu vào thiếu được phân tích ở bài chuyên về `null`.

## 11. Khi nào nên dùng `if` thay cho `switch`?

`switch` phù hợp với nhiều giá trị rời rạc của một selector hợp lệ. Các ngưỡng (`age >= 18`), khoảng số, tổ hợp nhiều điều kiện hoặc ưu tiên thường rõ hơn bằng `if/else if`. Không ép `long` hay `double` sang `int` chỉ để viết switch nếu có thể làm mất thông tin. Bài cuối chương cung cấp quy trình chọn cấu trúc bằng ví dụ nghiệp vụ.

## 12. Chương trình Java 17 hoàn chỉnh, chạy độc lập

Tạo file đúng tên **`SwitchStatementTypesDemo.java`**:

~~~java
public final class SwitchStatementTypesDemo {
    private SwitchStatementTypesDemo() {}

    enum Status {
        NEW, RUNNING, DONE
    }

    static final int OPEN = 1;

    static void showInt(int value) {
        switch (value) {
            case OPEN:
                System.out.println("int=open");
                break;
            case 2:
            case 3:
                System.out.println("int=two-or-three");
                break;
            default:
                System.out.println("int=other");
        }
    }

    static void showByte(byte value) {
        switch (value) {
            case -1 -> System.out.println("byte=negative-one");
            case 127 -> System.out.println("byte=max");
            default -> System.out.println("byte=other");
        }
    }

    static void showShort(short value) {
        switch (value) {
            case 300 -> System.out.println("short=300");
            default -> System.out.println("short=other");
        }
    }

    static void showChar(char value) {
        switch (value) {
            case 'A' -> System.out.println("char=A");
            default -> System.out.println("char=other");
        }
    }

    static void showString(String command) {
        switch (command) {
            case "start" -> System.out.println("string=start");
            case "stop" -> System.out.println("string=stop");
            default -> System.out.println("string=other");
        }
    }

    static void showStatus(Status status) {
        switch (status) {
            case NEW -> System.out.println("enum=new");
            case RUNNING -> System.out.println("enum=running");
            case DONE -> System.out.println("enum=done");
        }
    }

    static void showInteger(Integer value) {
        switch (value) {
            case 7 -> System.out.println("Integer=seven");
            default -> System.out.println("Integer=other");
        }
    }

    static void showWrappers() {
        Byte b = 1;
        Short s = 300;
        Character c = 'A';

        switch (b) {
            case 1 -> System.out.println("Byte=one");
            default -> System.out.println("Byte=other");
        }
        switch (s) {
            case 300 -> System.out.println("Short=300");
            default -> System.out.println("Short=other");
        }
        switch (c) {
            case 'A' -> System.out.println("Character=A");
            default -> System.out.println("Character=other");
        }
    }

    static void showFallThrough(int value) {
        switch (value) {
            case 1:
                System.out.println("fall=one");
                break;
            case 2:
                System.out.println("fall=two");
            case 3:
                System.out.println("fall=three");
                break;
            default:
                System.out.println("fall=other");
        }
    }

    public static void main(String[] args) {
        showInt(1);
        showInt(2);
        showInt(9);

        showByte((byte) -1);
        showByte((byte) 127);
        showShort((short) 300);
        showChar('A');

        showString(new String("start"));
        showString("START");
        showStatus(Status.RUNNING);

        showWrappers();
        showInteger(Integer.valueOf(7));

        showFallThrough(2);

        String missing = null;
        try {
            showString(missing);
        } catch (NullPointerException ex) {
            System.out.println("null String=NullPointerException");
        }

        Integer missingNumber = null;
        try {
            showInteger(missingNumber);
        } catch (NullPointerException ex) {
            System.out.println("null Integer=NullPointerException");
        }
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên; terminal tại thư mục chứa `SwitchStatementTypesDemo.java`. Chương trình không dùng thư viện bên ngoài JDK hoặc preview feature.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 SwitchStatementTypesDemo.java
java -cp . SwitchStatementTypesDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\SwitchStatementTypesDemo.java
java -cp . SwitchStatementTypesDemo
~~~

### Exact expected stdout

~~~text
int=open
int=two-or-three
int=other
byte=negative-one
byte=max
short=300
char=A
string=start
string=other
enum=running
Byte=one
Short=300
Character=A
Integer=seven
fall=two
fall=three
null String=NullPointerException
null Integer=NullPointerException
~~~

**Đọc kết quả:**

1. `int=open` chứng minh `case OPEN` là hằng compile time, dùng được làm nhãn.
2. `int=two-or-three` minh họa nhiều nhãn dùng chung một hành động.
3. `byte`, `short`, `char`, `int` và bốn wrapper tương ứng đều được dùng làm selector.
4. `new String("start")` vẫn khớp `case "start"`: switch so **nội dung String**; `"START"` rơi vào default vì phân biệt hoa/thường.
5. Enum chọn hằng `RUNNING` bằng tên không kèm prefix kiểu.
6. `fall=two` và `fall=three` cho thấy dạng dấu `:` có thể fall-through khi thiếu `break`.
7. Selector `String` hoặc `Integer` null ném NPE; `default` không bắt null trong switch Java 17 ổn định.

## 13. Lỗi thường gặp

| Lỗi hoặc ngộ nhận | Hệ quả | Cách đúng |
|---|---|---|
| `switch(longValue)` trong Java 17 | Không compile | `if/else` hoặc thiết kế mã int rõ |
| `switch(booleanFlag)` | Không compile | `if (flag) ... else ...` |
| `switch(doubleValue)` | Không compile | Điều kiện số thực có chính sách sai số phù hợp |
| `switch(object)` với `Object` đang chứa Integer | Kiểu tĩnh Object không hợp lệ | Dùng selector có kiểu cụ thể |
| `case variable:` với biến runtime | Nhãn không là compile-time constant | Hằng `static final` hoặc biểu thức hằng |
| Hai nhãn case cùng giá trị | Duplicate case compile error | Loại bỏ trùng lặp |
| `case 128` với selector byte | Ngoài miền kiểu byte | Chọn nhãn biểu diễn được |
| Thiếu `break` trong nhánh `case:` | Fall-through ngoài ý muốn | Thêm `break` hoặc dùng `->` |
| Mong `default` xử lý selector null | Null gây NPE | Guard null trước switch |
| Mong `switch(String)` so tham chiếu | Thực tế so nội dung | Hiểu case-sensitive nội dung |
| Viết `case Status.RUNNING` trong switch enum thường | Sai dạng nhãn enum Java 17 | Viết `case RUNNING` |
| Nghĩ dạng `->` luôn là switch expression | Switch statement cũng dùng `->` | Phân biệt ngữ cảnh và mục đích |
| Đọc tài liệu `case null` của phiên bản khác rồi áp dụng trực tiếp | Khác chuẩn Java 17 không preview | Kiểm tra phiên bản/cờ preview |

## 14. Bài tập và đáp án

### Bài A — selector nào hợp lệ?

Xét `byte`, `long`, `Character`, `String`, `boolean`, `Status enum`, `Double`, `Integer`.

**Đáp án:** `byte`, `Character`, `String`, `Status` và `Integer` hợp lệ; `long`, `boolean`, `Double` không hợp lệ với switch thông thường ổn định trong Java 17.

### Bài B — fall-through

~~~java
int x = 1;
switch (x) {
    case 1:
        System.out.println("A");
    case 2:
        System.out.println("B");
        break;
    default:
        System.out.println("C");
}
~~~

**Đáp án:**

~~~text
A
B
~~~

Thiếu `break` sau nhánh 1 nên tiếp tục chạy nhánh 2.

### Bài C — tránh fall-through

Viết lại để `x = 1` chỉ in `A` bằng cú pháp Java 17:

~~~java
switch (x) {
    case 1 -> System.out.println("A");
    case 2 -> System.out.println("B");
    default -> System.out.println("C");
}
~~~

**Đáp án:** Chỉ in `A`. Dạng `->` không fall-through.

### Bài D — String khác tham chiếu

~~~java
String command = new String("stop");
switch (command) {
    case "stop" -> System.out.println("matched");
    default -> System.out.println("other");
}
~~~

**Đáp án:** `matched`, vì switch String so **nội dung**, không phải object identity.

### Bài E — wrapper null

~~~java
Integer code = null;
// switch (code) {
//     case 1 -> System.out.println("one");
//     default -> System.out.println("other");
// }
~~~

**Đáp án:** Khi thực thi switch trên `code` null, ném `NullPointerException`, không chạy default. Phải kiểm tra null trước.

### Bài F — chọn switch hay if?

Yêu cầu: phân loại tuổi `age >= 18 && age < 65`, hoặc xử lý command `"start"`/`"stop"`.

**Đáp án:** dùng `if` cho điều kiện **miền tuổi**, dùng `switch(String)` cho **các giá trị command rời rạc**.

## 15. Checklist và kết luận

- [ ] Biết switch statement chọn nhánh dựa trên selector có **kiểu hỗ trợ**.
- [ ] Nhớ bốn primitive được hỗ trợ: `byte`, `short`, `char`, `int`.
- [ ] Nhớ bốn wrapper tương ứng: `Byte`, `Short`, `Character`, `Integer`.
- [ ] Biết `String` và kiểu `enum` cụ thể cũng dùng được làm selector.
- [ ] Biết `long`, `float`, `double`, `boolean` và wrapper tương ứng không được dùng trực tiếp ở Java 17 ổn định.
- [ ] Nhãn `case` hằng phải hợp lệ về kiểu, giá trị và không bị trùng.
- [ ] Biết switch String so nội dung và phân biệt chữ hoa/thường.
- [ ] Biết nhãn enum thông thường viết `case RUNNING`, không `case Status.RUNNING`.
- [ ] Hiểu `case:` cần `break` khi không muốn fall-through.
- [ ] Hiểu `case ->` không fall-through và **vẫn có thể là statement**.
- [ ] Guard selector null trước switch; `default` không bắt null trong Java 17 không preview.
- [ ] Dùng `if/else` cho điều kiện miền/ràng buộc không thể biểu đạt bằng case constant.
- [ ] Chạy `SwitchStatementTypesDemo.java` trên Java 17+ bằng `javac`/`java`, đối chiếu stdout.

**Kết luận:** Với switch statement Java 17 ổn định, các selector được hỗ trợ là **`byte`/`short`/`char`/`int`**, **bốn wrapper tương ứng**, **`String`** và **`enum`**. Nhãn `case` phải đúng kiểu và quy tắc hằng; dạng dấu `:` có thể fall-through, còn dạng `->` giúp tránh điều đó. Đặc biệt, hãy kiểm tra **null** trước khi switch với kiểu tham chiếu và chọn `if/else` khi cần điều kiện quan hệ/phức tạp.