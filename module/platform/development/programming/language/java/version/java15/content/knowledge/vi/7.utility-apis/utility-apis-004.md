# Triển khai CharSequence tùy biến và xung đột default method trong Java 15+

## 1. Vì sao chủ đề này quan trọng?

`CharSequence` (gói `java.lang`) mô tả **một dãy ký tự có thể đọc được** thông qua `length()`, `charAt(int)`, `subSequence(int, int)` và `toString()`. Các API cần đọc văn bản có thể nhận `CharSequence` thay vì buộc đối số phải là `String`. Những lớp quen thuộc như `String` và `StringBuilder` đều triển khai giao diện này.

**Điểm thay đổi được bổ sung trong Java 15:** `CharSequence` có một **default method**:

~~~java
default boolean isEmpty() {
    return length() == 0;
}
~~~

Đây là phương thức chính thức, vẫn có trong Java hiện hành. Một lớp triển khai `CharSequence` có thể sử dụng `isEmpty()` mà **không cần tự viết phương thức**. Tuy nhiên, nếu lớp đó đồng thời triển khai một interface khác cũng có `default boolean isEmpty()` không có quan hệ kế thừa phù hợp, Java không thể tự chọn một trong hai phương thức. Khi đó lập trình viên phải giải quyết xung đột một cách tường minh.

Bài này tập trung vào cách viết triển khai `CharSequence` đúng hợp đồng, cách Java chọn default method, trường hợp xung đột khi nâng cấp lên Java 15+, và cách sửa được kiểm chứng trên Java 17.

## 2. Hợp đồng tối thiểu của CharSequence

Để tạo một lớp `TextSlice implements CharSequence`, cần triển khai các thành viên trừu tượng:

| Thành viên | Ý nghĩa và hợp đồng |
| --- | --- |
| `int length()` | Số **UTF-16 code unit** (`char`) của chuỗi, không nhất thiết là số Unicode code point. |
| `char charAt(int index)` | Trả về `char` ở chỉ số bắt đầu từ 0; chỉ số ngoài `[0, length())` phải bị từ chối. |
| `CharSequence subSequence(int start, int end)` | Trả về dãy ký tự từ `start` **bao gồm** đến `end` **không bao gồm**. Điều kiện: `0 <= start <= end <= length()`. |
| `String toString()` | Trả về `String` có đúng các ký tự theo cùng thứ tự của dãy hiện tại. |

Từ Java 15, các phương thức **default** sẵn có bao gồm:

- `isEmpty()` — mặc định trả về `length() == 0`.
- `chars()` — trả `IntStream` của từng UTF-16 `char` (số phần tử thường bằng `length()`).
- `codePoints()` — trả `IntStream` của Unicode code point; cặp surrogate hợp lệ được ghép thành một code point.

`chars()` và `codePoints()` đã có từ trước Java 15 và vẫn được hỗ trợ. Điểm mới gắn với chủ đề Java 15 là **`isEmpty()` trên giao diện `CharSequence`**, cho phép gọi `someCharSequence.isEmpty()` qua kiểu giao diện.

### isEmpty khác isBlank

`isEmpty()` chỉ kiểm tra độ dài bằng 0; nó **không kiểm tra chuỗi toàn khoảng trắng**:

~~~java
CharSequence spaces = "   ";
System.out.println(spaces.isEmpty()); // false
System.out.println("   ".isBlank());  // true
~~~

`isBlank()` ở ví dụ sau là phương thức của `String`. Nếu biến có kiểu `CharSequence`, không mặc nhiên có `isBlank()`. Chỉ dùng `toString().isBlank()` khi điều đó phù hợp với đặc điểm của đối tượng và mục tiêu của chương trình.

## 3. Ví dụ triển khai tùy biến và chủ động xử lý xung đột

Giả sử một thư viện khác có giao diện `OtherEmpty` cũng định nghĩa `default boolean isEmpty()`. Để làm rõ xung đột, ví dụ cho phương thức đó trả về `false`. Đó là một giá trị minh họa, không phải quy tắc dành cho mọi interface khác.

Một lớp muốn triển khai **cả `CharSequence` lẫn `OtherEmpty`** phải ghi đè `isEmpty()` để nói rõ hành vi nào được dùng. Ở đây ta chọn hợp đồng của `CharSequence`.

~~~java
import java.util.Objects;

public class CharSequenceConflictDemo {
    interface OtherEmpty {
        default boolean isEmpty() {
            return false;
        }
    }

    static final class TextSlice implements CharSequence, OtherEmpty {
        private final String value;

        TextSlice(String value) {
            this.value = Objects.requireNonNull(value);
        }

        @Override
        public int length() {
            return value.length();
        }

        @Override
        public char charAt(int index) {
            return value.charAt(index);
        }

        @Override
        public CharSequence subSequence(int start, int end) {
            return new TextSlice(value.substring(start, end));
        }

        @Override
        public String toString() {
            return value;
        }

        @Override
        public boolean isEmpty() {
            return CharSequence.super.isEmpty();
        }
    }

    public static void main(String[] args) {
        TextSlice empty = new TextSlice("");
        TextSlice letters = new TextSlice("abc");
        String emoji = new String(Character.toChars(0x1F642));
        TextSlice unicode = new TextSlice("A" + emoji);

        System.out.println("empty=" + empty.isEmpty());
        System.out.println("letters=" + letters.isEmpty());
        System.out.println("sub=" + letters.subSequence(1, 3));
        System.out.println("charAt=" + letters.charAt(0));
        System.out.println("utf16=" + unicode.length());
        System.out.println("chars=" + unicode.chars().count());
        System.out.println("codePoints=" + unicode.codePoints().count());
        System.out.println("equals=" + "abc".equals(letters));
        System.out.println("contentEquals=" + "abc".contentEquals(letters));
        System.out.println("otherDefault=" + new OtherEmpty() {}.isEmpty());
    }
}
~~~

Tên tệp bắt buộc là **`CharSequenceConflictDemo.java`** vì lớp `public` có cùng tên. Biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 CharSequenceConflictDemo.java
java CharSequenceConflictDemo
~~~

**Kết quả stdout chính xác** (đã biên dịch và chạy thành công với mức ngôn ngữ Java 17):

~~~text
empty=true
letters=false
sub=bc
charAt=a
utf16=3
chars=3
codePoints=2
equals=false
contentEquals=true
otherDefault=false
~~~

Những điểm quan trọng:

- `TextSlice("")` trả `true` vì phương thức được chọn là `CharSequence.super.isEmpty()` và `length()` bằng 0.
- `TextSlice("abc")` trả `false`. `subSequence(1, 3)` lấy `"bc"` và `charAt(0)` lấy ký tự `a`.
- Chuỗi chứa ký tự `A` cộng một Unicode code point ngoài BMP có `length() == 3` (một `char` cho A và hai `char` cho cặp surrogate), nhưng `codePoints().count() == 2`.
- `"abc".equals(letters)` trả `false` vì `String.equals` không đánh giá một đối tượng tùy biến là `String` tương đương. `"abc".contentEquals(letters)` trả `true` vì nó so sánh nội dung ký tự.
- `OtherEmpty` tự nó trả `false`; khi kết hợp với `CharSequence` trong `TextSlice`, **phương thức override của lớp** quyết định kết quả.

Lớp triển khai dựa trên `String` bất biến, bảo vệ đối số không được `null` qua `Objects.requireNonNull`, và ủy quyền kiểm tra phạm vi cho `String.charAt` / `String.substring`. Đây là một mẫu đơn giản để giữ hợp đồng của `CharSequence` nhất quán.

## 4. Vì sao xảy ra xung đột default method?

Xét **ví dụ cố ý không biên dịch được** sau. Nó chỉ dùng để quan sát nguyên nhân; không đưa chung vào file chương trình chạy ở mục 3:

~~~java
interface OtherEmpty {
    default boolean isEmpty() {
        return false;
    }
}

interface Conflicted extends CharSequence, OtherEmpty {
}
~~~

Kể từ Java 15, `CharSequence` và `OtherEmpty` đều có **default method cùng chữ ký `boolean isEmpty()`**. Hai giao diện này **không kế thừa nhau**, nên không có phương thức nào hiển nhiên cụ thể hơn. Theo Java Language Specification, một interface kế thừa hai default method với chữ ký tương đương như vậy là **lỗi biên dịch**.

Với `javac --release 17`, phần chẩn đoán chính có nội dung tương đương:

~~~text
interface Conflicted inherits unrelated defaults for isEmpty() from types CharSequence and OtherEmpty
~~~

Tên dòng/file và vị trí dấu mũ trong thông báo phụ thuộc cách sắp xếp mã; bản chất lỗi là **unrelated defaults for isEmpty()**. Đây là quy tắc tại thời điểm biên dịch, không phải tình huống Java tự động chọn ngẫu nhiên một default lúc chạy.

Tương tự, một **lớp** khai báo `implements CharSequence, OtherEmpty` mà không cung cấp cách giải quyết xung đột cũng không thể trở thành lớp cụ thể hợp lệ chỉ nhờ triển khai `length()`, `charAt()`, `subSequence()` và `toString()`.

### Phạm vi ảnh hưởng khi chuyển sang Java 15+

Trước Java 15, `CharSequence` chưa khai báo `isEmpty()`. Một hệ thống có giao diện khác mang default `isEmpty()` có thể không gặp xung đột này. Khi **biên dịch lại mã nguồn** với nền tảng Java 15 trở lên, cùng khai báo kế thừa có thể trở nên xung đột vì giao diện chuẩn nay có thêm một default method.

Không phải mọi lớp `implements CharSequence` đều lỗi khi nâng cấp. Chỉ phát sinh vấn đề trong cấu trúc kế thừa có các phương thức trùng chữ ký nhưng không giải quyết được theo quy tắc của Java. Lớp có `public boolean isEmpty()` phù hợp và được chọn rõ ràng có thể tránh xung đột.

## 5. Ba cách giải quyết đúng

### 5.1. Ghi đè isEmpty trong lớp triển khai

Trong lớp `TextSlice implements CharSequence, OtherEmpty`, chọn rõ ràng một trong hai cách:

~~~java
@Override
public boolean isEmpty() {
    return CharSequence.super.isEmpty();
}
~~~

Hoặc:

~~~java
@Override
public boolean isEmpty() {
    return length() == 0;
}
~~~

Hai cách trên cho cùng ý nghĩa theo hợp đồng hiện hành của `CharSequence`. Với cú pháp `CharSequence.super.isEmpty()`, `CharSequence` phải là **superinterface trực tiếp phù hợp** tại vị trí gọi; nếu kiến trúc kế thừa không cho phép gọi kiểu đó, `return length() == 0` là cách đơn giản và rõ ràng. Không dùng `OtherEmpty.super.isEmpty()` trừ khi hợp đồng nghiệp vụ thực sự yêu cầu hành vi của interface đó.

Đừng viết `return isEmpty();` ngay trong chính override: nó tự gọi lại phương thức hiện tại vô hạn, dẫn đến `StackOverflowError` khi chạy.

### 5.2. Giải quyết ngay tại subinterface

Nếu một giao diện cần kết hợp hai nguồn hành vi, nó có thể định nghĩa lại `isEmpty()` để giải quyết xung đột cho tất cả lớp triển khai:

~~~java
interface OtherEmpty {
    default boolean isEmpty() {
        return false;
    }
}

interface ResolvedSequence extends CharSequence, OtherEmpty {
    @Override
    default boolean isEmpty() {
        return CharSequence.super.isEmpty();
    }
}
~~~

Đây là ví dụ **khai báo interface**, chưa phải chương trình độc lập có `main`. Các lớp cụ thể `implements ResolvedSequence` vẫn phải triển khai bốn phương thức trừu tượng của `CharSequence`. Giá trị mặc định `isEmpty()` đã được chỉ rõ ngay tại `ResolvedSequence`.

### 5.3. Thiết kế lại tên phương thức khi ý nghĩa khác nhau

Nếu `OtherEmpty.isEmpty()` đang kiểm tra **trạng thái của một bộ nhớ đệm hoặc một nhóm phần tử**, còn `CharSequence.isEmpty()` kiểm tra **độ dài văn bản**, việc trùng tên che giấu hai khái niệm khác nhau. Nên đổi tên phương thức nghiệp vụ thành tên giàu ý nghĩa, ví dụ `isCacheEmpty()` hoặc `hasElements()`, nếu có quyền thay đổi API đó. Lúc ấy không còn tranh chấp cùng chữ ký và người đọc không phải đoán “empty” ám chỉ điều gì.

Không nên sửa hợp đồng của `CharSequence.isEmpty()` để trả giá trị trái với `length() == 0` chỉ nhằm vượt qua lỗi biên dịch. Có thể máy biên dịch chấp nhận override, nhưng các lời gọi sử dụng đối tượng theo kiểu `CharSequence` sẽ nhận kết quả không nhất quán.

## 6. Quy tắc chọn phương thức: không phải lúc nào cũng xung đột

Java áp dụng quy tắc kế thừa và override, không đơn thuần so số lượng phương thức cùng tên.

| Tình huống | Cách Java xác định phương thức |
| --- | --- |
| Chỉ triển khai `CharSequence`, không có override `isEmpty()` | Sử dụng default `CharSequence.isEmpty()`. |
| Lớp tự khai báo `public boolean isEmpty()` | Phương thức của **lớp** được ưu tiên; phải giữ hợp đồng phù hợp. |
| Một superclass có phương thức instance `public boolean isEmpty()` hợp lệ | Phương thức lớp cụ thể có ưu tiên cao hơn default của interface. |
| Một subinterface ghi đè default `isEmpty()` từ `CharSequence` | Phương thức của interface **cụ thể hơn** có thể được chọn theo quan hệ kế thừa. |
| Hai interface không liên quan cung cấp default `isEmpty()` cùng chữ ký | Phải khai báo override tường minh để giải quyết; nếu không là lỗi biên dịch. |

Hai nguyên tắc hay dùng khi đọc cấu trúc kế thừa:

1. **Class wins:** phương thức instance cụ thể của lớp có ưu tiên so với default method của interface.
2. **More specific interface wins:** nếu một default method đã override một default khác theo quan hệ kế thừa, phương thức cụ thể hơn được ưu tiên.

Nguyên tắc trên **không** cho phép một interface tùy ý “thắng” chỉ vì xuất hiện trước trong danh sách `implements`. Việc đảo thứ tự `implements OtherEmpty, CharSequence` không chữa được hai default method độc lập có cùng chữ ký.

Khi hai interface độc lập trùng phương thức, nên viết override trực tiếp để thể hiện sự lựa chọn rõ ràng; đây cũng là vị trí thích hợp để kiểm tra hợp đồng nghiệp vụ và tránh thay đổi hành vi âm thầm.

## 7. Các bẫy khi triển khai CharSequence tùy biến

### 7.1. length và charAt làm việc với UTF-16 code unit

`CharSequence` không cam kết mỗi ký tự người dùng nhìn thấy tương ứng với đúng một `char`. Ký tự ngoài BMP có thể dùng hai code unit; tổ hợp ký tự Unicode còn có thể phức tạp hơn. Vì vậy:

- `length()` đếm đơn vị UTF-16.
- `charAt()` trả từng `char`, có thể là một nửa cặp surrogate.
- `chars()` đi qua các code unit.
- `codePoints()` ghép các cặp surrogate hợp lệ, trả Unicode code point.

Ví dụ Java ở mục 3 đưa ra `utf16=3`, `chars=3`, `codePoints=2` khi dữ liệu gồm `A` và code point `U+1F642`. Đừng dùng `length()` hoặc `chars().count()` như thể đó là phép đếm ký tự người dùng nhìn thấy.

### 7.2. subSequence phải tuân thủ chỉ số và nội dung

Với `subSequence(start, end)`, `start` được tính vào kết quả còn `end` được loại ra. Điều kiện đầu vào hợp lệ là `0 <= start <= end <= length()`. Kết quả phải có độ dài `end - start` và chứa đúng các ký tự tương ứng.

Trong `TextSlice`, `value.substring(start, end)` xử lý điều kiện này, sau đó `new TextSlice(...)` bọc lại bằng kiểu tùy biến. Một lớp sử dụng bộ đệm hoặc chỉ số offset riêng phải tự bảo đảm hành vi tương đương.

### 7.3. toString, equals và so sánh nội dung

Hợp đồng `toString()` yêu cầu tạo biểu diễn `String` chứa đúng dãy ký tự; không nên mặc định dùng cách `Object.toString()` dạng tên lớp và hash nếu nó không mang nội dung văn bản.

Tuy nhiên, `CharSequence` **không quy định một cơ chế `equals()/hashCode()` chung theo nội dung** cho mọi triển khai. Ví dụ `"abc".equals(new TextSlice("abc"))` là `false`, trong khi `"abc".contentEquals(new TextSlice("abc"))` là `true`. Khi cần so sánh nội dung với chuỗi, dùng API có hợp đồng phù hợp; nếu lớp tùy biến định nghĩa value equality thì phải định nghĩa `equals` và `hashCode` nhất quán.

### 7.4. Không mặc định rằng CharSequence bất biến

`CharSequence` không bắt mọi triển khai phải bất biến hay thread-safe. `String` là bất biến, còn các dạng bộ đệm như `StringBuilder` có thể thay đổi. Vì thế một triển khai tùy biến cần quyết định rõ có lưu bản sao, lưu tham chiếu đến bộ đệm hay tính toán trên một view. Thay đổi dữ liệu nền trong lúc dùng `chars()` / `codePoints()` có thể khiến kết quả không ổn định; không nên giả định các stream là snapshot của nội dung trước đó.

## 8. Lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| `inherits unrelated defaults for isEmpty()` khi biên dịch | Hai default cùng chữ ký từ các interface độc lập | Thêm override `isEmpty()` ở lớp/subinterface, chọn hành vi phù hợp hợp đồng. |
| `CharSequence.super.isEmpty()` báo lỗi | Interface không phải superinterface trực tiếp phù hợp, hoặc cách gọi nằm sai ngữ cảnh | Kiểm tra quan hệ `implements/extends`; có thể trả `length() == 0`. |
| `isEmpty()` trả `true` cho chuỗi toàn dấu cách | Đang nhầm rỗng với trắng; có thể là override sai hợp đồng | Với `CharSequence`, rỗng là `length() == 0`; nếu cần kiểm tra trắng, dùng API thích hợp cho `String`. |
| `subSequence(1, 3)` trả sai ký tự | Dùng chỉ số cuối bao gồm thay vì loại trừ | Thực hiện đoạn `[start, end)` và kiểm tra phạm vi. |
| `charAt()` chia ký tự emoji thành hai phần | Một code point Unicode có thể chiếm hai `char` | Dùng `codePoints()` khi mục tiêu là Unicode code point. |
| Gọi `equals` giữa `String` và lớp tùy biến trả `false` dù chữ giống nhau | `equals` không phải hợp đồng chung của `CharSequence` | Dùng `String.contentEquals(CharSequence)` khi cần so nội dung. |
| Default method của interface mới làm mã nguồn cũ biên dịch lỗi | Tên/chữ ký trùng với default sẵn có từ một interface khác | Rà lại các interface đang kết hợp, override rõ ràng và biên dịch trên JDK mục tiêu. |
| Thử đổi thứ tự `implements` để xử lý xung đột | Thứ tự khai báo không quyết định default thắng | Chọn phương thức bằng override; dùng `InterfaceName.super.method()` khi hợp lệ. |

## 9. Bài tập kiểm tra hiểu biết

1. Một `CharSequence` có `length() == 0`. Nếu không override, `isEmpty()` trả gì? **`true`**.
2. Nếu một interface khác định nghĩa `default boolean isEmpty()`, khai báo `class X implements CharSequence, OtherEmpty` nhưng không giải quyết xung đột có hợp lệ? **Không**, nếu cả hai default là độc lập và cùng chữ ký.
3. Cần giữ hành vi rỗng của `CharSequence` trong lớp trực tiếp triển khai cả hai interface: viết gì? **`@Override public boolean isEmpty() { return CharSequence.super.isEmpty(); }`** hoặc `return length() == 0;`.
4. `"abc".equals(custom)` và `"abc".contentEquals(custom)` có bắt buộc cùng kết quả không? **Không**. `contentEquals` so ký tự; `equals` phụ thuộc hợp đồng kiểu.
5. Với `CharSequence` chứa một chữ ASCII và một code point ngoài BMP, `length()` thường bao nhiêu? **3 UTF-16 code unit**; `codePoints().count()` bằng **2**.

## 10. Tài liệu chuẩn hiện hành

- [Java SE 26 — CharSequence API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/CharSequence.html): `length`, `charAt`, `subSequence`, `toString`, các default `chars`, `codePoints`, `isEmpty` (`Since: 15`).
- [Java Language Specification — `9.4.1.3, Inheriting Methods with Override-Equivalent Signatures](https://docs.oracle.com/javase/specs/jls/se26/html/jls-9.html#jls-9.4.1.3): trường hợp giao diện kế thừa phương thức trùng chữ ký.
- [Java Language Specification — `8.4.8, Inheritance, Overriding, and Hiding](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.4.8): nguyên tắc ưu tiên phương thức của lớp và quy tắc override.
- [dev.java — Overriding and Hiding Methods](https://dev.java/learn/inheritance/overriding/): diễn giải thực hành về interface default methods và xung đột.

Các nội dung và ví dụ ở đây sử dụng **cú pháp, API và quy tắc kế thừa còn áp dụng trên Java hiện đại**, tập trung vào mốc Java 15 khi `CharSequence.isEmpty()` trở thành default method chính thức.