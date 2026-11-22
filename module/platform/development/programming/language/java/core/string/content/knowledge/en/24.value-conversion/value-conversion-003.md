# String.copyValueOf và tạo chuỗi từ mảng ký tự trong Java

## 1. Bài toán: chuyển `char[]` thành `String`

Trong Java, `char[]` là **mảng các phần tử `char` có thể thay đổi**, còn `String` biểu diễn một chuỗi văn bản **bất biến (immutable)**. Khi xử lý văn bản bằng mảng ký tự, bạn thường cần tạo một `String` để trả về từ phương thức, so sánh, lưu trữ hoặc truyền cho API nhận chuỗi.

Ví dụ:

```java
char[] letters = {'J', 'a', 'v', 'a'};
String text = String.copyValueOf(letters);

System.out.println(text); // Java
```

`String.copyValueOf` là phương thức **static** của `java.lang.String`, chuyển một mảng ký tự hoặc một phần mảng thành chuỗi. Nó đặc biệt hữu ích khi đã có dữ liệu dạng `char[]` và muốn lấy đúng nội dung ký tự, thay vì biểu diễn của chính đối tượng mảng.

Bài học tập trung vào hai overload của `copyValueOf`, cách tạo chuỗi từ mảng, ngữ nghĩa sao chép, chọn phạm vi con và những lưu ý về Unicode/UTF-16.

## 2. Hai overload của String.copyValueOf

API cung cấp hai chữ ký:

```java
public static String copyValueOf(char[] data)
public static String copyValueOf(char[] data, int offset, int count)
```

| Tham số | Ý nghĩa |
| --- | --- |
| `data` | Mảng `char[]` chứa dữ liệu nguồn |
| `offset` | Chỉ số bắt đầu lấy trong mảng (đếm từ **0**) |
| `count` | **Số lượng** phần tử `char` cần lấy; không phải chỉ số kết thúc |

**Overload một tham số** lấy toàn bộ mảng:

```java
char[] data = {'H', 'e', 'l', 'l', 'o'};
String result = String.copyValueOf(data);

System.out.println(result); // Hello
```

**Overload ba tham số** lấy một đoạn liên tiếp từ `offset`, gồm `count` phần tử:

```java
char[] data = {'H', 'e', 'l', 'l', 'o', '-', 'J', 'a', 'v', 'a'};

String left = String.copyValueOf(data, 0, 5);
String right = String.copyValueOf(data, 6, 4);

System.out.println(left);  // Hello
System.out.println(right); // Java
```

Với `String.copyValueOf(data, 6, 4)`, các phần tử được lấy có chỉ số **6, 7, 8, 9**, tức đoạn nửa mở `[6, 10)`. Đối số thứ ba **không phải endIndex**. Nhầm `count` với vị trí kết thúc sẽ khiến bạn lấy sai đoạn hoặc gây ngoại lệ vượt phạm vi.

Cách tư duy rõ ràng là:

```text
data = ['H', 'e', 'l', 'l', 'o', '-', 'J', 'a', 'v', 'a']
index    0    1    2    3    4    5    6    7    8    9

copyValueOf(data, 6, 4)
                 |  +---- lấy 4 đơn vị char
                 +------- bắt đầu tại index 6

Kết quả: "Java"
```

## 3. Sao chép giá trị, không giữ một view đến mảng

Mảng `char[]` có thể được sửa sau khi tạo `String`. Chuỗi nhận được từ `copyValueOf` phải **không bị ảnh hưởng** bởi những lần thay đổi mảng sau đó.

```java
char[] source = {'c', 'o', 'd', 'e'};
String frozen = String.copyValueOf(source);

source[0] = 'm';

System.out.println(new String(source)); // mode
System.out.println(frozen);             // code
```

Điều này đúng vì `String` bất biến và API cam kết kết quả không thay đổi nếu mảng ký tự nguồn thay đổi. Không nên coi `String.copyValueOf(data)` là một **view có liên kết sống** với mảng.

Khi dùng overload chọn đoạn, ý nghĩa vẫn như vậy:

```java
char[] buffer = {'<', 'O', 'K', '>'};
String token = String.copyValueOf(buffer, 1, 2);

buffer[1] = 'N';

System.out.println(token);              // OK
System.out.println(new String(buffer)); // <NK>
```

Chiều ngược lại cũng độc lập về mặt giá trị: `String.toCharArray()` tạo mảng ký tự mới từ chuỗi. Sửa mảng đó không sửa `String`:

```java
String word = "Java";
char[] copy = word.toCharArray();

copy[0] = 'L';

System.out.println(word);             // Java
System.out.println(new String(copy)); // Lava
```

**Vì sao có ích?** Khi một bộ đệm ký tự được tái sử dụng để đọc dữ liệu tiếp theo, `copyValueOf` giúp lưu lại nội dung của lần đọc hiện tại dưới dạng `String` ổn định.

Lưu ý: API bảo đảm **ngữ nghĩa độc lập của kết quả**, chứ không yêu cầu bạn suy đoán chi tiết lưu trữ nội bộ của `String` trong từng phiên bản JDK.

## 4. copyValueOf, valueOf và new String(char[])

Có nhiều cách hợp lệ để tạo chuỗi từ mảng ký tự:

```java
char[] letters = {'J', 'a', 'v', 'a'};

String a = String.copyValueOf(letters);
String b = String.valueOf(letters);
String c = new String(letters);

System.out.println(a);                   // Java
System.out.println(a.equals(b));         // true
System.out.println(a.equals(c));         // true
```

Trong API `String`, `copyValueOf(char[])` là cách viết tương đương về chức năng với `valueOf(char[])`. Tương tự, overload `copyValueOf(char[], offset, count)` tương đương với `valueOf(char[], offset, count)` về chuỗi tạo ra.

| Cách viết | Kết quả với `char[]` | Khi nào nên dùng |
| --- | --- | --- |
| `String.copyValueOf(data)` | Chuỗi chứa toàn bộ mảng | Nhấn mạnh chuyển và giữ nội dung của mảng |
| `String.copyValueOf(data, offset, count)` | Chuỗi chứa đoạn mảng | Đã có offset và số `char` cần lấy |
| `String.valueOf(data)` khi `data` có kiểu tĩnh `char[]` | Chuỗi chứa toàn bộ mảng | Cách viết ngắn gọn, phổ biến |
| `String.valueOf(data, offset, count)` | Chuỗi chứa đoạn mảng | Tương đương overload chọn đoạn của `copyValueOf` |
| `new String(data)` | Chuỗi chứa toàn bộ mảng | Cách dùng constructor |
| `new String(data, offset, count)` | Chuỗi chứa đoạn mảng | Cách dùng constructor cho đoạn mảng |

Các cách trên cho cùng **nội dung** khi dùng cùng các ký tự và đoạn mảng. Không nên dùng toán tử `==` để suy ra chúng là cùng đối tượng. Với `String`, so sánh nội dung bằng `equals`.

### `valueOf(char[])` và `valueOf(Object)` khác nhau

`String.valueOf(data)` với biến có kiểu tĩnh `char[]` lấy **nội dung các ký tự**; ép thành `Object` chuyển sang biểu diễn đối tượng mảng:

```java
char[] data = {'H', 'i'};
System.out.println(String.valueOf(data));                // Hi
System.out.println(String.valueOf((Object) data)
        .startsWith("[C@"));                              // true
```

Nếu dữ liệu đến dưới kiểu `Object`, phải kiểm tra `instanceof char[]` trước khi chọn cách chuyển đổi; không ép kiểu vô điều kiện. Chi tiết phân giải overload và `null` nằm trong bài về `String.valueOf(Object)` so với `String.valueOf(char[])`.

### Phân biệt với Arrays.toString

`Arrays.toString(char[])` tạo biểu diễn hiển thị các **phần tử mảng**, có dấu ngoặc vuông, dấu phẩy và dấu cách; nó không ghép các ký tự thành chuỗi liền mạch:

```java
char[] data = {'H', 'i'};

System.out.println(String.copyValueOf(data)); // Hi
System.out.println(java.util.Arrays.toString(data)); // [H, i]
```

Hai cách đều có ích nhưng phục vụ mục đích khác nhau: cái đầu tạo văn bản, cái sau in cấu trúc mảng để gỡ lỗi.

## 5. offset và count: chọn đúng phạm vi

Giả sử `data.length == n`. Một phạm vi hợp lệ cần thỏa tất cả điều kiện:

- `offset >= 0`.
- `count >= 0`.
- `offset <= n`.
- `count <= n - offset`.

Nói cách khác, khoảng `[offset, offset + count)` phải nằm bên trong mảng. Viết điều kiện `count <= n - offset` giúp tránh việc tính `offset + count` bị tràn số nguyên trong tình huống giá trị cực đoan.

```java
char[] data = {'a', 'b', 'c', 'd'};

System.out.println(String.copyValueOf(data, 1, 2)); // bc
System.out.println(String.copyValueOf(data, 4, 0).isEmpty()); // true
```

Lấy `count == 0` trong phạm vi hợp lệ cho ra chuỗi rỗng `""`; `offset == data.length` được phép **nếu count bằng 0**. Ngược lại, chỉ số âm hoặc yêu cầu vượt giới hạn sẽ phát sinh ngoại lệ.

Nếu cần lấy từ vị trí `from` (bao gồm) đến `toExclusive` (không bao gồm), hãy tính `count = toExclusive - from`:

```java
char[] data = {'a', 'b', 'c', 'd', 'e'};
int from = 1;
int toExclusive = 4;

String result = String.copyValueOf(data, from, toExclusive - from);
System.out.println(result); // bcd
```

Cách này nhất quán với quy ước phạm vi nửa mở trong nhiều API Java. Tránh truyền thẳng `toExclusive` làm `count` nếu đoạn không bắt đầu từ 0.

## 6. null, vùng không hợp lệ và các ngoại lệ

Không có chuỗi hợp lệ nào được trả về khi truyền mảng `null` cho `copyValueOf`.

```java
char[] missing = null;

try {
    String.copyValueOf(missing);
} catch (NullPointerException e) {
    System.out.println("Mảng nguồn là null");
}
```

Một lời gọi với `offset` hoặc `count` không hợp lệ phát sinh `IndexOutOfBoundsException` (các phiên bản JDK có thể dùng lớp con cụ thể):

```java
char[] data = {'J', 'a', 'v', 'a'};

try {
    String.copyValueOf(data, 3, 2); // cần 2 char từ index 3
} catch (IndexOutOfBoundsException e) {
    System.out.println("Đoạn mảng vượt giới hạn");
}
```

Đừng nhầm với overload nhận `Object` của `String.valueOf`. Gọi `String.valueOf((Object) null)` cho chuỗi văn bản `"null"`, trong khi `String.copyValueOf((char[]) null)` ném `NullPointerException`. Đây là những hợp đồng khác nhau.

Khi dữ liệu đến từ người dùng hoặc buffer có `offset`/`count` tính toán, hãy kiểm tra bất biến phạm vi ở ranh giới hệ thống. Nếu dữ liệu bắt buộc có mảng, việc ném ngoại lệ có thể là lựa chọn phù hợp; nếu `null` có ý nghĩa nghiệp vụ, hãy xử lý rõ trước khi gọi:

```java
static String safelyCopy(char[] data) {
    return data == null ? "" : String.copyValueOf(data);
}
```

Mẫu này chọn chuỗi rỗng khi nguồn `null` **theo quyết định của ứng dụng**, không phải hành vi mặc định của API.

## 7. char[] là các đơn vị UTF-16, không phải mọi "ký tự nhìn thấy"

`char` trong Java là đơn vị mã UTF-16 16-bit. Nhiều ký tự Unicode thường gặp, như `'A'`, chiếm một `char`. Nhưng ký tự nằm ngoài Basic Multilingual Plane (BMP), chẳng hạn emoji `🚀` (U+1F680), được biểu diễn bằng **cặp surrogate gồm hai `char`**.

`copyValueOf(data, offset, count)` đếm theo **phần tử `char`**, không theo số Unicode code point và cũng không theo ký tự người dùng nhìn thấy (grapheme cluster).

```java
char[] symbols = {'A', '\uD83D', '\uDE80', 'B'};
String text = String.copyValueOf(symbols);

System.out.println(text.length()); // 4 đơn vị UTF-16
System.out.println(text.codePointCount(0, text.length())); // 3 code point

String rocket = String.copyValueOf(symbols, 1, 2);
System.out.println(rocket); // 🚀
System.out.println(rocket.length()); // 2
```

Nếu cắt một phần tử ở giữa cặp surrogate, kết quả có thể chứa một surrogate không ghép đôi; chuỗi Java vẫn có thể lưu đơn vị mã đó nhưng quá trình xử lý/hiển thị Unicode về sau có thể gặp vấn đề.

Khi offset/count xuất phát từ vị trí code point, cần tính sang chỉ số UTF-16 đúng cách trước khi dùng `copyValueOf`. Có thể bắt đầu bằng một `String` và dùng `offsetByCodePoints` để xác định ranh giới:

```java
String source = "A🚀B";
int begin = source.offsetByCodePoints(0, 1);
int end = source.offsetByCodePoints(begin, 1);
char[] units = source.toCharArray();

String rocket = String.copyValueOf(units, begin, end - begin);
System.out.println(rocket); // 🚀
```

Ở đây `begin == 1`, `end == 3`, nên `count == 2`. Đây là hai đơn vị `char` biểu diễn một code point, hoàn toàn phù hợp với hợp đồng của `copyValueOf`.

**Không nhầm với mã hóa:** `copyValueOf` không đọc byte và không áp dụng `UTF-8` hay `Charset`; đầu vào là các đơn vị `char` đã có sẵn. Khi đầu vào là `byte[]`, cần giải mã với charset phù hợp (ví dụ `new String(bytes, StandardCharsets.UTF_8)`), không dùng `copyValueOf`.

## 8. Ví dụ Java 17+ hoàn chỉnh

Lưu mã sau vào tệp **`CopyValueOfDemo.java`**:

```java
public class CopyValueOfDemo {

    public static void main(String[] args) {
        char[] letters = {'J', 'a', 'v', 'a', ' ', '1', '7'};

        String whole = String.copyValueOf(letters);
        String word = String.copyValueOf(letters, 0, 4);
        String tail = String.copyValueOf(letters, 5, 2);
        String byValueOf = String.valueOf(letters);
        String byConstructor = new String(letters);

        System.out.println("whole = " + whole);
        System.out.println("word = " + word);
        System.out.println("tail = " + tail);
        System.out.println("same text = "
                + (whole.equals(byValueOf) && whole.equals(byConstructor)));

        letters[0] = 'X';
        letters[5] = '2';

        System.out.println("array now = " + new String(letters));
        System.out.println("old string = " + whole);

        char[] roundTrip = word.toCharArray();
        roundTrip[0] = 'L';
        System.out.println("word remains = " + word);

        System.out.println("empty tail = "
                + String.copyValueOf(letters, letters.length, 0).isEmpty());

        System.out.println("object overload uses contents = "
                + String.valueOf((Object) letters).equals(new String(letters)));

        char[] symbols = {'A', '\uD83D', '\uDE80', 'B'};
        String line = String.copyValueOf(symbols);
        String rocket = String.copyValueOf(symbols, 1, 2);

        System.out.println("UTF16 units = " + line.length());
        System.out.println("code points = "
                + line.codePointCount(0, line.length()));
        System.out.println("rocket units = " + rocket.length());

        try {
            String.copyValueOf((char[]) null);
        } catch (NullPointerException e) {
            System.out.println("null -> NullPointerException");
        }

        try {
            String.copyValueOf(letters, 6, 2);
        } catch (IndexOutOfBoundsException e) {
            System.out.println("bad range -> IndexOutOfBoundsException");
        }
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 CopyValueOfDemo.java
java CopyValueOfDemo
```

Kết quả chuẩn:

```text
whole = Java 17
word = Java
tail = 17
same text = true
array now = Xava 27
old string = Java 17
word remains = Java
empty tail = true
object overload uses contents = false
UTF16 units = 4
code points = 3
rocket units = 2
null -> NullPointerException
bad range -> IndexOutOfBoundsException
```

Ý nghĩa của các dòng quan trọng:

- `whole` vẫn là `"Java 17"` sau khi `letters` đã thành `"Xava 27"`: chuỗi đã tạo không liên kết sống với mảng.
- `same text = true` xác nhận ba cách tạo chuỗi có cùng **nội dung**, không kết luận về việc chúng là cùng đối tượng.
- `empty tail = true` cho thấy `count = 0` hợp lệ tại cuối mảng.
- `object overload uses contents = false` cho thấy ép `char[]` thành `Object` làm thay đổi overload được chọn khi gọi `String.valueOf`.
- `UTF16 units = 4` nhưng `code points = 3` minh họa cặp surrogate; `rocket units = 2` là chiều dài theo `char` của một emoji.
- Hai ngoại lệ cuối kiểm tra riêng lỗi `null` và phạm vi không hợp lệ.

## 9. Khi nào nên chọn copyValueOf?

Sử dụng `String.copyValueOf(char[])` khi đã có một mảng ký tự chứa dữ liệu cần chuyển thành chuỗi, và `String.copyValueOf(char[], offset, count)` khi chỉ muốn giữ một đoạn mà không cần trước đó tự tạo mảng con.

Ví dụ với bộ đệm được sử dụng trong quá trình đọc:

```java
char[] buffer = new char[8];
// Giả sử API đọc đã điền 3 ký tự đầu: 'c', 'a', 't'
buffer[0] = 'c';
buffer[1] = 'a';
buffer[2] = 't';
int length = 3;

String snapshot = String.copyValueOf(buffer, 0, length);
// snapshot là "cat"; phần còn lại của buffer không được ghép vào chuỗi
```

Khi chỉ một phần mảng chứa dữ liệu có ý nghĩa, overload ba tham số giúp tránh đưa các phần tử chưa dùng (ví dụ `'\0'`) vào `String`.

Các lưu ý khi lựa chọn:

- Về **nội dung kết quả**, `String.valueOf(char[])` và `String.copyValueOf(char[])` tương đương. Có thể chọn cách viết quen thuộc của codebase.
- Không dùng `String.copyValueOf` để ghép nhiều mảng, chuyển kiểu đối tượng bất kỳ hay giải mã `byte[]`. Nếu cần ghép nhiều đoạn, `StringBuilder` hoặc cách ghép phù hợp thường diễn đạt mục đích rõ hơn.
- Việc tạo `String` mới từ mảng có chi phí xử lý và lưu trữ phụ thuộc độ dài; khi lặp với dữ liệu lớn, nên đo đạc trường hợp thực tế. Không suy đoán chi tiết nội bộ của từng JDK.
- Nếu mảng chứa bí mật cần xóa khỏi bộ nhớ ngay sau sử dụng, việc chuyển thành `String` bất biến có thể làm khó kiểm soát vòng đời dữ liệu; cân nhắc yêu cầu bảo mật trước khi tạo chuỗi.
- Với văn bản Unicode, kiểm tra ranh giới UTF-16 và chuẩn hóa riêng nếu bài toán cần so sánh Unicode tương đương; `copyValueOf` không tự chuẩn hóa dấu hay code point.

## 10. Những lỗi phổ biến

1. **Dùng `charArray.toString()` và mong nhận nội dung.** Phương thức đó biểu diễn đối tượng mảng, không ghép ký tự. Dùng `String.copyValueOf(charArray)`.
2. **Nhầm `count` là endIndex.** `copyValueOf(data, 2, 5)` nghĩa là lấy **năm ký tự từ chỉ số 2**, không phải lấy các chỉ số 2, 3, 4.
3. **Giữ tham chiếu đến mảng rồi tưởng thay đổi mảng sẽ đổi chuỗi.** `String` là immutable; snapshot đã tạo không đổi.
4. **Không kiểm tra `null` hoặc phạm vi.** `copyValueOf(null)` gây `NullPointerException`; đoạn ngoài mảng gây `IndexOutOfBoundsException`.
5. **Ép mảng thành `Object` khi gọi `String.valueOf`.** Overload `valueOf(Object)` không ghép các phần tử `char[]` thành văn bản.
6. **Dùng `Arrays.toString(char[])` khi cần chuỗi liền mạch.** Nó được dùng để hiển thị cấu trúc mảng, ví dụ `[H, i]`.
7. **Giả định `char` tương ứng một Unicode code point.** Một ký tự ngoài BMP thường chiếm hai đơn vị UTF-16; phạm vi có thể cắt nhầm cặp surrogate.
8. **Nhầm số ký tự hợp lệ của buffer với `buffer.length`.** Nếu buffer chỉ chứa một phần dữ liệu, phải truyền đúng `offset` và `count`.
9. **So sánh chuỗi bằng `==` thay vì `equals`.** Kết quả tạo từ nhiều API có thể là các đối tượng khác nhau nhưng có cùng văn bản.

## 11. Bài tập tự kiểm tra

**Bài 1.** Với đoạn mã sau, kết quả là gì?

```java
char[] data = {'A', 'B', 'C', 'D', 'E'};
System.out.println(String.copyValueOf(data, 1, 3));
```

**Đáp án:** `BCD`. Bắt đầu tại chỉ số 1 và lấy ba phần tử.

**Bài 2.** Vì sao `String.copyValueOf(data, 2, 4)` gây ngoại lệ khi `data.length == 5`?

**Đáp án:** Phạm vi dự kiến là `[2, 6)`, vượt ra ngoài `[0, 5)` của mảng. `count` cần nhỏ hơn hoặc bằng `5 - 2 = 3`.

**Bài 3.** Sau khi chạy mã sau, `s` có đổi thành `"Xbc"` không?

```java
char[] data = {'a', 'b', 'c'};
String s = String.copyValueOf(data);
data[0] = 'X';
```

**Đáp án:** Không. `s` vẫn là `"abc"` vì thay đổi mảng nguồn sau đó không ảnh hưởng `String` đã tạo.

**Bài 4.** `String.copyValueOf(data, 0, 1)` có chắc lấy được toàn bộ emoji ở đầu mảng không?

**Đáp án:** Không chắc. Emoji nằm ngoài BMP thường gồm hai `char` UTF-16. Cần xác định ranh giới code point chính xác rồi mới cắt theo `char`.

**Bài 5.** Tại sao `String.valueOf((Object) data)` không nên dùng để chuyển `char[]` thành văn bản?

**Đáp án:** Nó chọn overload `valueOf(Object)` và lấy biểu diễn đối tượng mảng. Muốn ghép từng phần tử `char`, dùng `String.valueOf(data)` với kiểu tĩnh `char[]`, `String.copyValueOf(data)` hoặc `new String(data)`.

## Tài liệu tham khảo

- [Java SE 17 — String API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): các overload `copyValueOf`, `valueOf`, constructor từ `char[]`, `toCharArray`, và quy tắc immutability.
- [Java SE 17 — Character API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): UTF-16 code units, code points và surrogate pairs.

**Ghi nhớ:** `copyValueOf` tạo `String` từ toàn bộ hoặc một đoạn mảng `char[]`, `offset` là vị trí bắt đầu, `count` là số **đơn vị UTF-16 `char`** được lấy, và nội dung chuỗi không thay đổi khi mảng nguồn bị sửa về sau.