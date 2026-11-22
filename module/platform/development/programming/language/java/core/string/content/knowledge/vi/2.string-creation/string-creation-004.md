# Tạo String từ char[] hoặc một vùng của mảng trong Java

Trong Java, `char[]` là mảng chứa các giá trị `char` có thể thay đổi; `String` là chuỗi ký tự **bất biến** (immutable). Khi đã có dữ liệu ở dạng `char[]` và cần một chuỗi để hiển thị, so sánh, truyền cho API hoặc lưu kết quả xử lý, có thể tạo `String` từ **toàn bộ mảng** hoặc từ **một đoạn liên tiếp** của mảng. Hai constructor cần nắm vững là `new String(char[])` và `new String(char[], int offset, int count)`.

## 1. Hai cách tạo chuỗi

| Cú pháp | Lấy ký tự nào? | Kết quả |
| --- | --- | --- |
| `new String(char[] value)` | Toàn bộ phần tử từ chỉ số `0` đến `value.length - 1` | Một `String` có nội dung tương ứng với toàn bộ mảng tại thời điểm tạo |
| `new String(char[] value, int offset, int count)` | `count` phần tử liên tiếp bắt đầu tại `offset` | Một `String` có nội dung của đúng vùng được chọn |

Với constructor thứ hai:

- `value`: mảng `char[]` nguồn.
- `offset`: **chỉ số bắt đầu**, tính từ 0, bao gồm phần tử tại chỉ số đó.
- `count`: **số phần tử cần lấy**, không phải chỉ số kết thúc.
- Vùng được sao chép có dạng **[offset, offset + count)**: lấy từ `offset` đến `offset + count - 1`. Dấu `)` nghĩa là không lấy phần tử ở chỉ số `offset + count`.

Ví dụ với mảng `{'J', 'a', 'v', 'a', ' ', '1', '7'}`:

| Chỉ số | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Giá trị | J | a | v | a | khoảng trắng | 1 | 7 |

`new String(chars, 0, 4)` lấy bốn ký tự tại chỉ số 0, 1, 2, 3 nên cho `"Java"`. `new String(chars, 5, 2)` lấy hai ký tự tại chỉ số 5, 6 nên cho `"17"`.

## 2. Ví dụ Java 17+ chạy độc lập

Lưu chương trình sau vào tệp **CharArrayToStringDemo.java**:

~~~java
public class CharArrayToStringDemo {
    public static void main(String[] args) {
        char[] chars = {'J', 'a', 'v', 'a', ' ', '1', '7'};

        String whole = new String(chars);
        String word = new String(chars, 0, 4);
        String version = new String(chars, 5, 2);
        String empty = new String(chars, chars.length, 0);

        System.out.println("whole = " + whole);
        System.out.println("word = " + word);
        System.out.println("version = " + version);
        System.out.println("empty length = " + empty.length());

        chars[0] = 'X'; // Thay đổi mảng sau khi đã tạo String
        System.out.println("chars[0] = " + chars[0]);
        System.out.println("whole sau sua mang = " + whole);
        System.out.println("word sau sua mang = " + word);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 CharArrayToStringDemo.java
java CharArrayToStringDemo
~~~

Kết quả chuẩn:

~~~text
whole = Java 17
word = Java
version = 17
empty length = 0
chars[0] = X
whole sau sua mang = Java 17
word sau sua mang = Java
~~~

Điểm then chốt: các constructor **sao chép nội dung ký tự** tại thời điểm gọi. Thay `chars[0]` từ `'J'` thành `'X'` chỉ thay đổi mảng; `whole` và `word` vẫn giữ nội dung cũ. Cũng không thể sửa một ký tự trong `String` bằng phép gán như `whole.charAt(0) = 'X'` vì `charAt()` trả về giá trị, không phải vị trí có thể gán. Khi cần tạo chuỗi mới từ mảng đã sửa, hãy gọi constructor lần nữa.

## 3. Kiểm tra vị trí bắt đầu và độ dài

Đặt `n = value.length`. Một vùng hợp lệ phải thỏa mãn đồng thời:

- `offset >= 0`;
- `count >= 0`;
- `offset <= n - count` (tương đương chọn vùng không vượt quá cuối mảng; dạng phép trừ còn tránh tràn số khi tự kiểm tra trên `int`).

Nếu `offset` âm, `count` âm hoặc vùng vượt mảng, `new String(value, offset, count)` ném **`IndexOutOfBoundsException`**. Khi mảng `value` là `null`, thao tác không thể đọc ký tự và ném **`NullPointerException`**. Đây là các lỗi runtime; constructor không tự cắt vùng về giới hạn hợp lệ.

Một số trường hợp biên cần phân biệt:

| `value.length` | `offset` | `count` | Hợp lệ? | Ý nghĩa |
| ---: | ---: | ---: | --- | --- |
| 3 | 0 | 3 | Có | Lấy toàn bộ mảng |
| 3 | 1 | 2 | Có | Lấy hai ký tự cuối |
| 3 | 0 | 0 | Có | Chuỗi rỗng |
| 3 | 3 | 0 | Có | Chuỗi rỗng bắt đầu ngay sau ký tự cuối |
| 3 | 4 | 0 | Không | `offset` vượt quá `length` |
| 3 | 2 | 2 | Không | Muốn lấy đến chỉ số 3, vượt mảng |
| 3 | -1 | 1 | Không | `offset` âm |
| 3 | 1 | -1 | Không | `count` âm |

Có thể kiểm tra hành vi bằng chương trình độc lập **RangeValidationDemo.java**:

~~~java
public class RangeValidationDemo {
    public static void main(String[] args) {
        char[] data = {'a', 'b', 'c'};

        System.out.println("valid = " + new String(data, 1, 2));
        System.out.println("empty = " + new String(data, 3, 0).length());

        try {
            new String(data, 2, 2);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("out of range");
        }

        try {
            new String((char[]) null);
        } catch (NullPointerException ex) {
            System.out.println("null array");
        }
    }
}
~~~

Chạy `javac -encoding UTF-8 RangeValidationDemo.java` rồi `java RangeValidationDemo`:

~~~text
valid = bc
empty = 0
out of range
null array
~~~

Cú pháp ép kiểu `(char[]) null` trong ví dụ giúp Java chọn chính xác constructor nhận `char[]`; lời gọi `new String(null)` thiếu kiểu cụ thể là **mơ hồ** vì `String` có nhiều constructor nhận kiểu tham chiếu.

Khi các chỉ số xuất phát từ đầu vào hoặc thao tác tính toán, nên kiểm tra giới hạn trước khi tạo chuỗi. Chẳng hạn, hàm dưới đây trả về kết quả chỉ khi phạm vi hợp lệ:

~~~java
static String take(char[] source, int offset, int count) {
    if (source == null) {
        throw new IllegalArgumentException("source must not be null");
    }
    if (offset < 0 || count < 0 || offset > source.length - count) {
        throw new IllegalArgumentException("invalid slice");
    }
    return new String(source, offset, count);
}
~~~

Đây là **đoạn phương thức minh họa**, cần đặt bên trong một lớp Java để biên dịch. Kiểu ngoại lệ trong ví dụ là lựa chọn của hàm `take` để báo lỗi đầu vào; constructor của `String` có các ngoại lệ như mô tả phía trên.

## 4. Sao chép, tính bất biến và vòng đời dữ liệu

`char[]` là cấu trúc có thể sửa tại chỗ: `chars[i] = 'x'` làm thay đổi mảng. `String` đã tạo không thay đổi giá trị sau đó. Hai constructor `char[]` sao chép các ký tự được chọn; chúng không cung cấp “cửa sổ sống” liên kết với mảng gốc. Vì thế:

1. Sửa mảng **trước** khi tạo chuỗi sẽ ảnh hưởng đến nội dung chuỗi được tạo sau đó.
2. Sửa mảng **sau** khi tạo chuỗi sẽ **không** ảnh hưởng đến chuỗi cũ.
3. Hai lần `new String(chars)` tạo hai đối tượng `String` riêng dù nội dung có thể bằng nhau; so sánh giá trị chuỗi bằng `equals()`, không dựa vào `==`.
4. Không nên suy ra chi tiết biểu diễn nội bộ của `String` (như kích thước mảng nội bộ) từ constructor; API chỉ bảo đảm nội dung và tính bất biến.

Với mật khẩu hoặc dữ liệu nhạy cảm, chuyển `char[]` thành `String` tạo thêm một bản nội dung bất biến mà chương trình không thể xóa từng ký tự theo yêu cầu; hãy cân nhắc yêu cầu bảo mật và API nhận dữ liệu đầu vào trước khi tạo chuỗi.

## 5. Lưu ý Unicode: `char` không luôn bằng một ký tự người đọc thấy

Mỗi `char` Java biểu diễn **một đơn vị mã UTF-16 (16 bit)**. Một ký tự Unicode nằm ngoài Basic Multilingual Plane (chẳng hạn nhiều emoji) cần **hai `char`**, gọi là một *surrogate pair*. Vì vậy `offset` và `count` đếm số phần tử `char[]`, **không đếm số ký tự hiển thị hay code point**.

Ví dụ dưới đây là **đoạn lệnh đặt bên trong một phương thức Java**:

~~~java
char[] units = "A😀B".toCharArray();
System.out.println(units.length); // 4: A, high surrogate, low surrogate, B

String emoji = new String(units, 1, 2);
System.out.println(emoji.length()); // 2 don vi ma UTF-16
System.out.println(emoji.codePointCount(0, emoji.length())); // 1

String broken = new String(units, 1, 1); // Chi lay high surrogate
System.out.println(broken.length()); // 1, nhung khong la emoji hoan chinh
~~~

Các con số được in ra tương ứng lần lượt là `4`, `2`, `1`, `1`. Vùng `[1, 3)` giữ nguyên cặp surrogate của emoji; vùng `[1, 2)` cắt đôi cặp, tạo chuỗi chứa surrogate lẻ. Khi xử lý văn bản đa ngôn ngữ, phải xác định chỉ số theo đơn vị mã UTF-16 và tránh cắt giữa cặp surrogate. Nếu ứng dụng cần chọn theo **code point**, hãy dùng các API như `codePointCount()`, `offsetByCodePoints()` hoặc thao tác trên `codePoints()` rồi mới xác định đoạn cần lấy. Cắt đúng ranh giới code point cũng chưa bảo đảm giữ nguyên mọi cụm ký tự hiển thị, ví dụ ký tự kèm dấu kết hợp.

**Phân biệt `char[]` với `byte[]`:** constructor nhận `char[]` không giải mã encoding. Với dữ liệu là byte, phải dùng cơ chế giải mã và chỉ định charset phù hợp, chẳng hạn `new String(bytes, StandardCharsets.UTF_8)`. Không ép byte thành char một cách tùy tiện để thay cho decoding.

## 6. Cách viết tương đương và lựa chọn sử dụng

Các lời gọi sau tạo chuỗi có cùng **giá trị nội dung** khi đầu vào hợp lệ:

~~~java
char[] data = {'H', 'e', 'l', 'l', 'o'};
String a = new String(data);
String b = String.valueOf(data);
String c = String.copyValueOf(data);

String partA = new String(data, 1, 3);
String partB = String.valueOf(data, 1, 3);
String partC = String.copyValueOf(data, 1, 3);
~~~

Kết quả: `a`, `b`, `c` cùng có giá trị `"Hello"`; `partA`, `partB`, `partC` cùng có giá trị `"ell"`. Những lời gọi trong nhóm tạo chuỗi từ `char[]` đều lấy nội dung tại thời điểm gọi. Có thể sử dụng `new String(chars, offset, count)` khi muốn diễn đạt rõ việc tạo một phần mảng; `String.valueOf(...)` cũng là lựa chọn quen thuộc.

Không nhầm với:

- `Arrays.toString(data)`: tạo dạng hiển thị phần tử mảng như `"[H, e, l, l, o]"`, **khác** `"Hello"`.
- `new String(data, 1, 4)`: lấy **bốn** ký tự từ chỉ số 1, tức `"ello"`; không phải lấy từ chỉ số 1 **đến** chỉ số 4 theo nghĩa điểm cuối.
- `new String(data, 0, data.length + 1)`: vượt vùng hợp lệ và gây ngoại lệ.
- `StringBuilder`: hữu ích khi cần nối/thay đổi ký tự liên tục trước khi tạo kết quả `String`; nó không bắt buộc cho việc sao chép một đoạn `char[]` đã có sẵn.

## 7. Tình huống thực tế: chỉ lấy phần dữ liệu đã đọc

Khi đọc vào bộ đệm `char[]` từ một `Reader`, số ký tự thực sự được đọc thường nhỏ hơn kích thước toàn bộ bộ đệm. Với đoạn mã **đặt trong phương thức có quyền ném `IOException`** và biến `reader` là một `java.io.Reader` đang mở:

~~~java
char[] buffer = new char[1024];
int count = reader.read(buffer);
if (count != -1) {
    String chunk = new String(buffer, 0, count);
    System.out.println("Read " + chunk.length() + " UTF-16 code units");
}
~~~

`reader.read(buffer)` trả về số đơn vị `char` đã được ghi vào buffer hoặc `-1` nếu hết dữ liệu; dùng `count` để chỉ lấy phần có dữ liệu. Nếu dùng `new String(buffer)`, kết quả có thể chứa các phần tử chưa được đọc hoặc còn sót từ lần đọc trước. Nếu muốn ghép toàn bộ nội dung đọc qua nhiều lần, hãy tích lũy bằng `StringBuilder` hoặc cơ chế xử lý dòng/stream phù hợp. Với dữ liệu Unicode, cần chú ý ranh giới surrogate khi xử lý độc lập từng chunk.

## 8. Tự kiểm tra

**Câu 1.** Cho `char[] a = {'0', '1', '2', '3', '4'};`, `new String(a, 2, 2)` trả về gì?

Đáp án: `"23"`, vì lấy các phần tử chỉ số 2 và 3.

**Câu 2.** Mảng có độ dài 5. `new String(a, 5, 0)` và `new String(a, 5, 1)` khác nhau thế nào?

Đáp án: lời gọi đầu hợp lệ và tạo chuỗi rỗng; lời gọi sau yêu cầu phần tử ở chỉ số 5 (không tồn tại), nên gây `IndexOutOfBoundsException`.

**Câu 3.** Vì sao tạo `String` rồi sửa `char[]` không thay đổi giá trị `String`?

Đáp án: constructor đã sao chép nội dung mảng, còn `String` là kiểu bất biến.

**Câu 4.** `count = 1` có luôn nghĩa là một ký tự Unicode hoàn chỉnh?

Đáp án: không. `count` tính đơn vị mã UTF-16; một code point bổ sung có thể cần hai `char`, và một cụm ký tự hiển thị có thể gồm nhiều code point.

## Tài liệu tham khảo

- [Java SE 17 — String constructors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): mô tả chính thức về sao chép mảng, `offset`, `count` và ngoại lệ.
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): cách Java biểu diễn Unicode code point và surrogate pair.
