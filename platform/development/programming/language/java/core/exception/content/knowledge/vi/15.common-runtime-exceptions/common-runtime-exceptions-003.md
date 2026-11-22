# `IndexOutOfBoundsException` và `ArrayIndexOutOfBoundsException` trong Java

> **Chủ đề:** Java Core → Exception → Ngoại lệ runtime. `IndexOutOfBoundsException` báo rằng một **chỉ số hoặc phạm vi** nằm ngoài giới hạn được một API cho phép. `ArrayIndexOutOfBoundsException` là **lớp con chuyên biệt** thường gặp khi truy cập trực tiếp một mảng Java bằng chỉ số sai. Cả hai thuộc nhánh `RuntimeException` (unchecked), vì vậy compiler không bắt buộc phải khai báo `throws` hoặc `catch` chúng. Để viết code đúng, cần hiểu giới hạn của mảng, collection, chuỗi, đoạn con và cách kiểm tra điều kiện **trước khi truy cập**, thay vì coi `try/catch` là phương pháp sửa lỗi chỉ số thông thường.

## 1. Hai lớp exception khác nhau thế nào?

Cây kế thừa rút gọn:

```text
java.lang.Throwable
└── java.lang.Exception
    └── java.lang.RuntimeException
        └── java.lang.IndexOutOfBoundsException
            ├── java.lang.ArrayIndexOutOfBoundsException
            └── java.lang.StringIndexOutOfBoundsException
```

- `IndexOutOfBoundsException`: lớp tổng quát báo lỗi **index/range**, chẳng hạn `List.get(index)`, `List.subList(from,to)` hoặc các helper kiểm tra phạm vi.
- `ArrayIndexOutOfBoundsException`: subtype của `IndexOutOfBoundsException`; phát sinh khi một phép truy cập phần tử **mảng** có chỉ số âm hoặc không nhỏ hơn `array.length`.
- `StringIndexOutOfBoundsException`: subtype khác, thường gặp khi truy cập ký tự chuỗi ở vị trí không hợp lệ, chẳng hạn `String.charAt(index)`.
- Vì `ArrayIndexOutOfBoundsException extends IndexOutOfBoundsException`, một `catch (IndexOutOfBoundsException e)` có thể nhận cả ngoại lệ từ mảng.
- Chiều ngược lại **không đúng**: `catch (ArrayIndexOutOfBoundsException)` không bắt mọi `IndexOutOfBoundsException`, ví dụ ngoại lệ chỉ số do một `List` hoặc `String` phát ra.

### 1.1. Bảng so sánh nhanh

| Tiêu chí | `IndexOutOfBoundsException` | `ArrayIndexOutOfBoundsException` |
| --- | --- | --- |
| Vai trò | Tổng quát cho chỉ số/phạm vi ngoài giới hạn | Chuyên biệt cho truy cập mảng |
| Package | `java.lang` | `java.lang` |
| Lớp cha trực tiếp | `RuntimeException` | `IndexOutOfBoundsException` |
| Checked hay unchecked? | Unchecked | Unchecked |
| Ví dụ nguồn thường gặp | `List.get`, `List.subList`, `Objects.checkIndex` | `arr[i]`, phép truy cập từng chiều của mảng |
| Bắt bằng `catch(IndexOutOfBoundsException)`? | Có | Có |
| Bắt bằng `catch(ArrayIndexOutOfBoundsException)`? | Không phải mọi trường hợp | Có |
| Có phải thông điệp luôn giống nhau? | Không | Không |
| Cách phòng tránh | Kiểm tra contract index/range cụ thể | Bảo đảm `0 <= i && i < arr.length` |

**Quy tắc chọn catch:** Khi muốn xử lý thống nhất lỗi chỉ số bất kể cấu trúc dữ liệu, bắt lớp cha `IndexOutOfBoundsException`. Khi chỉ muốn xử lý lỗi truy cập mảng cụ thể, có thể bắt lớp con. Nhưng trong phần lớn code nghiệp vụ, **sửa logic kiểm tra chỉ số** tốt hơn bắt những ngoại lệ này và tiếp tục như không có gì xảy ra.

## 2. Cả hai đều là unchecked exception

Các subtype của `RuntimeException` là **unchecked**: Java không áp dụng quy tắc bắt hoặc khai báo checked `throws` như với `IOException`.

Ví dụ:

```java
static int elementAt(int[] array, int index) {
    return array[index];
}
```

Phương thức này hợp lệ mà không có `throws ArrayIndexOutOfBoundsException`. Nếu `index` nằm ngoài miền cho phép, lúc chạy có thể phát sinh `ArrayIndexOutOfBoundsException`.

Một lời gọi cũng có thể chủ động khai báo `throws` với unchecked exception để tài liệu hóa:

```java
static int elementAt(int[] array, int index)
        throws ArrayIndexOutOfBoundsException {
    return array[index];
}
```

Nhưng khai báo trên **không bắt buộc** và không thay đổi cách kiểm tra khi biên dịch.

### 2.1. Tại sao không bắt buộc caller xử lý?

Sai chỉ số thường là dấu hiệu chương trình vi phạm một **tiền điều kiện** của thao tác truy cập, ví dụ:

- vòng lặp dừng sai;
- quên kiểm tra dữ liệu đầu vào;
- nhầm chỉ số và độ dài;
- sử dụng length của cấu trúc này để truy cập cấu trúc khác;
- nhầm đầu mút bao gồm/không bao gồm;
- dữ liệu đã thay đổi kích thước sau khi kiểm tra.

Java không yêu cầu mọi call site phải bọc `try/catch` cho những lỗi runtime này. Thiết kế tốt thường xác định và bảo đảm invariant, rồi kiểm thử các ranh giới. Nếu user nhập chỉ số tùy ý, validation ở biên hệ thống vẫn cần thiết để trả lỗi nhập liệu thân thiện.

### 2.2. Compiler có tự chặn mọi index sai không?

Không. Ví dụ:

```java
int[] values = {10, 20};
System.out.println(values[2]); // Có thể biên dịch, lỗi lúc chạy.
```

Dù chỉ số là hằng `2`, Java nói chung kiểm tra phạm vi truy cập mảng **khi chương trình thực thi**. Công cụ phân tích tĩnh hoặc IDE có thể cảnh báo trước, nhưng không nên xem cảnh báo ấy là bảo đảm của compiler.

## 3. Miền chỉ số hợp lệ của mảng

Với mảng có độ dài `n = array.length`:

```text
Chỉ số hợp lệ:    0, 1, 2, ..., n-1
Biểu thức đúng:   0 <= index && index < n
Chỉ số sai:       index < 0 hoặc index >= n
```

Ví dụ `int[] a = {5, 9, 12};`:

| Biểu thức | Kết quả |
| --- | --- |
| `a[0]` | `5` |
| `a[1]` | `9` |
| `a[2]` | `12` |
| `a[-1]` | `ArrayIndexOutOfBoundsException` |
| `a[3]` | `ArrayIndexOutOfBoundsException` |
| `a[100]` | `ArrayIndexOutOfBoundsException` |
| `a[a.length - 1]` | Phần tử cuối, với điều kiện mảng không rỗng |
| `a[a.length]` | Sai: `length` là số phần tử, không phải vị trí cuối |

**Độ dài không phải chỉ số cuối.** Khi `n > 0`, chỉ số cuối là `n - 1`. Với mảng rỗng `n == 0`, **không có bất kỳ chỉ số truy cập phần tử hợp lệ nào**, kể cả `0`.

### 3.1. Java 17 — ví dụ lỗi mảng với các chỉ số khác nhau

Tạo tệp **`ArrayBoundsDemo.java`**:

```java
public class ArrayBoundsDemo {
    static void inspect(int[] values, int index) {
        try {
            System.out.println(
                    "index " + index + " = " + values[index]);
        } catch (ArrayIndexOutOfBoundsException e) {
            System.out.println("index " + index + " ngoài giới hạn");
        }
    }

    public static void main(String[] args) {
        int[] numbers = {10, 20, 30};
        System.out.println("length = " + numbers.length);

        inspect(numbers, 0);
        inspect(numbers, 2);
        inspect(numbers, -1);
        inspect(numbers, 3);

        int[] empty = {};
        inspect(empty, 0);
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 ArrayBoundsDemo.java
java ArrayBoundsDemo
```

Stdout chính xác:

```text
length = 3
index 0 = 10
index 2 = 30
index -1 ngoài giới hạn
index 3 ngoài giới hạn
index 0 ngoài giới hạn
```

Trong chương trình này, `catch` chỉ để minh họa đường exception mà không làm dừng các ca kiểm thử tiếp theo. Với ứng dụng thật, nếu index đã được kiểm tra hợp lệ trước khi truy cập, không cần `catch` bao quanh mọi phép `a[i]`. Đặc biệt tránh bỏ qua lỗi mảng rồi tiếp tục dùng dữ liệu được giả định đã đọc thành công.

### 3.2. Điều gì xảy ra khi gán vào chỉ số sai?

Không chỉ **đọc** mà cả **ghi** phần tử mảng đều cần chỉ số hợp lệ:

```java
int[] values = {3, 4};
values[2] = 99; // Ném ArrayIndexOutOfBoundsException.
```

Không có phần tử `values[2]` được tạo mới. Mảng Java có **độ dài cố định sau khi tạo**, phép gán ở index ngoài giới hạn không tự mở rộng mảng.

Nếu cần danh sách có thể tăng số lượng phần tử, dùng cấu trúc như `ArrayList` với thao tác thêm phù hợp; không cố “append” bằng `arr[arr.length] = value`.

## 4. Index và độ dài: ba điều kiện cần nhớ

Với chỉ số phần tử `i` trong cấu trúc độ dài `n`:

```java
boolean validElementIndex = i >= 0 && i < n;
```

Với **ranh giới vị trí chèn** vào danh sách có độ dài `n`, `i == n` có thể hợp lệ nếu API cho chèn ở cuối, chẳng hạn `List.add(index, element)`:

```java
boolean validInsertionPosition = i >= 0 && i <= n;
```

Với **cặp đầu mút của đoạn [from, to)**:

```java
boolean validRange = 0 <= from && from <= to && to <= n;
```

Ba contract này **không giống nhau**. Một nguyên nhân lỗi thường gặp là lấy điều kiện cho **vị trí chèn** (cho phép `i == n`) rồi dùng để **đọc phần tử** (không cho phép `i == n`).

### 4.1. Vì sao dấu nhỏ hơn và nhỏ hơn hoặc bằng quan trọng?

- `array[index]` hoặc `list.get(index)`: `index < length/size`.
- `list.add(index, value)`: thường cho `index <= size` để append.
- `list.subList(from, to)`: có thể cho `to == size` do `to` là **exclusive end**.
- `String.substring(begin, end)`: `end == length` hợp lệ, còn `charAt(length)` sai.

Đừng học thuộc một điều kiện duy nhất rồi áp dụng cho mọi phương thức có tham số `index`. Hãy đọc hợp đồng từng API.

## 5. Lỗi vòng lặp `off-by-one` với dấu `<=`

Trường hợp phổ biến:

```java
int[] numbers = {4, 7, 9};

for (int i = 0; i <= numbers.length; i++) {
    System.out.println(numbers[i]); // Lỗi khi i == 3.
}
```

Điều kiện `i <= numbers.length` cho phép i bằng độ dài, nhưng chỉ số cuối là `length - 1`. Sửa thành:

```java
for (int i = 0; i < numbers.length; i++) {
    System.out.println(numbers[i]);
}
```

### 5.1. Java 17 — chạy thử phiên bản sai và phiên bản đúng

Tạo **`OffByOneDemo.java`**:

```java
public class OffByOneDemo {
    public static void main(String[] args) {
        int[] scores = {8, 13};

        try {
            for (int i = 0; i <= scores.length; i++) {
                System.out.println("Sai: " + scores[i]);
            }
        } catch (ArrayIndexOutOfBoundsException e) {
            System.out.println("Bắt lỗi tại i == length");
        }

        for (int i = 0; i < scores.length; i++) {
            System.out.println("Đúng: " + scores[i]);
        }

        for (int score : scores) {
            System.out.println("For-each: " + score);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 OffByOneDemo.java
java OffByOneDemo
```

Stdout:

```text
Sai: 8
Sai: 13
Bắt lỗi tại i == length
Đúng: 8
Đúng: 13
For-each: 8
For-each: 13
```

Giải thích:

1. Lần duyệt thứ nhất sử dụng điều kiện sai, truy cập `scores[2]` khi mảng có độ dài `2`.
2. Handler chỉ giữ chương trình ví dụ tiếp tục để so sánh, **không sửa** lỗi vòng lặp.
3. Lần duyệt thứ hai dùng `i < scores.length` nên chỉ có i = 0, 1.
4. `for-each` không cần tự tính index cho việc truy cập trực tiếp từng phần tử. Nó là lựa chọn tốt nếu mục tiêu chỉ là duyệt giá trị, không cần vị trí.
5. `for-each` không phòng mọi lỗi: nếu bên trong vẫn có phép `otherArray[i]` dùng chỉ số không hợp lệ, exception vẫn có thể xảy ra.

### 5.2. Các biến thể off-by-one

- Vòng lặp bắt đầu `i = 1` rồi đọc `array[i]`, vô tình bỏ phần tử đầu.
- Vòng lặp lùi dùng `i >= 0` nhưng khởi tạo `i = array.length`, truy cập vượt giới hạn ngay lần đầu.
- Sau khi gọi `list.remove(index)`, `size()` giảm, nhưng code vẫn dùng index dựa trên kích thước cũ.
- Dùng `i <= upperBound` khi `upperBound` là **exclusive**.
- Nhầm một dải `[start, end)` với dải `[start, end]`.

Cách sửa tốt nhất là đặt tên có ngữ nghĩa rõ: `exclusiveEnd`/`inclusiveLastIndex`, và viết test ở đầu, cuối, ngay trước/sau ranh giới.

## 6. `List` và `IndexOutOfBoundsException`

Với `List<T>` kích thước `n = list.size()`, `list.get(i)` yêu cầu `0 <= i < n`. Theo hợp đồng List, chỉ số không hợp lệ dẫn đến `IndexOutOfBoundsException`.

Ví dụ:

```java
java.util.List<String> names =
        java.util.List.of("An", "Bình");

System.out.println(names.get(0)); // "An"
System.out.println(names.get(1)); // "Bình"
// names.get(2); // Ngoài giới hạn.
```

Đây là mảnh code trong method. `list.size()` là **số phần tử**, tương tự `array.length` là số phần tử mảng. Nhưng cú pháp của List là **`size()`**, còn mảng dùng **trường `length`**:

```java
int[] array = {1, 2};
int arraySize = array.length;

java.util.List<Integer> list = java.util.List.of(1, 2);
int listSize = list.size();
```

**Lưu ý quan trọng về loại exception runtime:** Hợp đồng `List.get` nói `IndexOutOfBoundsException`; các implementation khác nhau có thể dùng subclass cụ thể tùy cách triển khai. Không dùng tên subtype xuất hiện trong log làm cách xác định chắc chắn cấu trúc dữ liệu đã được truy cập. Khi xử lý code viết theo interface `List`, thường nên dựa trên hợp đồng lớp cha thay vì phụ thuộc thông điệp hoặc subtype nội bộ.

### 6.1. `get` khác `add(index, element)`

Với List có `size() == 2`:

```java
java.util.List<String> names =
        new java.util.ArrayList<>(
                java.util.List.of("A", "B"));

names.add(2, "C");  // Hợp lệ: chèn cuối.
System.out.println(names.get(2)); // Hợp lệ sau khi thêm.
```

Đoạn trong method sẽ in `C`. Trước khi `add(2,"C")`, `names.get(2)` sai; sau khi thêm, size thành 3 nên index 2 hợp lệ.

Với `List.of(...)`, thao tác thay đổi như `add` sẽ ném `UnsupportedOperationException`, **không phải** `IndexOutOfBoundsException` chỉ vì list là immutable. Vì vậy khi đang đọc stack trace cần phân biệt lỗi **phạm vi chỉ số** với lỗi **khả năng thay đổi collection**.

## 7. `StringIndexOutOfBoundsException`: họ hàng cùng lớp cha

`String.charAt(index)` yêu cầu `0 <= index < string.length()`. Một chỉ số không hợp lệ thường làm phát sinh `StringIndexOutOfBoundsException`, cũng là subtype của `IndexOutOfBoundsException`.

```java
String text = "Java";
// text.charAt(4); // Sai vì length == 4.
```

Một handler lớp cha nhận được nhiều tình huống:

```java
try {
    String text = "Java";
    System.out.println(text.charAt(text.length()));
} catch (IndexOutOfBoundsException e) {
    System.out.println("Vị trí ký tự không hợp lệ");
}
```

Đoạn minh họa này in `Vị trí ký tự không hợp lệ`.

### 7.1. Đừng nhầm `String.length()` với số code point Unicode

Chuỗi Java lưu giá trị theo các **đơn vị UTF-16**. Một ký tự Unicode ngoài Basic Multilingual Plane (như nhiều emoji) dùng **hai UTF-16 code units** (surrogate pair). Do đó:

- `String.length()` trả số **UTF-16 code units**, không hứa là số ký tự người dùng nhìn thấy.
- `charAt(i)` trả một `char` — một code unit — không nhất thiết là toàn bộ Unicode code point.
- `codePointCount(begin,end)` đếm Unicode code points trong khoảng đã chọn.
- `offsetByCodePoints(index, codePointOffset)` hỗ trợ chuyển vị trí theo code point.
- Index mà `charAt` nhận luôn là chỉ số UTF-16, không phải thứ tự “ký tự hiển thị”.

### 7.2. Java 17 — Unicode không làm mất quy tắc bounds

Tạo **`StringBoundsUnicodeDemo.java`**:

```java
public class StringBoundsUnicodeDemo {
    public static void main(String[] args) {
        String text = "A😀B";

        System.out.println("UTF-16 length: " + text.length());
        System.out.println("Code points: "
                + text.codePointCount(0, text.length()));
        System.out.println("Low surrogate at 2: "
                + Character.isLowSurrogate(text.charAt(2)));

        int offsetOfB = text.offsetByCodePoints(0, 2);
        System.out.println("Offset of B: " + offsetOfB);

        try {
            text.charAt(text.length());
        } catch (StringIndexOutOfBoundsException e) {
            System.out.println("Exception: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 StringBoundsUnicodeDemo.java
java StringBoundsUnicodeDemo
```

Stdout:

```text
UTF-16 length: 4
Code points: 3
Low surrogate at 2: true
Offset of B: 3
Exception: StringIndexOutOfBoundsException
```

Vì `😀` dùng hai code units, text có `length() == 4` dù chứa ba code points (`A`, emoji, `B`). `charAt(2)` hợp lệ **về bounds** nhưng trả nửa sau của surrogate pair; muốn lấy nguyên code point, nên dùng `codePointAt` hoặc các API Unicode phù hợp.

Vẫn còn giới hạn: *code point* không đồng nghĩa một ký tự hiển thị (grapheme cluster), vì nhiều chuỗi có combining marks. Khi thao tác giao diện người dùng, cần hiểu mức trừu tượng bạn muốn đếm.

## 8. Dải con: `[from, to)` và `IndexOutOfBoundsException`

Nhiều API Java dùng **nửa khoảng mở**:

```text
[fromIndex, toIndex)
bao gồm fromIndex, không bao gồm toIndex
```

Đối với một cấu trúc có độ dài `n`, điều kiện hợp lệ thường là:

```text
0 <= fromIndex <= toIndex <= n
```

Hai ví dụ:

- `list.subList(1, 3)` lấy các phần tử ở index 1, 2.
- `text.substring(1, 3)` lấy các UTF-16 code units tương ứng index 1, 2.

Mỗi API có thêm điều kiện và các loại exception cụ thể. Nếu `fromIndex > toIndex`, một số API (như `List.subList`) có thể ném `IllegalArgumentException` chứ không nhất thiết chỉ `IndexOutOfBoundsException`; đọc hợp đồng phương thức chứ đừng suy từ tên “slice”.

### 8.1. Ví dụ Java 17 với phạm vi có đầu mút exclusive

Tạo **`RangeBoundsDemo.java`**:

```java
import java.util.List;

public class RangeBoundsDemo {
    public static void main(String[] args) {
        List<String> names = List.of("A", "B", "C");

        System.out.println("subList(1, 3): "
                + names.subList(1, 3));
        System.out.println("subList(3, 3): "
                + names.subList(3, 3));

        try {
            names.subList(2, 4);
        } catch (IndexOutOfBoundsException e) {
            System.out.println("toIndex 4 vượt size 3");
        }

        String text = "Java";
        System.out.println("substring(1, 4): "
                + text.substring(1, 4));
        System.out.println("substring(4, 4): '"
                + text.substring(4, 4) + "'");
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 RangeBoundsDemo.java
java RangeBoundsDemo
```

Stdout:

```text
subList(1, 3): [B, C]
subList(3, 3): []
toIndex 4 vượt size 3
substring(1, 4): ava
substring(4, 4): ''
```

**Những điểm rút ra:**

1. `toIndex == size` hợp lệ ở `subList` vì đầu mút trên được **loại trừ**.
2. `fromIndex == toIndex == size` biểu diễn một đoạn rỗng hợp lệ.
3. `toIndex > size` bị từ chối; ở ví dụ này handler `IndexOutOfBoundsException` nhận.
4. Với `String.substring`, `endIndex == length` hợp lệ; điều này **khác với `charAt(length)`**.
5. Trong code thật, `subList` thường là **view** của danh sách gốc, nên thay đổi cấu trúc list gốc khi vẫn dùng view có thể dẫn đến vấn đề độc lập với bounds. `List.of` trong ví dụ không cho sửa nên đơn giản hơn.

## 9. Công cụ kiểm tra chỉ số chuẩn: `Objects.checkIndex`

Từ Java 9, `java.util.Objects` cung cấp các phương thức kiểm tra index và range:

```java
Objects.checkIndex(index, length);
Objects.checkFromToIndex(fromIndex, toIndex, length);
Objects.checkFromIndexSize(fromIndex, size, length);
```

Các helper này có thể ném `IndexOutOfBoundsException` nếu tham số không hợp lệ, và trả lại index hoặc fromIndex khi hợp lệ. Chúng thường hữu ích khi **xây dựng API thao tác trên vùng dữ liệu**, cần validation nhất quán trước khi truy cập.

| Helper | Điều kiện hợp lệ (về mặt ý nghĩa) | Trường hợp hay dùng |
| --- | --- | --- |
| `checkIndex(i, n)` | `0 <= i < n` | Truy cập một phần tử |
| `checkFromToIndex(a,b,n)` | `0 <= a <= b <= n` | Đoạn `[a,b)` |
| `checkFromIndexSize(a,size,n)` | `0 <= a`, `0 <= size` và `a + size <= n` theo phép kiểm tra an toàn tràn số | Đoạn bắt đầu ở `a` có `size` phần tử |

Điều kiện toán học `a + size <= n` phải được thực thi theo cách không sai vì tràn số nguyên; dùng helper chuẩn hoặc so sánh an toàn, đừng cộng hai `int` tùy tiện rồi tin kết quả đã kiểm tra chính xác.

**Phân biệt phiên bản:** `Objects.checkIndex` và hai hàm kiểm tra phạm vi nói trên **không có từ Java 8**. Dự án dùng Java 17 có thể sử dụng trực tiếp.

### 9.1. Java 17 — ví dụ `Objects` với đầu ra cố định

Tạo **`ObjectsIndexCheckDemo.java`**:

```java
import java.util.Objects;

public class ObjectsIndexCheckDemo {
    static void test(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": OK");
        } catch (IndexOutOfBoundsException e) {
            System.out.println(label + ": OUT");
        }
    }

    public static void main(String[] args) {
        test("index 2", () -> Objects.checkIndex(2, 3));
        test("index 3", () -> Objects.checkIndex(3, 3));
        test("index -1", () -> Objects.checkIndex(-1, 3));

        test("range 0..3",
                () -> Objects.checkFromToIndex(0, 3, 3));
        test("empty range",
                () -> Objects.checkFromToIndex(3, 3, 3));
        test("range 0..4",
                () -> Objects.checkFromToIndex(0, 4, 3));

        test("size fits",
                () -> Objects.checkFromIndexSize(1, 2, 3));
        test("size exceeds",
                () -> Objects.checkFromIndexSize(2, 2, 3));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 ObjectsIndexCheckDemo.java
java ObjectsIndexCheckDemo
```

Stdout:

```text
index 2: OK
index 3: OUT
index -1: OUT
range 0..3: OK
empty range: OK
range 0..4: OUT
size fits: OK
size exceeds: OUT
```

Đoạn dùng `Runnable` để thử các phép kiểm tra và chỉ in kết quả, không dựa vào text của exception. Vì ba helper `Objects` ném unchecked exception nên callback `Runnable.run()` (không khai báo checked) phù hợp.

### 9.2. Kiểm tra chỉ số ở đâu?

- Tầng nhận input: validate chỉ số người dùng nhập, trả thông báo dễ hiểu.
- Method thư viện: kiểm tra tiền điều kiện nếu index/range là phần hợp đồng công khai; có thể dùng `Objects.checkIndex` hoặc kiểm tra riêng để đưa thông điệp phù hợp.
- Vòng lặp nội bộ: bảo đảm bất biến bằng điều kiện lặp/thiết kế thuật toán thay vì bao quanh từng lần truy cập bằng `try/catch`.
- Đầu vào đã được validation trước: vẫn phải xét trường hợp cấu trúc dữ liệu bị thay đổi kích thước giữa **check** và **use** nếu shared mutable state/concurrency có liên quan.

## 10. Mảng hai chiều: mỗi chiều có độ dài riêng

Trong Java, “mảng 2D” là **mảng chứa các mảng con**. Các hàng có thể dài khác nhau (*jagged array*) hoặc thậm chí có giá trị `null`:

```java
int[][] matrix = {
    {1, 2, 3},
    {4}
};
```

Với cấu trúc trên:

- `matrix.length == 2`: có hai hàng.
- `matrix[0].length == 3`: hàng đầu có ba phần tử.
- `matrix[1].length == 1`: hàng thứ hai có một phần tử.
- `matrix[1][1]`: sai chỉ số **cột của hàng thứ hai**, gây `ArrayIndexOutOfBoundsException`.
- `matrix[2][0]`: sai chỉ số **hàng**, cũng gây `ArrayIndexOutOfBoundsException`.
- Nếu `matrix[1] == null`, `matrix[1][0]` gây `NullPointerException`, **không phải** lỗi vượt giới hạn tại hàng.

### 10.1. Java 17 — truy cập mảng răng cưa

Tạo **`JaggedArrayBoundsDemo.java`**:

```java
public class JaggedArrayBoundsDemo {
    static void inspect(int[][] matrix, int row, int column) {
        try {
            System.out.println("(" + row + "," + column + ") = "
                    + matrix[row][column]);
        } catch (ArrayIndexOutOfBoundsException e) {
            System.out.println("(" + row + "," + column
                    + ") ngoài giới hạn");
        }
    }

    public static void main(String[] args) {
        int[][] matrix = {
                {1, 2, 3},
                {4}
        };

        System.out.println("Số hàng: " + matrix.length);
        System.out.println("Độ dài hàng 1: "
                + matrix[1].length);

        inspect(matrix, 0, 2);
        inspect(matrix, 1, 0);
        inspect(matrix, 1, 1);
        inspect(matrix, 2, 0);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 JaggedArrayBoundsDemo.java
java JaggedArrayBoundsDemo
```

Stdout:

```text
Số hàng: 2
Độ dài hàng 1: 1
(0,2) = 3
(1,0) = 4
(1,1) ngoài giới hạn
(2,0) ngoài giới hạn
```

**Bài học:** không thể dùng `matrix[0].length` cho mọi hàng nếu dữ liệu là mảng răng cưa. Duyệt an toàn:

```java
for (int row = 0; row < matrix.length; row++) {
    if (matrix[row] == null) {
        continue; // Chính sách tùy hợp đồng dữ liệu.
    }
    for (int col = 0; col < matrix[row].length; col++) {
        System.out.println(matrix[row][col]);
    }
}
```

Đây là đoạn trong method, không phải file độc lập. Kiểm tra `null` là điều kiện riêng với kiểm tra index, tránh đồng nhất `NullPointerException` với `ArrayIndexOutOfBoundsException`.

## 11. Dữ liệu bên ngoài: validation trước khi truy cập

Một chỉ số lấy từ form, CLI hoặc request HTTP có thể là:

- chuỗi không phải số (`"abc"`);
- số âm (`"-1"`);
- số nguyên vượt kích thước mảng;
- số nguyên quá lớn, không parse được thành `int`;
- chỉ số từ client bắt đầu ở 1 trong khi Java dùng index bắt đầu ở 0.

Cần phân biệt **lỗi phân tích cú pháp** với **lỗi ngoài phạm vi**. `Integer.parseInt("abc")` ném `NumberFormatException`; nó không trực tiếp ném `IndexOutOfBoundsException` của mảng.

### 11.1. Java 17 — kiểm tra đầu vào trước khi đọc

Tạo **`ValidatedIndexInputDemo.java`**:

```java
import java.util.List;

public class ValidatedIndexInputDemo {
    static void lookup(int[] values, String raw) {
        try {
            int index = Integer.parseInt(raw);

            if (index < 0 || index >= values.length) {
                System.out.println(raw + ": ngoài phạm vi");
                return;
            }

            System.out.println(raw + ": " + values[index]);
        } catch (NumberFormatException e) {
            System.out.println(raw + ": không phải số nguyên");
        }
    }

    public static void main(String[] args) {
        int[] values = {100, 200};

        for (String raw : List.of("0", "1", "2", "-1", "abc")) {
            lookup(values, raw);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 ValidatedIndexInputDemo.java
java ValidatedIndexInputDemo
```

Stdout:

```text
0: 100
1: 200
2: ngoài phạm vi
-1: ngoài phạm vi
abc: không phải số nguyên
```

Ở đây exception của mảng **không cần xảy ra** cho dữ liệu ngoài phạm vi, vì code kiểm tra trước. Tầng ứng dụng có thể chuyển các trường hợp input sai thành validation result hoặc HTTP 400/422 tùy hợp đồng, không cần chờ JVM ném `ArrayIndexOutOfBoundsException` rồi xem đó là cách báo lỗi người dùng.

### 11.2. Nếu người dùng đếm vị trí từ 1?

Ví dụ giao diện ghi “chọn mục 1, 2, 3” nhưng Java lưu ở index 0, 1, 2. Cần định nghĩa chuyển đổi có kiểm soát:

```java
int oneBasedPosition = 2;
int zeroBasedIndex = oneBasedPosition - 1;
```

Tránh trừ 1 nếu input đã là zero-based. Ngoài ra không nên dùng `input - 1` trước khi xét nguy cơ tràn số với `Integer.MIN_VALUE`; bảo đảm input thuộc miền 1..n trước, sau đó mới chuyển thành 0..n-1.

## 12. Bắt ngoại lệ: chọn lớp cha hay lớp con?

Vì quan hệ kế thừa, hai cách đều có giá trị trong ngữ cảnh riêng.

### 12.1. Handler tổng quát cho nhiều cấu trúc dữ liệu

```java
try {
    useIndex();
} catch (IndexOutOfBoundsException e) {
    reportInvalidPosition(e);
}
```

Đây là mẫu minh họa; `useIndex()` và `reportInvalidPosition(...)` chưa được định nghĩa. Một handler lớp cha có thể bắt cả `ArrayIndexOutOfBoundsException` và `StringIndexOutOfBoundsException`.

### 12.2. Handler chuyên biệt cho mảng

```java
try {
    int value = numbers[index];
    System.out.println(value);
} catch (ArrayIndexOutOfBoundsException e) {
    System.out.println("Truy cập mảng sai vị trí");
}
```

Đoạn trong method, giả định `numbers` và `index` có kiểu phù hợp. Handler chỉ bắt subtype chuyên biệt.

### 12.3. Thứ tự hai handler khi dùng cả hai

```java
try {
    readSomething();
} catch (ArrayIndexOutOfBoundsException e) {
    System.out.println("Lỗi chỉ số mảng");
} catch (IndexOutOfBoundsException e) {
    System.out.println("Lỗi chỉ số khác");
}
```

Đây là mẫu minh họa, `readSomething()` chưa định nghĩa. Handler **lớp con** phải đứng trước **lớp cha**, vì `catch(IndexOutOfBoundsException)` đứng trước sẽ bắt cả ArrayIOOBE và làm nhánh chuyên biệt phía sau không tới được.

Đoạn sau **cố ý sai**:

```java
try {
    readSomething();
} catch (IndexOutOfBoundsException e) {
    // Bắt quá rộng trước.
} catch (ArrayIndexOutOfBoundsException e) {
    // Compiler báo unreachable catch.
}
```

Một multi-catch `catch (IndexOutOfBoundsException | ArrayIndexOutOfBoundsException e)` cũng **không hợp lệ** vì các lựa chọn có quan hệ cha–con; chỉ giữ lớp cha nếu thật sự cần xử lý chung.

## 13. Chương trình Java 17 — ba kiểu lỗi được bắt bởi một lớp cha

Tạo **`BoundsHierarchyDemo.java`**:

```java
import java.util.List;

public class BoundsHierarchyDemo {
    static void inspect(String label, Runnable operation) {
        try {
            operation.run();
        } catch (IndexOutOfBoundsException e) {
            System.out.println(label + ": "
                    + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        inspect("array", () -> {
            int[] numbers = {1, 2};
            System.out.println(numbers[2]);
        });

        inspect("list", () -> {
            List<String> names = List.of("A", "B");
            System.out.println(names.get(2));
        });

        inspect("string", () -> {
            String text = "AB";
            System.out.println(text.charAt(2));
        });
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 BoundsHierarchyDemo.java
java BoundsHierarchyDemo
```

**Đầu ra khi chạy với JDK 17 tiêu chuẩn:**

```text
array: ArrayIndexOutOfBoundsException
list: IndexOutOfBoundsException
string: StringIndexOutOfBoundsException
```

Phân tích:

1. `numbers[2]` sai khi length bằng 2: exception từ truy cập mảng.
2. `names.get(2)` sai khi list size bằng 2: implementation `List.of` của JDK 17 thông thường phát `IndexOutOfBoundsException`.
3. `text.charAt(2)` sai với chuỗi dài 2: `StringIndexOutOfBoundsException`.
4. Cả ba đều bị `catch(IndexOutOfBoundsException)` bắt vì quan hệ kế thừa.
5. **Không ràng buộc production code vào chính xác subtype/message của mọi List implementation**. Hợp đồng công khai của `List.get` là `IndexOutOfBoundsException`, và implementation có thể có đặc điểm nội bộ khác.

Bài học về API: chọn handler theo **hợp đồng và chính sách khôi phục**, không chỉ vì muốn in một tên exception cố định.

## 14. Nên phòng tránh trước hay bắt lỗi sau?

Trong code nội bộ, một lỗi vượt chỉ số thường biểu thị bug. Bắt rồi lặng lẽ tiếp tục có thể che bug và để lại trạng thái ứng dụng không đúng.

Anti-pattern:

```java
for (int i = 0; i <= values.length; i++) {
    try {
        total += values[i];
    } catch (ArrayIndexOutOfBoundsException ignored) {
        // Lặng lẽ bỏ lượt cuối.
    }
}
```

Mảnh code minh họa, giả sử `values` và `total` đã định nghĩa. Kết quả hiện tại có thể “trông đúng” tình cờ vì ngoại lệ chỉ xảy ra ở lần cuối; nhưng vòng lặp sai và không an toàn nếu thuật toán đổi. Sửa điều kiện thành `i < values.length`.

### 14.1. Khi nào catch là hợp lý?

- Trong ví dụ học tập và test cần minh họa ngoại lệ.
- Ở ranh giới một yêu cầu độc lập, muốn chuyển lỗi không dự kiến thành failure rõ ràng, ghi log và không cho nó phá điều phối tác vụ khác.
- Trong API có hợp đồng đặc biệt dựa trên exception để báo index sai, caller thật sự có kế hoạch thay index/fallback.
- Khi xử lý nguồn dữ liệu không đáng tin và đã xác định exception tương ứng là một phần hợp đồng điều khiển.

Ngay cả khi catch hợp lý, phải tự hỏi: **tầng này có sửa được lỗi không?** Nếu không, nên báo failure hoặc ném tiếp. Không coi catch là bước “đã chữa khỏi” nguyên nhân.

### 14.2. Vì sao không parse message?

Chuỗi lỗi có thể thay đổi theo JDK, loại mảng, implementer, ngữ cảnh và bản phát hành. Ví dụ không nên:

```java
try {
    useIndex();
} catch (IndexOutOfBoundsException e) {
    if (e.getMessage().contains("Index 3")) {
        // Logic dựa trên text lỗi: dễ vỡ.
    }
}
```

Đây là minh họa cần có `useIndex()`, và message có thể là `null`. Nếu cần trả thông tin chỉ số và giới hạn cho UI, **hãy giữ chúng trong dữ liệu đầu vào/validation**, thay vì cố phân tích `getMessage()`. Nếu cần logging, log exception object và ngữ cảnh index/size riêng, theo chính sách bảo mật.

## 15. `NullPointerException`, `ArrayStoreException` và lỗi khác không đồng nghĩa với bounds

Các lỗi sau có nguyên nhân khác:

| Ngoại lệ | Tình huống |
| --- | --- |
| `ArrayIndexOutOfBoundsException` | Chỉ số truy cập phần tử mảng ngoài `[0, length)` |
| `IndexOutOfBoundsException` | Chỉ số/phạm vi ngoài contract của List/helper |
| `StringIndexOutOfBoundsException` | Chỉ số chuỗi không hợp lệ |
| `NullPointerException` | Dùng một tham chiếu `null` như đối tượng/mảng cần truy cập |
| `ArrayStoreException` | Gán đối tượng không tương thích vào runtime component type của reference array |
| `UnsupportedOperationException` | Thao tác không được collection hỗ trợ, ví dụ thêm vào `List.of` |
| `NegativeArraySizeException` | Tạo mảng có kích thước âm |

Hai ví dụ dễ nhầm:

```java
int[] a = null;
// int x = a[0]; // NullPointerException, không phải lỗi bounds.

int[] b = new int[-1];
// NegativeArraySizeException khi tạo mảng.
```

Đây là các mảnh minh họa **cố ý gây lỗi lúc chạy**.

Với reference array:

```java
Object[] values = new String[1];
// values[0] = Integer.valueOf(123); // ArrayStoreException.
```

Chỉ số `0` **hợp lệ**, nhưng kiểu đối tượng `Integer` không phù hợp với runtime component type `String`. Đây là lỗi lưu kiểu, không phải lỗi vượt chỉ số.

### 15.1. Mảng nhiều chiều có thể lỗi null ở tầng trong

```java
int[][] rows = new int[2][];
rows[0] = new int[] {1};
// rows[1][0]; // NullPointerException vì rows[1] chưa có mảng con.
```

Ngay cả khi `rows.length == 2` và index hàng `1` hợp lệ, mảng con vẫn có thể là `null`. Phải kiểm tra từng tầng đúng loại rủi ro.

## 16. Đường biên dữ liệu và tính nhất quán khi size thay đổi

Giả sử một `List` mutable được chia sẻ giữa hai thread:

```java
if (index >= 0 && index < list.size()) {
    return list.get(index);
}
```

Đây là method minh họa giả định `list` đã được định nghĩa. Điều kiện **không** tự bảo đảm an toàn nếu thread khác có thể giảm size giữa lúc kiểm tra và lúc gọi `get`. Đây là trường hợp *time-of-check to time-of-use* (TOCTOU).

Các chiến lược tùy bối cảnh:

- Giới hạn quyền sở hữu của collection trong một thread.
- Đồng bộ hóa check và use dưới cùng một lock phù hợp (cả các thao tác sửa list phải tuân lock).
- Dùng snapshot bất biến (`List.copyOf`) khi thích hợp để có size và nội dung ổn định.
- Sử dụng cấu trúc concurrent và hiểu hợp đồng thao tác của nó, không giả định tất cả cấu trúc thread-safe có cùng semantics về index.
- Thiết kế API tránh chia sẻ index vào một container đang biến đổi nếu có thể.

**Đừng nói** “đã kiểm tra `index < list.size()` thì không bao giờ có bounds error”: câu này còn phụ thuộc không có mutation không đồng bộ, overflow hay sai lệch biến chứa collection.

### 16.1. `List.subList` và thay đổi danh sách gốc

`subList` thông thường là một **view** trên list gốc, không hẳn bản sao độc lập. Thay đổi cấu trúc list gốc không thông qua sublist có thể làm semantics của view không còn được xác định/không còn hợp lệ theo hợp đồng. Nếu cần snapshot, chọn `new ArrayList<>(list.subList(...))` hoặc `List.copyOf(...)` khi phù hợp, sau khi xác thực phạm vi và concurrency.

## 17. Cách debug khi gặp bounds exception

Khi production xuất hiện `ArrayIndexOutOfBoundsException` hoặc `IndexOutOfBoundsException`, dùng quy trình:

1. **Đọc stack trace**, xác định method và dòng code thực sự truy cập chỉ số.
2. **Xác định container**: mảng, list, chuỗi, buffer, view hay dữ liệu mảng 2D.
3. **Đọc contract index/range** của API được gọi, không đoán mọi API đều `[0,n)`.
4. **Ghi chỉ số và độ dài/size tại cùng ngữ cảnh** (không đưa dữ liệu nhạy cảm vào log).
5. **Kiểm tra các trường hợp biên**: rỗng, một phần tử, index 0, last index, index == n, index âm.
6. **Xem phép biến đổi index**: cộng/trừ, đổi one-based sang zero-based, offset, tính start/end.
7. **Với nhiều container**, xác nhận size đang dùng thuộc đúng container được truy cập.
8. **Xem concurrency**: có ai thay đổi size sau validation không?
9. **Sửa invariant hoặc input validation**, không chỉ thêm catch để dập log.
10. **Thêm regression test** với input tối thiểu tái hiện lỗi.

### 17.1. Đọc exception type trước khi đọc message

Ví dụ:

```text
java.lang.ArrayIndexOutOfBoundsException: Index 3 out of bounds for length 3
    at example.OrderService.calculate(OrderService.java:42)
```

Đây là **minh họa thông điệp**, không phải kết quả cố định trên mọi JDK. Đọc nó như: thao tác mảng dùng index bằng length; tra dòng `calculate`, kiểm tra vòng lặp hoặc công thức index. Đừng xây logic production parse chuỗi `"Index 3..."`, vì thông điệp có thể khác.

### 17.2. Debug nên ghi gì?

Nếu không chứa dữ liệu nhạy cảm, thông tin hữu ích là `index`, `size`, tên thao tác và request correlation ID. Với chuỗi Unicode, nên ghi rõ đang xét **UTF-16 offset** hay **code point offset**. Với jagged array, ghi row index, row count, col index và row length tương ứng.

Không log toàn bộ input/request chỉ vì một index sai; log tối thiểu vẫn thường đủ tìm bug.

## 18. Hiệu năng: bounds check là một phần an toàn của Java

Mọi truy cập mảng theo chỉ số phải tuân theo semantics kiểm tra giới hạn. JVM/JIT có thể **tối ưu bỏ phép kiểm tra lặp** trong một số vòng lặp nếu chứng minh được index luôn hợp lệ, nhưng không được làm thay đổi hành vi Java được quan sát khi chỉ số thực sự sai.

Điều này dẫn đến những lưu ý:

- Không dùng `try/catch` như một phép kiểm tra “nhanh” thay cho điều kiện loop đúng.
- Tránh cố tính `array[index]` với hy vọng ngoài giới hạn thì được giá trị mặc định; Java không làm vậy.
- Một lỗi bounds xảy ra thường xuyên trong hot path là dấu hiệu cần sửa thuật toán/validation, không chỉ tối ưu logging.
- Compiler/JIT không miễn kiểm tra chỉ số sai chỉ vì một vòng lặp được đánh dấu “fast”.
- `for-each`, `Arrays` và collection API có thể giúp hạn chế lỗi chỉ số thủ công; chọn cấu trúc hợp nhiệm vụ.

Không cần tự đoán JIT đã loại bỏ bounds check tại runtime cụ thể. Nếu hiệu năng quan trọng, benchmark trên workload thật và giữ kiểm thử correctness trước.

## 19. Unit test đường biên

Các ca test có giá trị:

| Kích thước cấu trúc | Input | Kỳ vọng |
| --- | --- | --- |
| Mảng rỗng `n=0` | `0` | `ArrayIndexOutOfBoundsException` hoặc validation failure trước truy cập |
| Mảng một phần tử `n=1` | `0` | Hợp lệ |
| Mảng một phần tử `n=1` | `1` | Ngoài giới hạn |
| Mảng ba phần tử `n=3` | `2` | Phần tử cuối hợp lệ |
| Mảng ba phần tử `n=3` | `3` | Ngoài giới hạn |
| Bất kỳ `n>=0` | `-1` | Ngoài giới hạn |
| Subrange `n=3` | `[3,3)` | Đoạn rỗng hợp lệ nếu API cho phép |
| Subrange `n=3` | `[2,4)` | Ngoài giới hạn |
| Mảng răng cưa | Hàng 1 có length 1, col 1 | Ngoài giới hạn của hàng |

### 19.1. Mẫu JUnit 5 minh họa

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;

class BoundsContractTest {
    @Test
    void arrayRejectsInvalidIndex() {
        int[] values = {4, 5};
        assertEquals(5, values[1]);
        assertThrows(ArrayIndexOutOfBoundsException.class,
                () -> { int ignored = values[2]; });
    }

    @Test
    void listRejectsInvalidIndexByContract() {
        List<Integer> values = List.of(4, 5);
        assertThrows(IndexOutOfBoundsException.class,
                () -> values.get(2));
    }

    @Test
    void halfOpenRangeAllowsEmptyTail() {
        List<String> names = List.of("A", "B");
        assertTrue(names.subList(2, 2).isEmpty());
    }
}
```

**Đây là file test dành cho một dự án có JUnit Jupiter**, không phải chương trình `javac` độc lập chỉ dùng thư viện chuẩn. Test kiểm tra hợp đồng của thao tác thay vì so sánh message exception. `assertThrows(IndexOutOfBoundsException.class, ...)` chấp nhận instance của subclass nếu implementation dùng subtype.

### 19.2. Test validation khác test exception phát sinh tự nhiên

Nếu public API kiểm tra `index` rồi chủ động trả một `Result` lỗi, nên test **kết quả validation**, không buộc phải ném `ArrayIndexOutOfBoundsException`. Exception runtime từ truy cập mảng thường phản ánh một đường bug; ứng dụng có thể chọn báo lỗi input bằng cách khác trước khi chạm vào mảng.

## 20. Các lỗi phổ biến và cách sửa

| Sai lầm | Kết quả | Cách sửa |
| --- | --- | --- |
| Dùng `i <= array.length` khi đọc `array[i]` | Truy cập index bằng length | Dùng `i < array.length` |
| Đọc `array[array.length]` để lấy cuối | Luôn vượt giới hạn | Dùng `array[array.length-1]` nếu không rỗng |
| Đọc `array[0]` khi length 0 | `ArrayIndexOutOfBoundsException` | Kiểm tra rỗng/thiết kế empty case |
| Dùng `list.get(list.size())` để append | Index đọc vượt giới hạn | `list.add(element)` hoặc `list.add(size, element)` nếu mutable |
| Dùng length của hàng 0 cho mọi hàng | Jagged array có row khác length | Dùng `matrix[row].length` |
| Dùng `String.charAt(length)` | String index sai | Xác định index hợp lệ, hoặc dùng substring end-exclusive |
| Nhầm code point offset với UTF-16 index | Truy cập giữa surrogate pair hoặc sai vị trí | Dùng `codePointAt`/`offsetByCodePoints` |
| Lấy khoảng `[from,to]` nhưng API hiểu `[from,to)` | Lệch một phần tử | Đọc contract endpoint exclusive |
| Coi `i==n` luôn sai | Sai với một số thao tác chèn/empty end range | Phân biệt index phần tử và vị trí chèn/range |
| Bắt `ArrayIndexOutOfBoundsException` để xử lý mọi List lỗi index | Có thể bỏ sót IndexOutOfBoundsException thuần | Dựa trên API contract, bắt cha khi thật cần |
| Đặt `catch(IndexOutOfBoundsException)` trước catch subclass | Handler subclass unreachable | Đặt catch cụ thể trước |
| Multi-catch cha + con | Không biên dịch | Giữ cha hoặc hai catch riêng hợp lệ |
| Catch rồi bỏ qua trong vòng lặp | Che bug điều kiện lặp | Sửa invariant |
| Parse `getMessage()` để lấy index | Message khác theo runtime/phiên bản | Giữ index và size riêng |
| Quên `null` array | `NullPointerException`, không phải bounds | Kiểm tra dữ liệu/null độc lập |
| Dùng `new int[-1]` rồi nghĩ lỗi access | `NegativeArraySizeException` khi tạo | Validate kích thước tạo |
| Sửa List đồng thời sau khi kiểm tra size | Check/use có thể lệch | Đồng bộ, snapshot hoặc ownership phù hợp |
| Đo index từ 1 rồi dùng trực tiếp với mảng | Lệch 1 | Validate vị trí one-based rồi trừ 1 |
| Dùng chỉ số đã tính có nguy cơ overflow | Index biến thành âm hoặc giá trị sai | Dùng phép toán/validation tránh tràn |
| Trả raw stack trace cho client | Lộ chi tiết nội bộ | Map sang phản hồi lỗi an toàn và log có kiểm soát |

## 21. Câu hỏi thường gặp

### 21.1. `ArrayIndexOutOfBoundsException` có phải là `IndexOutOfBoundsException` không?

Có, vì nó **extends** `IndexOutOfBoundsException`. Vì vậy `catch(IndexOutOfBoundsException)` có thể bắt `ArrayIndexOutOfBoundsException`, còn `catch(ArrayIndexOutOfBoundsException)` không đảm bảo bắt được lỗi do `List.get` hoặc `String.charAt`.

### 21.2. Hai exception có phải checked exception không?

Không. Chúng thuộc `RuntimeException`, nên code không bắt buộc khai báo `throws` hoặc bắt chúng. Tuy nhiên vẫn có thể bắt khi có chính sách xử lý đúng.

### 21.3. `array.length` có phải chỉ số cuối không?

Không. Với mảng không rỗng, chỉ số cuối là `array.length - 1`. Nếu mảng rỗng, không có chỉ số nào hợp lệ.

### 21.4. Có thể truy cập `array[-1]` để lấy phần tử cuối như Python không?

Không. Java **không** dùng indexing âm để truy cập từ cuối. `array[-1]` phát sinh `ArrayIndexOutOfBoundsException`. Muốn lấy phần tử cuối, kiểm tra mảng không rỗng rồi dùng `array[array.length-1]`.

### 21.5. Vì sao `list.add(list.size(), x)` có thể hợp lệ, nhưng `list.get(list.size())` không?

`add(index, element)` (với List mutable) thường nhận **vị trí chèn** thuộc `[0,size]`, kể cả cuối. `get(index)` nhận **vị trí phần tử** thuộc `[0,size)`. Đây là hai hợp đồng khác nhau.

### 21.6. Vì sao `substring(0, length)` hợp lệ nhưng `charAt(length)` sai?

Vì `substring(begin,end)` dùng **end-exclusive**; chỉ số end là ranh giới sau phần tử cuối. `charAt(index)` cần chính vị trí một code unit tồn tại, nên index phải nhỏ hơn length.

### 21.7. Có nên bọc mọi phép truy cập bằng `try/catch(IndexOutOfBoundsException)`?

Thường không. Đối với code nội bộ, sửa loop/validation và kiểm thử đường biên rõ hơn. Bắt exception chỉ phù hợp nếu tầng đó có chính sách xử lý hoặc chuyển báo lỗi thực sự.

### 21.8. Có thể trông cậy vào message “Index X out of bounds for length N” không?

Không như một **giao thức ổn định**. Một số JDK sinh message như vậy, nhưng text có thể khác giữa implementation và loại API. Dùng exception type và dữ liệu index/size gốc thay vì parse message.

### 21.9. `List.of` truy cập sai index có luôn ném ArrayIndexOutOfBoundsException không?

Không nên khẳng định điều đó. `List` công bố contract `IndexOutOfBoundsException`; implementation JDK có thể dùng cách kiểm tra và subtype cụ thể. Nếu cần xử lý chung các lỗi index của List, bắt lớp cha.

### 21.10. Bounds check có bảo đảm thread safety không?

Không. Bounds check xác nhận chỉ số với trạng thái được quan sát ở một thao tác; list mutable bị thread khác thay đổi vẫn có thể gây lỗi hoặc vấn đề nhất quán. Cần chính sách đồng bộ/snapshot độc lập.

## 22. Bài tập tự luyện

### Bài 1 — Dự đoán các chỉ số

`int[] a = {2, 4, 6};`. Cho biết kết quả của `a[0]`, `a[2]`, `a[3]` và `a[-1]`. **Đáp án:** `2`, `6`, hai lần lỗi `ArrayIndexOutOfBoundsException`.

### Bài 2 — Sửa vòng lặp

Cho `for (int i = 0; i <= a.length; i++)`, hãy viết lại điều kiện duyệt tất cả phần tử và xử lý trường hợp mảng rỗng. **Đáp án:** `i < a.length`; vòng lặp tự bỏ qua nếu mảng rỗng.

### Bài 3 — Catch theo phân cấp

Viết một đoạn có `catch(ArrayIndexOutOfBoundsException)` trước `catch(IndexOutOfBoundsException)`. Giải thích vì sao đảo thứ tự khiến handler thứ hai không thể tới được.

### Bài 4 — Jagged array

Với `int[][] a = {{1,2,3}, {4}}`, giải thích `a[1][0]`, `a[1][1]` và `a[2][0]`. Tại sao dùng `a[0].length` cho tất cả hàng là sai?

### Bài 5 — String và UTF-16

Chạy `StringBoundsUnicodeDemo`. Giải thích vì sao `length()` bằng 4 nhưng `codePointCount` bằng 3. `charAt(2)` sai về index hay chỉ là lấy một phần của surrogate pair? **Đáp án:** index 2 hợp lệ, nhưng trả low surrogate.

### Bài 6 — Bắt đầu ở 1

Một CLI nhận vị trí người dùng 1..5. Viết validation trước khi chuyển thành chỉ số 0..4. Kiểm tra cả `0`, `-1`, `6` và `Integer.MIN_VALUE` mà không làm phép trừ 1 trước validation.

### Bài 7 — End-exclusive

Cho `List.of("A","B","C")`, dự đoán `subList(1,3)`, `subList(3,3)` và `subList(2,4)`. **Đáp án:** `[B,C]`, `[]`, lỗi vượt giới hạn.

### Bài 8 — `Objects.checkIndex`

Chạy `ObjectsIndexCheckDemo`. Sửa các lời gọi để kiểm tra dải `[2,2)`, `[0,4)` và `from=3,size=0` với length 3. Điều kiện nào hợp lệ? Vì sao đoạn rỗng ở cuối có thể hợp lệ nhưng phần tử tại index 3 không tồn tại?

### Bài 9 — Tác động của mutation

Một `ArrayList` có size 4, thread A kiểm tra index 3 hợp lệ, thread B xóa phần tử trước khi A gọi `get(3)`. Giải thích vì sao check trước đó chưa đủ và đưa ra giải pháp ownership/snapshot/lock phù hợp.

### Bài 10 — Regression test

Viết JUnit 5 test cho một method `elementAt(int[], int)`: thử mảng rỗng, chỉ số âm, index cuối, index bằng length. Chỉ assert loại exception và hành vi, không dựa trên text message.

## 23. Checklist trước khi hoàn thành

- [ ] Tôi phân biệt được lớp cha `IndexOutOfBoundsException` và lớp con `ArrayIndexOutOfBoundsException` chưa?
- [ ] Tôi biết hai lớp này là unchecked `RuntimeException`, không phải checked exception chưa?
- [ ] Với truy cập phần tử, tôi luôn xác minh `0 <= i && i < length/size` chứ?
- [ ] Tôi không nhầm `length`/`size()` với chỉ số phần tử cuối chưa?
- [ ] Tôi xử lý mảng rỗng trước khi dùng `arr[0]` hoặc `arr[length-1]` chưa?
- [ ] Tôi dùng `<` thay vì `<=` trong vòng lặp đọc `arr[i]` chưa?
- [ ] Tôi phân biệt index của phần tử với vị trí chèn cho phép bằng `size` chưa?
- [ ] Tôi hiểu đoạn `[from,to)` cho phép `to == length` và có thể rỗng chưa?
- [ ] Tôi biết `List.get` theo hợp đồng ném `IndexOutOfBoundsException`, không phụ thuộc một subtype runtime chưa?
- [ ] Tôi biết `String.length` dùng UTF-16 code units, không luôn bằng số Unicode code points chưa?
- [ ] Với mảng nhiều chiều, tôi đã dùng `row.length` của từng hàng, không giả mọi hàng đều dài bằng nhau chưa?
- [ ] Tôi phân biệt bounds error với `NullPointerException`, `ArrayStoreException`, `NegativeArraySizeException` chưa?
- [ ] Tôi có validate đầu vào người dùng và chuyển one-based/zero-based đúng không?
- [ ] Tôi có cân nhắc `Objects.checkIndex`/`checkFromToIndex`/`checkFromIndexSize` khi viết API phạm vi chưa?
- [ ] Tôi tránh dùng `try/catch` để che bug vòng lặp hoặc trả thành công giả chưa?
- [ ] Tôi đặt catch subtype trước catch lớp cha nếu có cả hai chưa?
- [ ] Tôi đã xét concurrency và thay đổi size giữa check/use chưa?
- [ ] Tôi không phụ thuộc message hoặc số dòng stack trace như giao thức xử lý nghiệp vụ chưa?
- [ ] Tôi có test input `-1`, `0`, `n-1`, `n`, mảng rỗng và các đoạn rỗng chưa?

**Kết luận:** `ArrayIndexOutOfBoundsException` là **một loại `IndexOutOfBoundsException`** chuyên cho truy cập mảng. Cả hai là unchecked exceptions. Truy cập phần tử hợp lệ dùng **`0 <= index < length/size`**; một số API vị trí chèn hoặc dải **`[from,to)`** cho phép đầu mút bằng `length/size`. Giữ điều kiện vòng lặp chính xác, hiểu contract từng API, kiểm tra dữ liệu tại biên, xử lý mảng răng cưa và Unicode đúng loại chỉ số; nếu có lỗi, sửa invariant thay vì chỉ bắt rồi bỏ qua.