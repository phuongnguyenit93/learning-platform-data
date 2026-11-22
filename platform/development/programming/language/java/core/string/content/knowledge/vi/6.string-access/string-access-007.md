# toCharArray() và bản sao dữ liệu ký tự trong Java

## 1. Mục tiêu học tập

Phương thức `String.toCharArray()` chuyển nội dung một đối tượng `String` thành một **mảng `char[]` mới**, chứa các **đơn vị mã UTF-16** theo đúng thứ tự trong chuỗi. Mỗi lần gọi, phương thức cung cấp một mảng được cấp phát mới; thay đổi phần tử trong mảng này **không làm thay đổi chuỗi nguồn**.

Sau bài học, bạn có thể:

1. Dùng `toCharArray()` đúng cú pháp và xác định chính xác kiểu dữ liệu trả về.
2. Chứng minh mảng trả về là **bản sao độc lập** với `String` gốc và với các mảng từ lời gọi khác.
3. Đọc, duyệt, chỉnh sửa từng phần tử `char[]`; tạo `String` mới từ dữ liệu đã chỉnh sửa.
4. Hiểu sự khác nhau giữa **`char` (UTF-16 code unit)**, **Unicode code point** và **ký tự hiển thị**.
5. Chọn đúng giữa `toCharArray()`, `charAt()`, `getChars()` và các API xử lý code point.
6. Tránh lỗi liên quan đến chỉ số, giá trị `null`, surrogate pair, sao chép dữ liệu, bộ nhớ và cách in mảng.

Đây là phần học thuộc nhóm **Độ dài và truy cập** của Java Core String. Kiến thức cần có: `String`, mảng một chiều, kiểu `char`, vòng lặp, phép gán, tham chiếu và tính bất biến của `String`. Ví dụ đầy đủ sử dụng Java 17+.

## 2. toCharArray() làm gì?

Chữ ký phương thức theo Java API:

~~~java
public char[] toCharArray()
~~~

Cách dùng cơ bản:

~~~java
String word = "Java";
char[] letters = word.toCharArray();

System.out.println(letters.length);  // 4
System.out.println(letters[0]);      // J
System.out.println(letters[3]);      // a
~~~

`word` có kiểu `String`, còn `letters` có kiểu **`char[]`**. Mỗi phần tử của mảng chứa một đơn vị UTF-16 trong chuỗi. Mảng có độ dài bằng `word.length()`, vì cả hai đều đếm **UTF-16 code units** chứ không nhất thiết đếm ký tự người dùng nhìn thấy.

Cần phân biệt cú pháp:

| Tác vụ | Với String | Với char[] |
| --- | --- | --- |
| Độ dài | `word.length()` (phương thức) | `letters.length` (thuộc tính mảng) |
| Lấy phần tử ở vị trí `i` | `word.charAt(i)` | `letters[i]` |
| Thay phần tử `i` | Không có thao tác sửa tại chỗ | `letters[i] = 'K'` |
| Chuyển thành dữ liệu bên kia | `word.toCharArray()` | `new String(letters)` |
| Kiểu giá trị | `String` bất biến | `char[]` mutable, độ dài cố định |

Ví dụ duyệt mảng sau khi chuyển:

~~~java
String word = "Code";
char[] units = word.toCharArray();

for (int i = 0; i < units.length; i++) {
    System.out.println(i + ": " + units[i]);
}
~~~

Kết quả:

~~~text
0: C
1: o
2: d
3: e
~~~

Chỉ số bắt đầu từ `0` và kết thúc ở `length - 1`. Truy cập `units[-1]` hoặc `units[units.length]` sẽ ném `ArrayIndexOutOfBoundsException`.

## 3. Bản sao độc lập: thay đổi mảng không làm đổi chuỗi nguồn

Đây là cơ chế quan trọng nhất.

~~~java
String source = "Java";
char[] chars = source.toCharArray();

chars[0] = 'K';

System.out.println(source);           // Java
System.out.println(new String(chars)); // Kava
~~~

Sau `chars[0] = 'K'`, đối tượng `String` vẫn mang nội dung `"Java"`. Việc sửa mảng chỉ tác động lên **bản sao**. Minh họa:

~~~text
source ───────────────► String "Java"  (bất biến)
                            │
                            │ toCharArray()
                            ▼ sao chép giá trị
chars  ───────────────► char[] ['J', 'a', 'v', 'a']
                                   │
                                   │ chars[0] = 'K'
                                   ▼
                        char[] ['K', 'a', 'v', 'a']

source vẫn là "Java"
~~~

**Không nhầm "bản sao" với "view":** `toCharArray()` không trả về cửa sổ nhìn trực tiếp vào bộ nhớ mà `String` dùng để lưu nội dung. Bạn có quyền chỉnh sửa mảng nhận được nhưng không thể dùng việc đó để chỉnh sửa chuỗi. Cách biểu diễn nội bộ của `String` là chi tiết triển khai của JDK; từ Java 9 nhiều JDK sử dụng *Compact Strings*, không nên giả định đối tượng `String` tự lưu bằng `char[]`.

### Mỗi lần gọi có mảng riêng

~~~java
String text = "ABC";
char[] first = text.toCharArray();
char[] second = text.toCharArray();

System.out.println(first == second); // false

first[0] = 'X';
System.out.println(new String(first));  // XBC
System.out.println(new String(second)); // ABC
System.out.println(text);               // ABC
~~~

Hai lời gọi độc lập trả **hai mảng khác nhau**. Toán tử `==` trên hai mảng so sánh **tham chiếu**, không so sánh nội dung.

Nếu cần so nội dung mảng:

~~~java
char[] a = "java".toCharArray();
char[] b = "java".toCharArray();

System.out.println(a == b);                         // false
System.out.println(java.util.Arrays.equals(a, b)); // true
~~~

Sự khác biệt này quan trọng vì `String.equals()` so **nội dung** hai chuỗi, trong khi mảng `char[]` không tự ghi đè `Object.equals()` để so từng phần tử.

## 4. Từ char[] trở lại String cũng tạo ra giá trị độc lập

Nếu đã chỉnh sửa các ký tự và muốn có chuỗi tương ứng, hãy tạo đối tượng `String` từ mảng:

~~~java
char[] chars = {'J', 'a', 'v', 'a'};
String snapshot = new String(chars);

chars[0] = 'K';

System.out.println(snapshot);        // Java
System.out.println(new String(chars)); // Kava
~~~

`new String(chars)` **sao chép nội dung mảng** tại thời điểm tạo chuỗi. Thay đổi mảng sau đó không làm sửa `snapshot`.

Như vậy hai chiều đều có tính **snapshot độc lập** đối với những dữ liệu đang xét:

~~~text
String nguồn --toCharArray()--> char[] bản sao có thể sửa
char[] dữ liệu --new String(...)--> String mới bất biến
~~~

Từ `char[]` còn có thể tạo `String` bằng `String.valueOf(chars)`. Để tạo từ **một đoạn** của mảng, dùng constructor `new String(chars, offset, count)`; lưu ý `count` là **số phần tử**, không phải chỉ số kết thúc:

~~~java
char[] letters = {'J', 'a', 'v', 'a'};
String part = new String(letters, 1, 2);
System.out.println(part); // av
~~~

Chỉ số hoặc độ dài đoạn không hợp lệ gây `IndexOutOfBoundsException`. Dù chỉ chọn một đoạn, `String` tạo ra vẫn độc lập với thay đổi tiếp theo của mảng.

### Lưu ý: char[].toString() không chuyển nội dung mảng thành String

Một mảng là đối tượng. Gọi `chars.toString()` dùng cách biểu diễn mặc định của đối tượng, **không cho ra** nội dung ký tự mong muốn. Dùng:

~~~java
char[] chars = {'O', 'K'};

System.out.println(new String(chars));          // OK
System.out.println(String.valueOf(chars));       // OK
System.out.println(java.util.Arrays.toString(chars)); // [O, K]
~~~

`System.out.println(chars)` cũng hiển thị nội dung mảng bởi `PrintStream` có overload riêng nhận `char[]`. Đừng suy rộng hành vi này sang `chars.toString()` hoặc sang mọi API nhận `Object`.

## 5. char[] là mảng có thể sửa, nhưng có độ dài cố định

Mảng cho phép **thay phần tử**; kích thước không tự tăng giảm:

~~~java
char[] data = "cats".toCharArray();
data[0] = 'b';

System.out.println(new String(data)); // bats
System.out.println(data.length);      // 4
~~~

Nếu cần **chèn hoặc xóa** làm thay đổi độ dài, `StringBuilder` thường thuận tiện hơn. Nếu mục tiêu chỉ là đọc vài ký tự mà không cần một mảng độc lập, `String.charAt()` tránh phải cấp phát mảng `char[]` đầy đủ.

Cần nhớ ba tầng trạng thái:

1. **Chuỗi nguồn:** immutable.
2. **Mảng bản sao:** mutable theo từng phần tử, kích thước cố định.
3. **Chuỗi tạo lại từ mảng:** snapshot immutable, không theo dõi những thay đổi sau đó của mảng.

### Sao chép mảng sang mảng khác

Một phép gán mảng **không sao chép phần tử**:

~~~java
char[] first = "Hi".toCharArray();
char[] alias = first;

alias[0] = 'B';
System.out.println(new String(first)); // Bi
~~~

`alias` và `first` là hai tham chiếu đến **cùng một mảng**. Nếu muốn bản sao độc lập của `char[]`:

~~~java
char[] first = "Hi".toCharArray();
char[] copy = first.clone();

copy[0] = 'B';
System.out.println(new String(first)); // Hi
System.out.println(new String(copy));  // Bi
~~~

Có thể dùng `Arrays.copyOf(first, first.length)` hoặc `System.arraycopy(...)` khi phù hợp. Đừng nhầm việc **sao chép từ String bằng toCharArray()** với việc **gán tham chiếu giữa hai biến char[]**.

## 6. Quan hệ với length() và charAt()

Đối với mọi chỉ số hợp lệ `i`, giá trị `source.toCharArray()[i]` tương ứng với `source.charAt(i)` tại thời điểm chuyển. Cả hai API đều thao tác với **UTF-16 code unit**.

~~~java
String word = "Java";
char[] copy = word.toCharArray();

for (int i = 0; i < word.length(); i++) {
    System.out.println(word.charAt(i) == copy[i]);
}
~~~

Cả bốn dòng in `true`. Tuy nhiên cách dùng khác nhau:

- `charAt(i)`: đọc một đơn vị ký tự tại vị trí `i` từ `String` mà không tạo một `char[]` hoàn chỉnh.
- `toCharArray()`: lấy toàn bộ nội dung thành mảng mới để có thể duyệt nhiều lần, dùng API yêu cầu `char[]`, hoặc thay dữ liệu trong **bản sao**.
- Sau khi đã chỉnh sửa mảng, `word.charAt(i)` vẫn đọc từ chuỗi gốc, nên không phản ánh thay đổi trên mảng.

Cả `length()` và `toCharArray().length` đều sử dụng đơn vị UTF-16; không được xem kết quả này luôn là số chữ cái, code points hay grapheme.

### Chuỗi rỗng và null

~~~java
String empty = "";
char[] emptyArray = empty.toCharArray();

System.out.println(emptyArray.length); // 0
~~~

Mảng trả về hợp lệ và có độ dài `0`. Ngược lại:

~~~java
String missing = null;
// missing.toCharArray(); // NullPointerException
~~~

`null` không phải chuỗi rỗng. Khi API nhận dữ liệu không chắc chắn, xác định quy tắc của hàm rõ ràng:

~~~java
static char[] orEmpty(String input) {
    return input == null ? new char[0] : input.toCharArray();
}
~~~

Hàm minh họa trên **chọn** biến `null` thành mảng rỗng. Trong các tình huống khác, trả `null` hoặc ném ngoại lệ với thông báo cụ thể có thể đúng hơn; không mặc định mọi ứng dụng nên làm giống ví dụ.

## 7. Unicode: char[] chứa UTF-16 code units, không phải "ký tự nhìn thấy"

Đây là điểm quan trọng nhất khi dùng `toCharArray()` cho tiếng Việt, emoji và văn bản quốc tế.

Java `char` là một **đơn vị 16 bit**. Một code point Unicode ở ngoài **Basic Multilingual Plane (BMP)** cần **hai** đơn vị UTF-16 gọi là *surrogate pair*. Ví dụ emoji `😀` là một code point nhưng chiếm hai phần tử `char[]`.

~~~java
String text = "A😀B";
char[] units = text.toCharArray();

System.out.println(text.length());                       // 4
System.out.println(units.length);                        // 4
System.out.println(text.codePointCount(0, text.length())); // 3
System.out.println(Character.isHighSurrogate(units[1])); // true
System.out.println(Character.isLowSurrogate(units[2]));  // true
~~~

Sơ đồ:

~~~text
Văn bản hiển thị:   A     😀       B
Code points:        A   U+1F600    B       (3 code points)
UTF-16 code units: [A] [high] [low] [B]   (4 char)
Chỉ số mảng:        0     1     2    3
~~~

**Hậu quả quan trọng:**

- `units[1]` là **high surrogate**, `units[2]` là **low surrogate**. In riêng từng đơn vị có thể không hiển thị thành emoji mong đợi.
- Nếu sửa một nửa surrogate pair mà không xử lý nửa kia, mảng (và `String` tạo từ nó) có thể chứa **surrogate đơn lẻ** và dữ liệu Unicode không hợp lệ về mặt cặp surrogate.
- `toCharArray()` chỉ sao chép các code units. Nó **không** tự tách văn bản thành Unicode code points hoặc ký tự người dùng cảm nhận.

### Khi cần duyệt code points

Sử dụng `String.codePoints()`, trả về `IntStream` của các code points, rồi chuyển thành `int[]` khi cần mảng độc lập:

~~~java
String text = "A😀B";
int[] points = text.codePoints().toArray();

System.out.println(points.length);       // 3
System.out.println(points[1] == 0x1F600); // true
~~~

Có thể duyệt code point bằng `Character.toChars(codePoint)` hoặc khôi phục bằng constructor `new String(int[] codePoints, int offset, int count)`. Mảng `int[]` phù hợp khi thuật toán làm việc trên code points hơn là code units.

**Code point chưa chắc là một "ký tự nhìn thấy".** Chẳng hạn `"e\u0301"` có hai code points (chữ e và dấu sắc kết hợp) nhưng có thể hiển thị như một ký tự. Một số emoji là chuỗi nhiều code points ghép lại. Nếu thuật toán yêu cầu phân đoạn theo *grapheme cluster*, cần dùng công cụ phân đoạn Unicode phù hợp chứ không chỉ `toCharArray()` hoặc `codePoints()`.

### Không nhầm với byte và mã hóa ký tự

`char[]` chứa **đơn vị UTF-16**. `byte[]` từ `getBytes(StandardCharsets.UTF_8)` chứa **các byte đã mã hóa theo UTF-8**. Hai cấu trúc khác nhau về phần tử, độ dài và ý nghĩa. Với nhiều emoji, số byte UTF-8 là 4, số `char` UTF-16 là 2, số code point là 1.

~~~java
String emoji = "😀";
char[] chars = emoji.toCharArray();
byte[] bytes = emoji.getBytes(java.nio.charset.StandardCharsets.UTF_8);

System.out.println(chars.length); // 2
System.out.println(bytes.length); // 4
~~~

`toCharArray()` không thực hiện mã hóa hay giải mã UTF-8, nên không dùng nó thay `getBytes()` khi ghi dữ liệu ra file/mạng.

## 8. So với getChars(), charAt() và StringBuilder

| Nhu cầu | Lựa chọn thường phù hợp | Vì sao |
| --- | --- | --- |
| Đọc 1–vài vị trí trong chuỗi | `charAt(i)` | Tránh tạo mảng chứa toàn bộ chuỗi |
| Cần mảng ký tự **độc lập** toàn bộ chuỗi | `toCharArray()` | Cấp phát và trả `char[]` mới |
| Chép **một đoạn** vào mảng đã có | `getChars(srcBegin, srcEnd, dst, dstBegin)` | Điều khiển phạm vi nguồn và điểm bắt đầu đích |
| Cần chỉnh sửa nội dung theo nhiều bước, độ dài có thể đổi | `StringBuilder` | Hỗ trợ thêm, xóa, chèn, thay mà không cố định độ dài |
| Cần duyệt Unicode code points | `codePoints()` | Tránh tách một surrogate pair thành hai đơn vị độc lập |
| Cần UTF-8 để truyền dữ liệu | `getBytes(StandardCharsets.UTF_8)` | Mã hóa thành byte[] theo charset chỉ định |

### getChars(): chép đoạn vào mảng đích có sẵn

~~~java
String text = "Hello";
char[] destination = {'_', '_', '_', '_', '_', '_'};

text.getChars(1, 4, destination, 2);

System.out.println(new String(destination)); // __ell_
~~~

Cận `srcEnd` là **exclusive**: `getChars(1, 4, ...)` chép `'e'`, `'l'`, `'l'` (ba ký tự), bắt đầu ở `destination[2]`. Phương thức **trả về `void`**, thực hiện sao chép vào mảng đích mà người gọi đưa vào; nó không đổi `text`.

Khác với `toCharArray()`, `getChars()` không tạo mảng đích cho bạn. Bạn phải cấp phát đủ phần tử. Khoảng chỉ số không hợp lệ có thể ném `IndexOutOfBoundsException`.

### StringBuilder khi cần thay đổi độ dài

~~~java
StringBuilder builder = new StringBuilder("Java");
builder.insert(0, "Core ");
builder.append(" 17");

System.out.println(builder.toString()); // Core Java 17
~~~

Mảng `char[]` không thể tự mở rộng kích thước để thêm một đoạn dài hơn. `StringBuilder` có thể phát triển dung lượng và thuận tiện hơn cho thao tác lặp đi lặp lại. Tuy nhiên nó là đối tượng **mutable**, không giống `String`.

## 9. Bộ nhớ, hiệu năng và tính an toàn dữ liệu

**Chi phí của toCharArray():** để chép một chuỗi có `n` đơn vị UTF-16, phương thức phải tạo mảng đủ `n` phần tử và sao chép nội dung. Vì vậy, thời gian và bộ nhớ thêm là **O(n)** theo độ dài chuỗi. Khi cần tạo bản sao để sửa hoặc chuyển cho API yêu cầu mảng, chi phí này có mục đích rõ ràng. Khi chỉ muốn đọc một vài vị trí, `charAt()` có thể hiệu quả hơn vì không phải tạo cả mảng.

**Không giữ bản sao lâu hơn cần thiết:** mỗi `char[]` là một đối tượng có dữ liệu riêng; lặp `toCharArray()` hàng nghìn lần trên chuỗi lớn có thể làm tăng phân bổ bộ nhớ không cần thiết. Nếu cần dùng mảng trong một khối xử lý, chuyển một lần rồi tái sử dụng mảng đó khi đúng logic.

**Không tự tạo độ an toàn tuyệt đối từ bản sao:** bản sao độc lập giúp code sửa mảng mà không ảnh hưởng `String` nguồn, nhưng `char[]` vẫn mutable. Nếu chia sẻ **cùng mảng** cho nhiều đoạn code, một đoạn có thể sửa dữ liệu của đoạn khác. Hãy cân nhắc `clone()` hoặc `Arrays.copyOf()` ở ranh giới API khi cần bảo vệ dữ liệu.

**Dữ liệu nhạy cảm:** một `char[]` có thể được ghi đè khi không còn dùng:

~~~java
char[] sensitive = {'1', '2', '3'};
java.util.Arrays.fill(sensitive, '\0');
~~~

Tuy nhiên, nếu mảng được tạo bằng `existingString.toCharArray()` thì xóa mảng **không xóa chuỗi nguồn** hoặc các bản sao khác từng tồn tại trong bộ nhớ. Không được coi `toCharArray()` + `Arrays.fill()` là bảo đảm xóa sạch mọi dấu vết của dữ liệu. Với API nhận bí mật, ưu tiên cơ chế quản lý bí mật phù hợp ngay từ lúc nhận dữ liệu, thay vì chủ động tạo `String` chứa bí mật.

**Lưu ý:** `String.toCharArray()` không lấy đi quyền sở hữu của `String`; nó chỉ tạo một bản sao. Tính bất biến của `String` giúp nội dung gốc không bị thay đổi qua mảng nhận được, nhưng việc công bố/chia sẻ một mảng mutable cần thiết kế rõ ràng.

## 10. Ví dụ tổng hợp có thể chạy độc lập (Java 17+)

Tạo file tên **`CharArrayCopyDemo.java`**:

~~~java
import java.util.Arrays;

public class CharArrayCopyDemo {
    public static void main(String[] args) {
        String source = "Java";
        char[] first = source.toCharArray();
        char[] second = source.toCharArray();

        System.out.println(first == second);
        first[0] = 'K';
        System.out.println(source);
        System.out.println(new String(first));
        System.out.println(new String(second));

        String snapshot = new String(first);
        first[1] = 'o';
        System.out.println(new String(first));
        System.out.println(snapshot);

        char[] destination = {'_', '_', '_', '_', '_', '_'};
        "Hello".getChars(1, 4, destination, 2);
        System.out.println(new String(destination));

        String unicode = "A😀B";
        char[] units = unicode.toCharArray();
        System.out.println(unicode.length());
        System.out.println(units.length);
        System.out.println(unicode.codePointCount(0, unicode.length()));
        System.out.println(Character.isHighSurrogate(units[1]));
        System.out.println(Character.isLowSurrogate(units[2]));

        System.out.println(Arrays.toString("OK".toCharArray()));
    }
}
~~~

Biên dịch và chạy trong cùng thư mục với file:

~~~bash
javac CharArrayCopyDemo.java
java CharArrayCopyDemo
~~~

Stdout **chính xác**:

~~~text
false
Java
Kava
Java
Kova
Kava
__ell_
4
4
3
true
true
[O, K]
~~~

Đọc hiểu output theo nhóm:

1. `first == second` là `false` vì hai lần `toCharArray()` trả hai mảng độc lập.
2. Sửa `first[0]` thành `'K'` khiến mảng thứ nhất hiển thị `"Kava"`, trong khi `source` và `second` vẫn là `"Java"`.
3. `snapshot` nhận bản chụp `"Kava"`; sửa tiếp `first[1]` thành `'o'` cho `"Kova"` không làm đổi `snapshot`.
4. `getChars(1, 4, ...)` chép ba ký tự `"ell"` vào mảng đã có ở vị trí `2`, kết quả `"__ell_"`.
5. `"A😀B"` chứa **4 code units** nhưng **3 Unicode code points**, vị trí `1` và `2` là high/low surrogate.
6. `Arrays.toString()` hiển thị danh sách phần tử dạng `[O, K]` thay vì nối trực tiếp thành `"OK"`.

Muốn kiểm chứng thêm, hãy sửa `source` thành `"Hi"` và điều chỉnh các vị trí đang truy cập. Đừng chỉ thay input mà giữ nguyên chỉ số vì điều đó sẽ gây ngoại lệ ngoài biên.

## 11. Bài tập luyện tập theo mức độ

### Bài tập 1 — Chuyển và duyệt

Viết `printIndexedChars(String text)` dùng `toCharArray()` và vòng `for` để in các đơn vị UTF-16 cùng chỉ số. Kiểm thử với `"Java"`, `""` và `"A😀B"`. Giải thích vì sao đầu vào emoji cần thận trọng khi in từng `char`.

### Bài tập 2 — Chứng minh bản sao

Tạo hai mảng bằng hai lần gọi `"Code".toCharArray()`. Đổi phần tử đầu tiên của mảng thứ nhất thành `'N'`; in chuỗi nguồn và hai mảng bằng `new String(...)`. Dự đoán trước kết quả và giải thích vì sao mảng thứ hai giữ nguyên.

### Bài tập 3 — Snapshot khi chuyển ngược

Tạo `char[] chars = {'C', 'a', 't'};` rồi `String animal = new String(chars);`. Sau đó sửa `chars[0] = 'B';`. In cả `animal` và `new String(chars)`, mô tả cơ chế độc lập giữa hai giá trị.

### Bài tập 4 — So sánh mảng đúng cách

Tạo `char[] a = "abc".toCharArray();`, `char[] b = "abc".toCharArray();`. So sánh bằng `==` và `Arrays.equals()`. Tại sao một phương thức có kết quả `false` và phương thức kia cho `true`?

### Bài tập 5 — Sao chép một đoạn

Với chuỗi `"012345"` và mảng đích sáu dấu `'_'`, sử dụng `getChars(2, 5, dst, 1)`. Kết quả mong đợi là `"_234__"`. Giải thích cách tính cận cuối và số phần tử được chép.

### Bài tập 6 — Unicode

Đo `length()`, `toCharArray().length`, `codePointCount()` và `codePoints().toArray().length` của `"😀😀"`. Kỳ vọng lần lượt `4`, `4`, `2`, `2`. Giải thích tại sao chỉ số mảng `char[]` không tương ứng trực tiếp với số emoji.

### Bài tập 7 — Chọn giải pháp

Viết hai phiên bản đếm số ký tự ASCII `'a'` trong một chuỗi: phiên bản đọc bằng `charAt()` và phiên bản dùng `toCharArray()`. Cả hai cần cho cùng kết quả. Phân tích sự đánh đổi: `charAt()` không cấp phát mảng; `toCharArray()` tạo một snapshot mà bạn có thể thao tác độc lập.

### Bài tập 8 — Thao tác nhạy cảm

Cho một mảng `char[]` nhận được từ API, dùng `Arrays.fill(chars, '\0')` sau khi sử dụng. Giải thích sự khác biệt giữa xóa **mảng ấy** và khẳng định dữ liệu đã bị xóa khỏi **toàn bộ bộ nhớ JVM** (khẳng định sau không được bảo đảm). Thảo luận vì sao chuyển bí mật thành `String` có thể làm tăng số bản lưu trong bộ nhớ.

## 12. Lỗi thường gặp và tiêu chí hoàn thành

| Lỗi | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Nghĩ `toCharArray()` sửa String | String immutable; phương thức chỉ trả bản sao | Nhận `char[]`, sửa bản sao và tạo String mới khi cần |
| Gọi `text.toCharArray()` rồi bỏ kết quả | Mảng được trả về không được lưu hoặc sử dụng | `char[] units = text.toCharArray();` |
| Dùng `chars.length()` | Mảng có thuộc tính `length`, không có phương thức này | `chars.length` |
| Dùng `chars.toString()` để lấy văn bản | Trả biểu diễn đối tượng mảng | `new String(chars)` hoặc `String.valueOf(chars)` |
| So `char[]` bằng `==` khi cần so nội dung | `==` so tham chiếu | `Arrays.equals(a, b)` |
| Tin rằng `char[] alias = chars` là bản sao | Chỉ sao chép tham chiếu | `chars.clone()` hoặc `Arrays.copyOf(...)` |
| Nghĩ một `char` luôn là một Unicode code point | Surrogate pair cần hai `char` | Dùng `codePoints()` khi xử lý code points |
| Cắt hoặc sửa riêng một nửa surrogate pair | Có thể tạo surrogate lẻ | Bảo toàn cặp hoặc xử lý bằng code point |
| Không xử lý `null` | Gọi phương thức trên `null` ném NPE | Xác định contract và kiểm tra trước |
| Nhầm `char[]` với `byte[]` | Code units UTF-16 khác byte mã hóa | `getBytes(UTF_8)` khi cần mã hóa |
| Gọi `toCharArray()` lặp lại không cần thiết | Tạo bản sao và chi phí O(n) mỗi lần | Tái sử dụng mảng hoặc dùng `charAt()` |
| Tưởng xóa mảng cũng xóa mọi bản sao String | Các snapshot độc lập | Quản lý bí mật ngay từ lúc nhập, tránh tạo String không cần |

**Tự kiểm tra trước khi hoàn thành bài:**

1. `toCharArray()` trả về kiểu gì và có thay đổi chuỗi nguồn không?
2. Vì sao hai lời gọi `toCharArray()` trả hai mảng có thể có nội dung giống nhau nhưng `==` là `false`?
3. Khi `chars[0]` thay đổi, điều gì xảy ra với `String` nguồn và với một `String` đã tạo bằng `new String(chars)` trước đó?
4. Khi nào nên dùng `charAt()` thay vì `toCharArray()`? Khi nào nên dùng `getChars()`?
5. Vì sao `"😀".toCharArray().length` bằng `2` mà `"😀".codePointCount(0, 2)` bằng `1`?
6. Mảng `char[]` có thể thay đổi kích thước không? Nếu cần nối, chèn, xóa nhiều lần thì công cụ nào phù hợp hơn?
7. Vì sao `Arrays.fill(chars, '\0')` không đồng nghĩa mọi dấu vết dữ liệu nhạy cảm đã biến mất?

**Quy tắc ghi nhớ:** `String.toCharArray()` tạo **mảng `char[]` mới chứa bản sao các đơn vị UTF-16**. Bạn có thể thay đổi **mảng ấy**, nhưng **không thể sửa String nguồn thông qua mảng**. Muốn biến đổi dữ liệu rồi có chuỗi, hãy tạo một `String` mới từ mảng đã sửa.

### Tài liệu tham khảo

- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `toCharArray()`, `length()`, `charAt()`, `getChars()`, constructors và `codePoints()`.
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): surrogate pairs, code points và `Character.toChars()`.
- [Java SE 17 — Arrays](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): `Arrays.equals()`, `Arrays.copyOf()`, `Arrays.fill()` và `Arrays.toString()`.
- [Java SE 17 — StringBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html): thao tác thay đổi nội dung và chuyển sang `String`.
