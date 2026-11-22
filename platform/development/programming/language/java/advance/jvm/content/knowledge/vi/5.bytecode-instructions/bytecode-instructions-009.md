# `checkcast`, `instanceof`, `arraylength` và kiểm tra khi truy cập mảng

Trong mô hình thực thi JVM, **`checkcast`**, **`instanceof`** và **`arraylength`** là ba bytecode instruction có mục đích khác nhau. Hai lệnh đầu làm việc với **giá trị tham chiếu và kiểu đối tượng tại runtime**; lệnh thứ ba lấy **độ dài của đối tượng mảng**. Khi chương trình truy cập phần tử mảng, các lệnh như `iaload`, `aastore` còn thực hiện những kiểm tra riêng về **null**, **chỉ số hợp lệ** và **kiểu phần tử được lưu**.

Hiểu các lệnh này giúp giải thích vì sao Java có thể biên dịch thành công nhưng khi chạy lại gặp `ClassCastException`, `NullPointerException`, `ArrayIndexOutOfBoundsException` hoặc `ArrayStoreException`. Đồng thời, nó cho thấy JVM bytecode có những kiểm tra động **khác** với bytecode verifier: verifier kiểm tra tính hợp lệ về cấu trúc/kiểu của mã trước khi thực thi, còn các instruction thực hiện kiểm tra trên **giá trị thực tế của chương trình**.

## 1. Bức tranh tổng quan

| Instruction/nhóm | Đối tượng thao tác | Đầu vào trên operand stack | Kết quả chính | Lỗi runtime điển hình |
| --- | --- | --- | --- | --- |
| `checkcast` | Kiểu tham chiếu đích | Một reference | Giữ lại chính reference nếu cast hợp lệ | `ClassCastException` |
| `instanceof` | Kiểu tham chiếu đích | Một reference | `int` 1 hoặc 0 | Không ném `ClassCastException` khi không khớp kiểu |
| `arraylength` | Mảng | Một array reference | `int` là độ dài | `NullPointerException` nếu reference là `null` |
| `*aload` | Phần tử mảng | Array reference và chỉ số `int` | Giá trị phần tử | `NullPointerException`, `ArrayIndexOutOfBoundsException` |
| `*astore` | Phần tử mảng | Array reference, chỉ số, giá trị ghi | Không đẩy kết quả | `NullPointerException`, `ArrayIndexOutOfBoundsException`; với `aastore` còn có thể là `ArrayStoreException` |

Trong bảng, `*aload` và `*astore` là **tên nhóm**, không phải tên opcode hợp lệ để ghi nguyên văn vào class file. JVM có những opcode riêng như `iaload`, `aaload`, `iastore`, `aastore`.

Ba nguyên tắc cần nhớ:

1. **`checkcast` kiểm tra khả năng chuyển reference sang kiểu đích**, không tạo object mới, không sửa runtime class của object.
2. **`instanceof` hỏi một reference có tương thích với kiểu đích hay không**; nó trả `0` hoặc `1` trên operand stack, sau đó bytecode rẽ nhánh có thể sử dụng kết quả.
3. **Mảng Java là object có độ dài cố định**, và các instruction truy cập phần tử phải xử lý null, bounds và (với reference array) khả năng gán kiểu tại runtime.

## 2. Nhắc lại: reference, operand stack và kiểu runtime

Trong Java:

```java
Object value = "JVM";
String text = (String) value;
```

`value` được khai báo với kiểu tĩnh `Object`, nhưng ở runtime nó giữ reference tới một `String`. Biến `text` nhận cùng reference sau phép cast hợp lệ. Trình biên dịch Java xác minh cách viết có thể cast theo quy tắc ngôn ngữ; JVM **kiểm tra object thực tế** khi chạy bytecode `checkcast`.

Với operand stack, các reference đều là **category 1**. Ký hiệu dưới đây viết theo thứ tự **dưới → trên**; `value` nằm ở đỉnh:

```text
... , value
            ↑
           TOP
```

Một giá trị reference trên stack không phải toàn bộ nội dung object được sao chép vào stack. JVM sử dụng nó để truy cập object hay array. Khi `checkcast` thành công, **reference vẫn như cũ**. `instanceof` thì tiêu thụ reference và **đẩy kết quả `int`**. Những chi tiết này quyết định instruction kế tiếp có thể làm gì.

## 3. `checkcast`: kiểm tra kiểu reference khi chạy

### 3.1. Cú pháp bytecode và hiệu ứng stack

Opcode `checkcast` là **`0xC0`**. Instruction mang một chỉ số hai byte tham chiếu tới thông tin kiểu đích trong constant pool (một `CONSTANT_Class` phù hợp).

```text
Trước: ..., objectref
checkcast <target-type>
Sau nếu thành công: ..., objectref
```

- Nếu `objectref` là **`null`**, `checkcast` **thành công**, giữ `null` trên stack.
- Nếu reference khác `null` và object runtime tương thích với kiểu đích, instruction **thành công**, giữ **chính reference đó**.
- Nếu object không thể chuyển sang kiểu đích, instruction ném **`ClassCastException`**.
- Việc phân giải kiểu đích từ constant pool cũng có thể gặp vấn đề liên kết/lớp trong những tình huống riêng; đừng mặc định mọi lỗi nạp class đều là `ClassCastException`.

Ví dụ hợp lệ:

```java
Object value = "hello";
String text = (String) value;
System.out.println(text.length());
```

Đây là **đoạn mã đặt trong một method**, không phải chương trình hoàn chỉnh. `value` giữ một `String`; compiler có thể dùng `checkcast java/lang/String` sau khi nạp reference để bảo đảm loại object trước khi gọi `String.length()`.

Ví dụ không hợp lệ tại runtime:

```java
Object value = Integer.valueOf(42);
String text = (String) value; // ClassCastException tại runtime
```

Đoạn này vẫn có thể **biên dịch**, vì kiểu tĩnh `Object` cho phép cast tường minh sang `String`. Nhưng object thực tế là `Integer`. Không có thao tác chuyển nội dung số `42` thành chuỗi `"42"` ở instruction `checkcast`.

### 3.2. Cast không tương đương chuyển đổi giá trị

```java
Object number = Integer.valueOf(42);
String converted = String.valueOf(number); // "42"
```

`String.valueOf` thực hiện thao tác tạo/nhận chuỗi theo API, còn `(String) number` kiểm tra **khả năng dùng reference như String**. Chúng có ngữ nghĩa hoàn toàn khác.

Phép cast nguyên thủy cũng khác: `(int) 3.7` dùng cơ chế chuyển đổi số tương ứng (chẳng hạn `d2i`), **không** dùng `checkcast` vì toán hạng không phải reference.

### 3.3. Kiểm tra kiểu được làm ở đâu?

`javac` kiểm tra tính hợp lệ của biểu thức cast theo **hệ thống kiểu nguồn**. Khi cần một phép cast reference còn phải kiểm tra động, compiler sinh `checkcast`. Những cast chắc chắn thừa có thể không sinh instruction kiểm tra riêng; do đó **không phải mọi dấu ngoặc cast trong source đều ứng với một opcode `checkcast`**.

Trong Java generic sau type erasure, compiler cũng có thể thêm `checkcast` sau khi lấy giá trị từ API generic đã xóa kiểu. Ví dụ gán một kết quả `List<String>.get(...)` vào `String` có thể cần `checkcast java/lang/String` tại bytecode, dù source không viết cast tường minh.

**Lưu ý generic:** JVM có thể kiểm tra runtime object có là `List` hay không nhưng thường không có cơ chế từ một reference đơn lẻ để xác minh mọi phần tử của nó đều là `String`. Tham số generic đã được erase ở descriptor; đây là lý do unchecked cast và heap pollution cần được hiểu riêng.

## 4. `instanceof`: kiểm tra kiểu và cho ra `int` 0/1

Opcode `instanceof` là **`0xC1`**; nó cũng tham chiếu kiểu đích qua chỉ số constant pool.

```text
Trước: ..., objectref
instanceof <target-type>
Sau:   ..., result (int)
```

- Reference là `null` → kết quả **`0`**.
- Reference không `null`, object tương thích với target type → **`1`**.
- Reference không `null`, object không tương thích → **`0`**.
- `instanceof` không ném `ClassCastException` chỉ vì kiểu không khớp. Tuy nhiên những lỗi về phân giải kiểu được chỉ định có thể tồn tại độc lập.

Ở Java source, `instanceof` có kết quả **`boolean`**. Ở mức operand stack của JVM, giá trị điều kiện được biểu diễn bằng `int` 0/1 và có thể dùng với các lệnh như `ifeq` hoặc `ifne`.

Ví dụ:

```java
Object value = "abc";
if (value instanceof String) {
    System.out.println("Đây là String");
}
```

Đây là đoạn mã đặt trong method; compiler có thể sinh `instanceof java/lang/String`, rồi `ifeq` để bỏ qua nhánh nếu kết quả bằng 0.

### 4.1. `instanceof` và `checkcast` thường đi cùng nhau

Đoạn source:

```java
static int textLength(Object value) {
    if (value instanceof String) {
        return ((String) value).length();
    }
    return -1;
}
```

là **method phụ trợ**, cần đặt trong một class Java để biên dịch. Ở các compiler điển hình, nhánh điều kiện dùng `instanceof`, và khi truy cập `String.length()`, một `checkcast` giúp đưa reference về dạng mà bytecode dùng cho thao tác đó.

Tuy hai instruction thường đứng gần nhau, **chúng không thay thế nhau**:

| Trường hợp | `instanceof String` | `(String) value` / `checkcast String` |
| --- | --- | --- |
| `value` là reference tới `String` | `true` (bytecode trả 1) | Thành công, giữ reference |
| `value` là reference tới `Integer` | `false` (bytecode trả 0) | Ném `ClassCastException` |
| `value` là `null` | `false` (bytecode trả 0) | Thành công, kết quả vẫn `null` |

**Đặc biệt:** `(String) null` **không tự gây `NullPointerException`**. Nhưng nếu dùng kết quả `null` để gọi `length()`, câu lệnh gọi instance method có thể gây `NullPointerException`.

### 4.2. Pattern matching cho `instanceof` (Java 17)

Java 17 hỗ trợ pattern matching kiểu:

```java
static String describe(Object value) {
    if (value instanceof String text) {
        return "String length=" + text.length();
    }
    return "other";
}
```

`text` là **pattern variable** được compiler giới hạn phạm vi trong nhánh biết chắc kiểu khớp. Điều này làm source ngắn hơn và tránh việc lập trình viên viết lại cast thủ công; **không có nghĩa JVM có opcode riêng tên `instanceof_pattern`**. Bytecode có thể vẫn gồm `instanceof`, rẽ nhánh, cast khi cần và store vào local variable. Xem `javap -c` để biết compiler cụ thể tạo gì.

## 5. Kiểu array cũng tham gia `checkcast` và `instanceof`

Mảng Java là object; mỗi mảng có **runtime array class** với element type và số chiều. Vì vậy các phép kiểm tra reference cũng áp dụng cho mảng:

```java
Object values = new String[2];
boolean b1 = values instanceof String[]; // true
boolean b2 = values instanceof Object[]; // true
boolean b3 = values instanceof int[];    // false
String[] names = (String[]) values;       // thành công
```

Đây là đoạn source đặt trong method. Nó minh họa `String[]` là một reference type, không cần phần tử mảng đang chứa một chuỗi cụ thể nào để `instanceof String[]` trả `true`.

Các kiểu mảng reference có quy tắc **covariance**: ví dụ `String[]` có thể được tham chiếu qua `Object[]`. Nhưng runtime component type của object vẫn là `String`; khi ghi phần tử, `aastore` phải kiểm tra khả năng gán.

```java
Object[] base = new String[1];
base[0] = "ok";
base[0] = new Object(); // ArrayStoreException tại runtime
```

Đoạn này **không phải** lỗi `ClassCastException`. Phép gán biến `Object[] base = new String[1]` được phép theo covariance. Lỗi chỉ phát sinh khi thực sự cố **lưu một đối tượng không tương thích** vào mảng có runtime component type là `String`.

Mảng primitive như `int[]` cũng là object, nhưng **không phải `Object[]`**, vì phần tử của nó không phải reference. Một `int[]` có thể gán vào biến kiểu `Object`, nhưng không thể gán trực tiếp vào biến kiểu `Object[]`.

## 6. `arraylength`: lấy số phần tử của mảng

Opcode `arraylength` là **`0xBE`**, không có toán hạng constant-pool index.

```text
Trước: ..., arrayref
arraylength
Sau:   ..., length (int)
```

- Nếu `arrayref` là reference tới mảng hợp lệ, JVM đọc **độ dài của mảng** và đẩy kết quả kiểu `int`.
- Nếu `arrayref == null`, instruction ném **`NullPointerException`**.
- Độ dài mảng là **số phần tử**, không phải dung lượng byte. Ví dụ `new long[3]` có `length == 3`, không phải 24.
- Độ dài mảng không thay đổi sau khi object mảng được tạo. Muốn số phần tử khác, tạo một đối tượng mảng khác hoặc dùng cấu trúc động như `ArrayList`.

Ví dụ:

```java
int[] values = {10, 20, 30};
System.out.println(values.length); // 3
```

Điểm khác biệt quan trọng: cú pháp Java `values.length` là **thuộc tính đặc biệt của array type**, và compiler thường sinh opcode **`arraylength`**, không phải `getfield length` của một class Java thông thường. Đối với `String`, `text.length()` là **lời gọi method**, hoàn toàn khác.

### `arraylength` không kiểm tra bounds

`arraylength` chỉ cần array reference; nó **không nhận chỉ số phần tử**. Kiểm tra chỉ số diễn ra ở `*aload`/`*astore`. Ví dụ:

```java
int[] values = new int[2];
int n = values.length; // n = 2, không truy cập phần tử
int x = values[2];     // ArrayIndexOutOfBoundsException
```

Đây là đoạn minh họa đặt trong method, không phải một chương trình chạy độc lập. Với một mảng có độ dài `n`, chỉ số hợp lệ là **`0 <= index < n`**; chỉ số âm cũng không hợp lệ.

### Mảng nhiều chiều

Java biểu diễn mảng nhiều chiều dưới dạng **mảng chứa các mảng con**:

```java
int[][] grid = { {1, 2, 3}, {4} };
System.out.println(grid.length);    // 2: số hàng
System.out.println(grid[0].length); // 3: số phần tử hàng đầu
System.out.println(grid[1].length); // 1: độ dài hàng thứ hai
```

`grid.length` và `grid[0].length` là hai lần `arraylength` áp dụng lên **hai array reference khác nhau**. Java không buộc mọi mảng con phải có cùng độ dài. Nếu một hàng bằng `null`, dùng `grid[i].length` có thể gặp `NullPointerException`.

## 7. Các lệnh `*aload`: đọc phần tử mảng

Mỗi loại phần tử có instruction thích hợp:

| Opcode | Mảng tương ứng | Loại giá trị được đẩy |
| --- | --- | --- |
| `iaload` | `int[]` | `int` |
| `laload` | `long[]` | `long` (category 2) |
| `faload` | `float[]` | `float` |
| `daload` | `double[]` | `double` (category 2) |
| `aaload` | Mảng kiểu tham chiếu, ví dụ `String[]` | Reference |
| `baload` | `byte[]` hoặc `boolean[]` | Giá trị được đưa lên operand stack theo dạng `int` |
| `caload` | `char[]` | `int` (zero-extended từ `char`) |
| `saload` | `short[]` | `int` (sign-extended từ `short`) |

`baload` khi đọc `byte[]` sign-extend byte có dấu thành `int`; với `boolean[]`, biểu diễn true/false tuân thủ quy tắc tương ứng của JVM. `caload` giữ giá trị không dấu của `char` khi đưa lên stack.

Hiệu ứng stack tổng quát:

```text
Trước: ..., arrayref, index(int)
*aload
Sau:   ..., value
```

Các kiểm tra quan trọng:

1. Array reference phải khác `null`, nếu không → **`NullPointerException`**.
2. Chỉ số phải trong phạm vi `0..length-1`, nếu không → **`ArrayIndexOutOfBoundsException`**.
3. Operand và opcode phải phù hợp với kiểu mảng theo các ràng buộc về kiểu của bytecode; JVM verifier bảo vệ khỏi việc tùy ý dùng `iaload` như thể tham chiếu tới `String[]` là mảng `int[]`.

**Khi cả array reference là `null` và index là giá trị ngoài phạm vi**, không có mảng hợp lệ để xác định bounds: lỗi null sẽ xảy ra thay vì kết luận về bounds của một đối tượng không tồn tại. Trên một mảng hợp lệ, chỉ số âm hay `>= length` đều sai.

### Ví dụ đọc kiểu hẹp

```java
byte[] bytes = {(byte) 0xFF};
char[] chars = {(char) 255};
short[] shorts = {(short) -2};

System.out.println(bytes[0]);       // -1
System.out.println((int) chars[0]); // 255
System.out.println(shorts[0]);      // -2
```

Đoạn ví dụ này đặt trong `main` hoặc method tương đương. Sự khác biệt `-1` và `255` giúp thấy `byte` là kiểu có dấu, còn `char` là đơn vị mã UTF-16 không dấu; compiler/JVM thực hiện chuyển đổi tương ứng khi đẩy giá trị lên operand stack.

## 8. Các lệnh `*astore`: ghi phần tử mảng

| Opcode | Mảng được ghi | Giá trị ghi |
| --- | --- | --- |
| `iastore` | `int[]` | `int` |
| `lastore` | `long[]` | `long` |
| `fastore` | `float[]` | `float` |
| `dastore` | `double[]` | `double` |
| `aastore` | Mảng reference như `Object[]`, `String[]` | Reference, có kiểm tra runtime component type |
| `bastore` | `byte[]`, `boolean[]` | Giá trị phù hợp được xử lý từ dạng `int` |
| `castore` | `char[]` | Giá trị phù hợp được chuyển về `char` |
| `sastore` | `short[]` | Giá trị phù hợp được chuyển về `short` |

Hiệu ứng stack tổng quát:

```text
Trước: ..., arrayref, index(int), value
*astore
Sau:   ...
```

`lastore` và `dastore` tiêu thụ một giá trị **category 2**; các opcode còn lại nhận loại toán hạng theo quy tắc tương ứng. Sau khi store thành công, instruction **không để lại chính giá trị đã ghi** trên stack. Nếu biểu thức gán phải có kết quả, compiler có thể dùng `dup_x2` hoặc `dup2_x2` thích hợp để giữ bản sao giá trị trước khi store.

### 8.1. Ba loại kiểm tra khi ghi

Với tham chiếu mảng:

- **Null check**: array reference là `null` → `NullPointerException`.
- **Bounds check**: index nhỏ hơn 0 hoặc lớn hơn/equal length → `ArrayIndexOutOfBoundsException`.
- **Store type check cho `aastore`**: với phần tử ghi khác `null`, runtime object của phần tử phải phù hợp với **runtime component type của chính object mảng**; nếu không → `ArrayStoreException`.

Cần tách **static type của biến mảng** khỏi **runtime type của object mảng**:

```java
Object[] slots = new String[2];
slots[0] = "ok";       // hợp lệ
slots[1] = new Object(); // ArrayStoreException tại runtime
```

Compiler chấp nhận gán `new Object()` vào phần tử biến có kiểu tĩnh `Object[]`. Nhưng object mảng thực tế là `String[]`, nên `aastore` phải từ chối object không phải `String`. Kiểm tra kiểu này **không phải `checkcast`** và lỗi là **`ArrayStoreException`**, không phải `ClassCastException`.

### 8.2. Giá trị `null` và mảng reference

`null` có thể ghi vào bất kỳ mảng reference phù hợp nào:

```java
String[] words = new String[1];
words[0] = null; // hợp lệ
```

Dù giá trị ghi là `null` và không có object để kiểm tra runtime class, **null/bounds check đối với chính mảng vẫn cần được đáp ứng**. Chẳng hạn `words[9] = null` vẫn vượt bounds.

Mảng primitive không có `null` cho từng phần tử: `int[]` chứa các giá trị `int`, không phải `Integer` reference. Nếu cần các phần tử nullable, có thể dùng `Integer[]`, nhưng nó là loại mảng khác và việc boxing/unboxing có thêm quy tắc.

## 9. Khác biệt giữa bytecode verifier và kiểm tra động

Một lỗi phổ biến là nói “JVM đã verify bytecode rồi nên truy cập mảng không thể sai”. Thực tế có hai tầng kiểm tra khác nhau:

| Tầng | Kiểm tra ví dụ | Thời điểm/mục đích |
| --- | --- | --- |
| Trình biên dịch `javac` | Kiểu biểu thức `a[i]`, tính khả thi của cast, loại biến, cú pháp | Trước khi tạo class file |
| Bytecode verification / linking | Kiểu toán hạng trên operand stack, stack frame, control flow, tính phù hợp của `iaload`/`arraylength` | Khi JVM xác minh/chuẩn bị dùng class file theo quy tắc JVM |
| Kiểm tra động tại instruction | Object cast được không, reference có null không, index có trong bounds không, phần tử có đúng runtime array component type không | **Trong lúc thực thi**, phụ thuộc dữ liệu runtime |

Bytecode verifier không thể biết trước giá trị thực của một index nhận từ người dùng hoặc một object được trả về từ thư viện. Bởi vậy một class file hoàn toàn hợp lệ vẫn có thể ném exception tại runtime.

JIT có thể tối ưu để bỏ **những lần kiểm tra không cần thiết về mặt quan sát được** khi chứng minh chúng dư thừa, chẳng hạn hoisting/eliminating một số bounds check. Điều này không thay đổi ngữ nghĩa phải được bảo toàn: trường hợp đáng ra ném exception vẫn phải có hành vi phù hợp với mô hình Java. Không dùng sự tồn tại của JIT để kết luận các instruction không có kiểm tra runtime.

## 10. Ví dụ Java 17+ chạy được: cast, `instanceof`, độ dài và truy cập mảng

Tạo một tệp **`CastArrayDemo.java`** tại thư mục làm việc:

```java
public class CastArrayDemo {
    static String castText(Object value) {
        return (String) value;
    }

    static String describe(Object value) {
        if (value instanceof String text) {
            return "String(" + text.length() + ")";
        }
        return "other";
    }

    static int arraySize(int[] data) {
        return data.length;
    }

    static int read(int[] data, int index) {
        return data[index];
    }

    static void write(int[] data, int index, int value) {
        data[index] = value;
    }

    public static void main(String[] args) {
        Object text = "JVM";
        Object number = Integer.valueOf(42);
        Object absent = null;

        System.out.println("instanceof text: " + (text instanceof String));
        System.out.println("instanceof number: " + (number instanceof String));
        System.out.println("instanceof null: " + (absent instanceof String));
        System.out.println("pattern: " + describe(text));
        System.out.println("cast: " + castText(text));
        System.out.println("cast null: " + (castText(absent) == null));

        try {
            castText(number);
        } catch (ClassCastException e) {
            System.out.println("bad cast: ClassCastException");
        }

        int[] scores = {5, 8};
        System.out.println("length: " + arraySize(scores));
        System.out.println("read: " + read(scores, 1));
        write(scores, 0, 11);
        System.out.println("after write: " + scores[0]);

        byte[] bytes = {(byte) 0xFF};
        char[] chars = {(char) 255};
        System.out.println("byte load: " + bytes[0]);
        System.out.println("char load: " + (int) chars[0]);

        try {
            read(scores, 2);
        } catch (ArrayIndexOutOfBoundsException e) {
            System.out.println("bad index: ArrayIndexOutOfBoundsException");
        }

        try {
            arraySize(null);
        } catch (NullPointerException e) {
            System.out.println("null array: NullPointerException");
        }

        Object[] slots = new String[1];
        slots[0] = "ok";
        System.out.println("stored: " + slots[0]);
        try {
            slots[0] = new Object();
        } catch (ArrayStoreException e) {
            System.out.println("bad store: ArrayStoreException");
        }

        Object rawArray = new String[2];
        System.out.println("instanceof String[]: "
                + (rawArray instanceof String[]));
        System.out.println("cast array length: "
                + ((String[]) rawArray).length);
    }
}
```

Với JDK 17 trở lên:

```bash
javac -encoding UTF-8 CastArrayDemo.java
java CastArrayDemo
```

**Standard output chính xác:**

```text
instanceof text: true
instanceof number: false
instanceof null: false
pattern: String(3)
cast: JVM
cast null: true
bad cast: ClassCastException
length: 2
read: 8
after write: 11
byte load: -1
char load: 255
bad index: ArrayIndexOutOfBoundsException
null array: NullPointerException
stored: ok
bad store: ArrayStoreException
instanceof String[]: true
cast array length: 2
```

Giải thích:

1. `text` trỏ tới `String` nên `instanceof` là `true`; `number` trỏ tới `Integer` nên không khớp; `absent == null` làm `instanceof` trả `false`.
2. `describe(text)` dùng **pattern matching cho `instanceof`** và trả độ dài chuỗi 3.
3. `castText(text)` thành công; `castText(absent)` vẫn trả `null`; chỉ `castText(number)` ném `ClassCastException`.
4. `scores.length` là 2; chỉ số 1 hợp lệ và đọc ra 8. Sau khi ghi `scores[0] = 11`, mảng giữ giá trị 11.
5. Giá trị byte `0xFF` tương ứng `-1` khi diễn giải `byte` có dấu; `char` 255 là không dấu.
6. Đọc `scores[2]` vượt phạm vi `0..1` nên bị bắt dưới dạng `ArrayIndexOutOfBoundsException`.
7. `arraySize(null)` thực hiện `arraylength` trên reference `null`, gây `NullPointerException`.
8. `slots` có kiểu biến `Object[]` nhưng object là `String[]`. Ghi `"ok"` hợp lệ, ghi `new Object()` bị từ chối bằng `ArrayStoreException`.
9. Reference `rawArray` trỏ tới `String[]`; cả kiểm tra `instanceof String[]` và `checkcast` sang `String[]` đều hợp lệ. Cast không tạo mảng thứ hai.

Ví dụ cố ý **bắt exception theo loại** và in chuỗi cố định, vì thông báo chi tiết trong `e.getMessage()` có thể thay đổi theo JVM và phiên bản. Nhờ vậy stdout trên là kết quả ổn định của chương trình.

## 11. Dùng `javap` để đọc bytecode thật

Từ thư mục có `CastArrayDemo.class`:

```bash
javap -c -p CastArrayDemo
javap -v -p CastArrayDemo
```

`-c` in bytecode, `-p` cho phép xem cả những method không public; `-v` hiển thị thêm constant pool, descriptor, exception table và thuộc tính ClassFile.

Tìm các method/đoạn như sau:

| Source/method | Bytecode điển hình | Ý nghĩa |
| --- | --- | --- |
| `castText(Object)` | `aload_0`, `checkcast java/lang/String`, `areturn` | Kiểm tra reference rồi trả reference |
| `describe(Object)` | `instanceof java/lang/String`, rẽ nhánh, có thể `checkcast` | Quyết định nhánh và gán pattern variable |
| `arraySize(int[])` | `aload_0`, `arraylength`, `ireturn` | Lấy độ dài mảng thành `int` |
| `read(int[], int)` | `aload_0`, `iload_1`, `iaload`, `ireturn` | Lấy phần tử `int` có kiểm tra null/bounds |
| `write(int[], int, int)` | `aload_0`, `iload_1`, `iload_2`, `iastore`, `return` | Ghi phần tử `int` |
| `slots[0] = new Object()` | `aastore` | Kiểm tra runtime component type khi lưu reference |

Các dòng trên mô tả **instruction quan trọng**; offset, constant pool index và cách compiler tạo pattern matching/string concatenation có thể khác giữa JDK. Không thay thế việc xem `javap` thực tế bằng một bản listing giả định.

### 11.1. Operand stack qua `checkcast`

```text
aload_0
  ..., objectref
checkcast java/lang/String
  ..., objectref         // giữ cùng giá trị nếu thành công
areturn
  ...                    // reference được trả về caller
```

### 11.2. Operand stack qua `instanceof`

```text
aload_0
  ..., objectref
instanceof java/lang/String
  ..., result(int: 0 hoặc 1)
ifeq target
  ...                    // điều kiện được lấy khỏi stack để rẽ nhánh
```

### 11.3. Operand stack qua `arraylength` và `iaload`

```text
aload_0                    // int[] reference
arraylength                // int length
ireturn

aload_0                    // int[] reference
iload_1                    // int index
iaload                     // int element
ireturn
```

Các mảnh này là **sơ đồ minh họa**, không phải một file `.jasm` cần chạy độc lập. Nếu mảng hoặc index không hợp lệ, instruction ném exception thay vì đặt kết quả bình thường lên stack.

### 11.4. `aastore` có thể lỗi mà không cần `checkcast`

Khi biên dịch `Object[] slots = new String[1]`, biến `slots` có kiểu tĩnh `Object[]`. Lệnh ghi một object qua biến đó có thể trực tiếp dùng **`aastore`**, không cần thêm `checkcast String` vào source/bytecode. **Bản thân `aastore`** chịu trách nhiệm đảm bảo đối tượng đang lưu tương thích với kiểu phần tử của mảng thực tế. Đây là điểm giúp phân biệt `ArrayStoreException` và `ClassCastException`.

## 12. Ma trận lỗi và cách suy luận đúng thứ tự

| Tình huống | Lệnh/hoạt động | Kết quả |
| --- | --- | --- |
| `(String) Integer.valueOf(42)` sau khi kiểu tĩnh cho phép cast | `checkcast` | `ClassCastException` |
| `null instanceof String` | `instanceof` | `false` / bytecode `0` |
| `(String) null` | `checkcast` | Thành công, giữ `null` |
| `((String) null).length()` | Cast rồi gọi method | Cast hợp lệ, lần dereference gây `NullPointerException` |
| `((int[]) null).length` | `arraylength` | `NullPointerException` |
| `new int[2]` rồi đọc index `-1` hoặc `2` | `iaload` | `ArrayIndexOutOfBoundsException` |
| `new int[2]` rồi ghi index `2` | `iastore` | `ArrayIndexOutOfBoundsException` |
| `Object[] a = new String[1]; a[0] = new Object();` | `aastore` | `ArrayStoreException` |
| `Object[] a = new String[1]; a[0] = null;` | `aastore` | Hợp lệ |
| `new long[3]` và `.length` | `arraylength` | `3` dưới dạng `int` |

**Không đánh đồng thứ tự đánh giá của Java source với thứ tự kiểm tra trong một instruction.** Trong một biểu thức phức tạp, Java có quy tắc riêng về việc đánh giá toán hạng và tác dụng phụ. Khi đã tới `*aload`/`*astore`, instruction làm việc với các giá trị chuẩn bị sẵn trên operand stack và kiểm tra null/bounds/type theo đặc tả. Nếu cần xác định exception nào xuất hiện trong một biểu thức có nhiều subexpression cùng lỗi, hãy xem cả thứ tự đánh giá nguồn và bytecode của `javap`.

### Phân biệt lỗi với lỗi tạo mảng

`NegativeArraySizeException` phát sinh khi tạo mảng với kích thước âm trong các instruction như `newarray` hoặc `anewarray`, **không phải** do `arraylength`. `OutOfMemoryError` cũng có thể phát sinh khi cấp phát mảng nếu runtime không đủ tài nguyên. Chúng liên quan vòng đời object mảng nhưng không thay thế các kiểm tra truy cập mảng trong bài này.

## 13. Những nhầm lẫn phổ biến

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`checkcast` chuyển `Integer` thành `String`.” | Nó kiểm tra khả năng dùng **cùng reference** dưới kiểu đích; không chuyển nội dung object |
| “Cast `null` sang `String` ném NPE.” | Cast `null` thành công; NPE chỉ xuất hiện khi thực hiện thao tác dereference không hợp lệ |
| “`instanceof` trả reference mới nếu đúng kiểu.” | Nó lấy reference khỏi stack và đẩy `int` 1/0 |
| “Source có `instanceof` thì bytecode luôn chỉ có đúng một opcode.” | Compiler có thể thêm rẽ nhánh, `checkcast` và lưu pattern variable tùy logic |
| “`array.length` là `getfield` như field thông thường.” | Mảng dùng instruction riêng `arraylength` |
| “`arraylength` kiểm tra index của mảng.” | Nó không có toán hạng index; `*aload`/`*astore` kiểm tra bounds |
| “Một mảng `Object[]` có thể chứa bất kỳ object nào.” | Nếu object mảng thực tế là `String[]`, `aastore` chỉ cho giá trị tương thích với `String` hoặc `null` |
| “`ArrayStoreException` là `ClassCastException`.” | Đây là hai exception khác nhau, do các phép kiểm tra runtime khác nhau |
| “Verifier đã kiểm tra bytecode nên index runtime không thể sai.” | Verifier không biết trước index/object thực tế sẽ nhận lúc chạy |
| “`int[][]` là một khối luôn hình chữ nhật.” | Mảng hai chiều là mảng của mảng; các hàng có thể khác độ dài hoặc `null` |
| “`baload` chỉ dùng cho `byte[]`.” | Nó dùng với cả `byte[]` và `boolean[]` theo JVM Specification |
| “JIT bỏ bounds check thì chương trình không cần tuân theo Java semantics.” | Tối ưu phải bảo toàn hành vi được quan sát theo ngữ nghĩa Java |

## 14. Bài tập tự kiểm tra

**1.** `Object x = null; String s = (String) x;` có ném `ClassCastException` không?  
**Đáp án:** Không. `checkcast` chấp nhận `null`; `s == null`.

**2.** `Object x = Integer.valueOf(10); boolean ok = x instanceof String;` có ném `ClassCastException` không?  
**Đáp án:** Không. `ok == false`. Nếu cố `(String) x`, lúc đó mới phát sinh cast không hợp lệ.

**3.** Với `int[] a = new int[4]`, chỉ số hợp lệ là gì?  
**Đáp án:** 0, 1, 2, 3. `-1` và `4` đều gây `ArrayIndexOutOfBoundsException` khi truy cập.

**4.** Vì sao `int[] a = null; int n = a.length;` gây lỗi?  
**Đáp án:** `arraylength` cần reference tới một đối tượng mảng, nhưng toán hạng là `null`, nên `NullPointerException`.

**5.** `Object[] a = new String[1]; a[0] = Integer.valueOf(1);` lỗi gì?  
**Đáp án:** `ArrayStoreException`: object mảng thực tế là `String[]`, không chứa được một `Integer` như phần tử.

**6.** `instanceof` và `checkcast` khác nhau về operand stack?  
**Đáp án:** `instanceof` lấy reference rồi đẩy `int` 0/1; `checkcast` nếu thành công giữ reference đó trên stack, nếu thất bại ném exception.

**7.** `long[] a = new long[3]; a.length` trả `long` vì phần tử có kiểu `long`?  
**Đáp án:** Không. `arraylength` luôn đẩy **`int`** biểu thị số phần tử; kết quả là 3.

**8.** Vì sao `aastore` cần kiểm tra kiểu động dù `javac` đã kiểm tra phép gán?  
**Đáp án:** Mảng reference **covariant**, vì thế biến kiểu `Object[]` có thể trỏ tới object `String[]`. Compiler chỉ thấy kiểu tĩnh của biến; runtime biết kiểu phần tử thực tế và ngăn phép ghi phá vỡ tính an toàn kiểu.

**9.** `byte[]` và `boolean[]` có hai opcode load hoàn toàn khác nhau?  
**Đáp án:** Không. JVM dùng `baload` cho cả hai trường hợp, với quy tắc biểu diễn/đọc phần tử thích hợp.

**10.** Nếu `ArrayIndexOutOfBoundsException` xuất hiện, có nên sửa bằng cách tắt bytecode verifier không?  
**Đáp án:** Không. Lỗi là do **index runtime** nằm ngoài phạm vi mảng. Cần kiểm tra điều kiện `0 <= index && index < array.length` và logic tạo/duyệt mảng; verifier không phải nguyên nhân.

**Tài liệu đối chiếu:** *Java Virtual Machine Specification*, chương 6.5 (các mục `checkcast`, `instanceof`, `arraylength`, `iaload`, `aaload`, `aastore` và các instruction mảng liên quan): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html. Với các biểu thức nguồn Java và thứ tự đánh giá toán hạng, xem thêm *Java Language Specification* Java 17.

**Kết luận:** `checkcast` **kiểm tra và giữ reference**, `instanceof` **kiểm tra rồi đẩy `int` 0/1**, `arraylength` **đẩy độ dài kiểu `int` của mảng**, còn `*aload`/`*astore` **đọc/ghi phần tử với kiểm tra null và bounds**; đặc biệt `aastore` còn kiểm tra **runtime component type**. Khi gặp exception, hãy phân biệt **kiểm tra kiểu đối tượng**, **dereference**, **chỉ số**, **tương thích phần tử mảng** và **bytecode verification** trước khi sửa chương trình.