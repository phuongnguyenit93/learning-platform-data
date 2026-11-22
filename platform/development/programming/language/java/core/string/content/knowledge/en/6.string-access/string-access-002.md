# `String.charAt()` và điều kiện chỉ số hợp lệ trong Java

## 1. Mục tiêu bài học

`String.charAt(int index)` là cách đọc **một đơn vị mã UTF-16 (`char`)** tại một vị trí trong `String`. Để dùng đúng, cần nắm quy tắc chỉ số bắt đầu từ `0`, điều kiện `0 <= index < length()`, cách xử lý chuỗi rỗng và chỉ số vượt biên, cùng giới hạn của `charAt` đối với ký tự Unicode cần hai đơn vị UTF-16.

Sau bài này, bạn có thể:

- Xác định chỉ số đầu/cuối hợp lệ trong một `String` và viết vòng lặp không vượt biên.
- Giải thích `String.length()`, `charAt(0)` và `charAt(length() - 1)` hoạt động thế nào với chuỗi rỗng và không rỗng.
- Kiểm tra đầu vào trước khi truy cập hoặc chủ động xử lý ngoại lệ đúng trường hợp.
- Phân biệt `charAt` với `codePointAt` khi chuỗi chứa emoji, ký tự bổ sung hoặc surrogate pair.

## 2. Cú pháp và hợp đồng của `charAt`

Phương thức của `java.lang.String`:

~~~java
public char charAt(int index)
~~~

- **Đầu vào:** `index` là **chỉ số của một code unit UTF-16** trong chuỗi.
- **Đầu ra:** một giá trị `char` tại vị trí đó. Một `char` rộng 16 bit, không nhất thiết đại diện cho một Unicode code point hoàn chỉnh.
- **Chỉ số hợp lệ:** với chuỗi `s` có độ dài `n = s.length()`, chỉ số `index` phải thỏa **`0 <= index && index < n`**.
- **Vượt biên:** API quy định ném `IndexOutOfBoundsException`; ở triển khai `String` của Java thông dụng, ngoại lệ thực tế là lớp con `StringIndexOutOfBoundsException`.
- **Tham chiếu null:** gọi `s.charAt(index)` khi `s == null` gây `NullPointerException` trước khi có thể xét nội dung chuỗi.

Ví dụ:

~~~java
String s = "Java";  // length() == 4
char a = s.charAt(0); // 'J'
char b = s.charAt(1); // 'a'
char c = s.charAt(2); // 'v'
char d = s.charAt(3); // 'a'
~~~

Biểu diễn:

~~~text
Chuỗi:     J   a   v   a
Chỉ số:    0   1   2   3
length():  4
Biên hợp lệ: [0, 4) = 0, 1, 2, 3
~~~

Ký hiệu `[0, 4)` nghĩa là **bao gồm `0` nhưng không bao gồm `4`**. `length()` là độ dài, **không phải chỉ số cuối**.

| Biểu thức trên `"Java"` | Kết quả | Vì sao? |
| --- | --- | --- |
| `s.charAt(0)` | `'J'` | Chỉ số đầu hợp lệ |
| `s.charAt(3)` | `'a'` | Chỉ số cuối hợp lệ |
| `s.charAt(s.length() - 1)` | `'a'` | `4 - 1 = 3` |
| `s.charAt(-1)` | Ngoại lệ vượt biên | Chỉ số âm |
| `s.charAt(4)` | Ngoại lệ vượt biên | `4 == length()` |
| `s.charAt(100)` | Ngoại lệ vượt biên | Vượt xa cuối chuỗi |

**Công thức trọng tâm:**

~~~java
boolean valid = index >= 0 && index < s.length();
~~~

Điều kiện này áp dụng khi `s != null`. Không chỉ kiểm tra `index < s.length()`, vì giá trị âm vẫn lọt qua; cũng không dùng `index <= s.length()`, vì `length()` đã nằm ngoài phạm vi.

## 3. Phần tử đầu, phần tử cuối và chuỗi rỗng

Với một `String` **không rỗng**:

~~~java
String name = "Java";
char first = name.charAt(0);
char last = name.charAt(name.length() - 1);
~~~

Hai phép đọc trên chỉ an toàn khi `name.length() > 0`. Nếu `name` là `""`:

- `name.length()` bằng `0`.
- **Không tồn tại chỉ số hợp lệ** vì không có số nguyên `i` thỏa `0 <= i < 0`.
- `name.charAt(0)` vượt biên.
- `name.charAt(name.length() - 1)` trở thành `name.charAt(-1)` và cũng vượt biên.

Ví dụ kiểm tra trước khi lấy ký tự cuối:

~~~java
String text = "";

if (!text.isEmpty()) {
    char last = text.charAt(text.length() - 1);
    System.out.println(last);
} else {
    System.out.println("Chuỗi rỗng: không có ký tự cuối");
}
~~~

`String.isEmpty()` tương đương kiểm tra `length() == 0`. Nếu biến có thể `null`, `text.isEmpty()` tự nó cũng gây `NullPointerException`; có thể dùng `text != null && !text.isEmpty()` hoặc đặt yêu cầu không nhận null từ đầu theo hợp đồng của hàm.

### Chuỗi chứa khoảng trắng có phải rỗng không?

~~~java
String spaces = "   ";
System.out.println(spaces.length()); // 3
System.out.println(spaces.isEmpty()); // false
~~~

`"   "` không rỗng: có ba code unit là dấu cách, nên `charAt(0)` hợp lệ. Nếu bài toán muốn biết chuỗi *chỉ có khoảng trắng* thì đó là câu hỏi khác; có thể xem xét `isBlank()`, nhưng đừng dùng `isBlank()` thay cho điều kiện chỉ số hợp lệ. Chuỗi trống và chuỗi toàn khoảng trắng là hai trường hợp khác nhau.

## 4. Vòng lặp truy cập từng `char` đúng biên

Mẫu vòng lặp cơ bản:

~~~java
String text = "Java";

for (int i = 0; i < text.length(); i++) {
    char current = text.charAt(i);
    System.out.println(i + ": " + current);
}
~~~

`stdout`:

~~~text
0: J
1: a
2: v
3: a
~~~

Điều kiện `i < text.length()` dừng vòng lặp trước khi `i == 4`. Đối với chuỗi rỗng, vòng lặp không chạy lần nào, nên không gọi `charAt` với chỉ số sai.

Mẫu lỗi phổ biến:

~~~java
// SAI: nếu text = "Java", lần cuối sẽ gọi charAt(4).
for (int i = 0; i <= text.length(); i++) {
    char current = text.charAt(i);
}
~~~

Sửa `<=` thành `<`. Tương tự, nếu duyệt ngược, khởi đầu từ `length() - 1` và dừng ở `i >= 0`:

~~~java
for (int i = text.length() - 1; i >= 0; i--) {
    System.out.println(text.charAt(i));
}
~~~

Mẫu duyệt ngược theo `char` này cũng an toàn với chuỗi rỗng vì khi đó `i` ban đầu là `-1`, điều kiện `i >= 0` sai ngay. Tuy nhiên cả hai vòng lặp đều duyệt **UTF-16 code unit**; với supplementary Unicode code point, chúng đi qua hai nửa surrogate riêng.

## 5. Ví dụ đầy đủ Java 17+: hợp lệ, vượt biên và Unicode

Lưu tệp **`CharAtBoundsDemo.java`**:

~~~java
public class CharAtBoundsDemo {
    public static void main(String[] args) {
        String word = "Java";
        System.out.println("length=" + word.length());
        System.out.println("first=" + word.charAt(0));
        System.out.println("last=" + word.charAt(word.length() - 1));

        for (int i = 0; i < word.length(); i++) {
            System.out.println("charAt[" + i + "]=" + word.charAt(i));
        }

        printIfValid(word, 2);
        printIfValid(word, 4);
        printIfValid("", 0);

        showInvalid(word, -1);
        showInvalid(word, word.length());
        showInvalid("", 0);

        String mixed = "A" + Character.toString(0x1F600) + "B";
        System.out.println("mixed.length=" + mixed.length());
        for (int i = 0; i < mixed.length(); i++) {
            System.out.printf("mixed[%d]=U+%04X%n", i, (int) mixed.charAt(i));
        }
        System.out.printf("codePointAt(1)=U+%X%n", mixed.codePointAt(1));
        System.out.println("codePointCount="
                + mixed.codePointCount(0, mixed.length()));
    }

    private static void printIfValid(String text, int index) {
        if (index >= 0 && index < text.length()) {
            System.out.println("safe[" + index + "]=" + text.charAt(index));
        } else {
            System.out.println("out of range: index=" + index
                    + ", length=" + text.length());
        }
    }

    private static void showInvalid(String text, int index) {
        try {
            text.charAt(index);
        } catch (StringIndexOutOfBoundsException e) {
            System.out.println("caught: " + e.getClass().getSimpleName()
                    + " (index=" + index + ", length=" + text.length() + ")");
        }
    }
}
~~~

Chạy trên Java 17+:

~~~bash
javac -encoding UTF-8 CharAtBoundsDemo.java
java CharAtBoundsDemo
~~~

Kết quả `stdout` đã đối chiếu bằng cách biên dịch và chạy chương trình:

~~~text
length=4
first=J
last=a
charAt[0]=J
charAt[1]=a
charAt[2]=v
charAt[3]=a
safe[2]=v
out of range: index=4, length=4
out of range: index=0, length=0
caught: StringIndexOutOfBoundsException (index=-1, length=4)
caught: StringIndexOutOfBoundsException (index=4, length=4)
caught: StringIndexOutOfBoundsException (index=0, length=0)
mixed.length=4
mixed[0]=U+0041
mixed[1]=U+D83D
mixed[2]=U+DE00
mixed[3]=U+0042
codePointAt(1)=U+1F600
codePointCount=3
~~~

**Phân tích kết quả:**

1. `"Java"` có `length() == 4` và index `0..3`, nên lấy ký tự đầu/cuối thành công.
2. `printIfValid` kiểm tra cả hai cận trước khi truy cập; index `4` và index `0` của chuỗi rỗng chỉ sinh ra thông báo, không gây ngoại lệ.
3. `showInvalid` cố ý gọi ba chỉ số sai để minh họa lớp ngoại lệ từ `String.charAt`. Ví dụ bắt ngoại lệ **chỉ để trình diễn và thử biên**, không có nghĩa nên lạm dụng ngoại lệ trong mọi vòng lặp thông thường.
4. `mixed` chứa `"A"`, một emoji `U+1F600` và `"B"`. Emoji cần **hai `char` UTF-16**: `U+D83D` và `U+DE00`. Do đó `mixed.length()` bằng `4`, mặc dù có **ba code point**.
5. `charAt(1)` và `charAt(2)` trả về hai code unit của emoji; `codePointAt(1)` trả về code point đầy đủ `0x1F600`.

## 6. Ngoại lệ: lúc nào kiểm tra, lúc nào bắt?

Có hai cách kiểm soát chỉ số, tùy hợp đồng API và dữ liệu đầu vào.

### Cách A — kiểm tra trước khi đọc

Thích hợp khi index đến từ người dùng, cấu hình hoặc dữ liệu ngoài:

~~~java
static boolean isValidCharIndex(String text, int index) {
    return text != null && index >= 0 && index < text.length();
}
~~~

Sử dụng:

~~~java
String text = "Java";
int index = 2;

if (isValidCharIndex(text, index)) {
    System.out.println(text.charAt(index));
} else {
    System.out.println("Không thể truy cập chỉ số yêu cầu");
}
~~~

Ở đây kết quả hợp lệ in `v`. Điều kiện `text != null` đứng đầu và toán tử `&&` **short-circuit** giúp không gọi `length()` trên `null`. Hàm kiểm tra phải phản ánh chính sách nghiệp vụ: khi `null` là lỗi lập trình, có thể chọn chặn ngay bằng `Objects.requireNonNull` thay vì âm thầm coi như index không hợp lệ.

### Cách B — dựa vào hợp đồng và cho phép ném ngoại lệ

Nếu một phương thức yêu cầu người gọi luôn cung cấp index hợp lệ, có thể gọi trực tiếp:

~~~java
static char requiredCharAt(String text, int index) {
    return text.charAt(index);
}
~~~

Nếu truyền index sai, ngoại lệ làm lỗi hiển lộ ở nơi phát sinh. Khi cần xử lý lỗi do **đầu vào không tin cậy**, kiểm tra trước thường giúp trả về thông báo có ý nghĩa. Tránh dùng `try/catch` cho mỗi lần duyệt trong một vòng lặp mà bạn đã biết giới hạn qua `length()`.

**Phân biệt hai dạng lỗi:**

| Trường hợp | Nguyên nhân | Ngoại lệ thường thấy |
| --- | --- | --- |
| `"Java".charAt(-1)` | Index âm | `StringIndexOutOfBoundsException` |
| `"Java".charAt(4)` | Index bằng `length()` | `StringIndexOutOfBoundsException` |
| `"".charAt(0)` | Chuỗi rỗng, không có index hợp lệ | `StringIndexOutOfBoundsException` |
| `((String) null).charAt(0)` | Gọi phương thức qua tham chiếu `null` | `NullPointerException` |

Bản thân `String` không tự đổi index ngoài biên thành ký tự mặc định, không trả về `null` và không “quay vòng” index âm. Nếu muốn cơ chế giá trị mặc định, ứng dụng phải định nghĩa rõ.

## 7. Unicode: một chỉ số hợp lệ vẫn có thể nằm giữa emoji

`charAt(index)` đọc đúng **một UTF-16 code unit**, dù chỉ số hợp lệ. Nhiều code point ngoài BMP (như 😀) được mã hóa bởi cặp **high surrogate** rồi **low surrogate**, nên đọc từng `char` có thể lấy riêng một nửa cặp.

```java
String text = "A" + Character.toString(0x1F600) + "B";
System.out.printf("%04X%n", (int) text.charAt(1)); // D83D
System.out.printf("%04X%n", (int) text.charAt(2)); // DE00
System.out.printf("%X%n", text.codePointAt(1));    // 1F600
```

Cả index 1 và 2 đều hợp lệ theo `charAt` nhưng không tương đương hai Unicode code point. `codePointAt(1)` nhận biết cặp surrogate vì bắt đầu ở high surrogate; `codePointAt(2)` bắt đầu ở low surrogate nên trả về `0xDE00`, không tự ghép ngược về emoji đầy đủ.

Khi cần duyệt Unicode code point, hãy bắt đầu tại ranh giới phù hợp và tiến theo `Character.charCount(codePoint)` hoặc dùng `codePoints()`. Bài tiếp theo **codePointAt và codePointBefore** sẽ đi sâu vào cách đọc code point từ hai hướng. Với dấu kết hợp và emoji nối nhiều thành phần, ngay cả một code point cũng chưa chắc là một ký tự hiển thị trọn vẹn.
## 8. `charAt`, `substring` và lỗi cắt ngang surrogate pair

`substring(beginIndex, endIndex)` dùng hai **chỉ số UTF-16**, với `beginIndex` được bao gồm và `endIndex` không được bao gồm. Điều kiện hợp lệ tương ứng là `0 <= beginIndex <= endIndex <= length()`. Khác `charAt`, `substring(length(), length())` là **chuỗi rỗng hợp lệ** vì không lấy phần tử nào.

Nhưng index **hợp lệ về số học** chưa chắc là ranh giới code point. Với `"A😀B"`, lệnh sau không gây lỗi index, nhưng cắt giữa high và low surrogate:

~~~java
String text = "A" + Character.toString(0x1F600) + "B";
String broken = text.substring(0, 2); // 'A' + high surrogate lẻ
~~~

Không nên coi `broken` là “hai ký tự Unicode đầu” hoàn chỉnh. Nếu muốn hai **code point** đầu:

~~~java
int end = text.offsetByCodePoints(0, 2); // 3, UTF-16 index
String firstTwoCodePoints = text.substring(0, end); // "A😀"
~~~

Hợp đồng `charAt` chỉ bảo đảm đọc một `char`; còn hợp đồng hiển thị/trao đổi Unicode có thể cần thêm kiểm tra surrogate pair và ranh giới code point.

## 9. Lỗi thường gặp và cách sửa

1. **Dùng `<= length()` trong vòng lặp.** Với `charAt`, cận trên là **nhỏ hơn** `length()`. Viết `for (int i = 0; i < s.length(); i++)`.
2. **Gọi `charAt(length())` để lấy ký tự cuối.** Index cuối là `length() - 1`, nhưng trước đó phải bảo đảm chuỗi không rỗng.
3. **Chỉ kiểm tra `index < length()`.** Index âm vẫn thỏa điều kiện; thêm `index >= 0`.
4. **Nhầm `null` với `""`.** Chuỗi rỗng là một đối tượng `String` hợp lệ với `length() == 0`; `null` là không có đối tượng để gọi phương thức.
5. **Cho rằng `charAt(i)` luôn đọc nguyên một ký tự Unicode.** Với supplementary code point, mỗi lần chỉ lấy một nửa surrogate; chọn `codePointAt` và tiến theo `Character.charCount` nếu cần đọc code point.
6. **Dùng số code point như thể là index UTF-16.** `codePointCount` trả số lượng, không chuyển đổi tự động sang vị trí `charAt`. Dùng `offsetByCodePoints` để chuyển.
7. **Bắt `StringIndexOutOfBoundsException` trong từng bước xử lý dữ liệu vốn đã kiểm tra được.** Khi duyệt theo `length()`, hãy viết biên đúng. Chỉ bắt lỗi nếu thực sự có chiến lược khôi phục hoặc thông báo cho người gọi.
8. **Cho rằng index được bảo đảm hợp lệ trước khi chuỗi thay đổi.** `String` bất biến; tuy nhiên biến có thể được gán sang đối tượng `String` khác. Nếu kiểm tra `a` mà sau đó gọi `charAt` trên giá trị mới khác, điều kiện cũ không còn bảo đảm. Dùng cùng một tham chiếu chuỗi ổn định trong phép kiểm tra và truy cập.

## 10. Bài tập tự kiểm tra

**Câu 1.** Với `String s = "Core";`, index nào hợp lệ và `s.charAt(s.length())` trả về gì?

**Đáp án:** `0, 1, 2, 3` hợp lệ. `length()` bằng `4`; `charAt(4)` ném ngoại lệ vượt biên.

**Câu 2.** Vì sao `"".charAt(0)` và `"".charAt("".length() - 1)` đều sai?

**Đáp án:** `length() == 0`, không có index hợp lệ. Hai biểu thức truy cập lần lượt dùng `0` và `-1`.

**Câu 3.** Điều kiện kiểm tra `i < s.length()` đã đủ chưa?

**Đáp án:** chưa, vì `i` có thể âm. Cần `i >= 0 && i < s.length()` và `s != null` nếu dữ liệu có thể null.

**Câu 4.** `"A😀B".length()`, `charAt(1)` và `codePointAt(1)` khác nhau thế nào?

**Đáp án:** độ dài là **4 code unit UTF-16**; `charAt(1)` là **high surrogate U+D83D**; `codePointAt(1)` là **code point U+1F600** vì ghép high/low surrogate hợp lệ.

**Câu 5.** Cho `String s = "ab";`, vòng lặp `for (int i = 0; i <= s.length(); i++)` lỗi ở đâu?

**Đáp án:** lượt `i == 2` gọi `charAt(2)`, vượt cận trên. Sửa `<=` thành `<`.

**Câu 6.** `substring(s.length(), s.length())` có giống `charAt(s.length())` về hợp lệ không?

**Đáp án:** không. `substring` với hai biên bằng `length()` trả chuỗi rỗng hợp lệ; `charAt(length())` luôn vượt biên vì phải đọc một phần tử thật.

## 11. Tài liệu tham khảo

- [Oracle Java SE 17 — `String.charAt(int)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#charAt(int)): kiểu trả về, điều kiện index, ngoại lệ.
- [Oracle Java SE 17 — `String.length()`, `isEmpty()`, `codePointAt()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): độ dài UTF-16 và thao tác với code point.
- [Oracle Java SE 17 — `Character`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): `char`, surrogate pair, `charCount` và các phép kiểm tra.
- [Java Language Specification §3.10.5 — String Literals](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.5): literal chuỗi trong mã nguồn Java.

**Ghi nhớ:** `charAt(index)` chỉ hợp lệ khi **`0 <= index < s.length()`** và `s` không null. `String.length()` và `charAt` làm việc theo **code unit UTF-16**. Nếu bài toán thực sự yêu cầu **Unicode code point**, hãy dùng các API `codePoint...` với ranh giới index thích hợp.