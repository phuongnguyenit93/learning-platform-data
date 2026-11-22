# Kiểm thử biên số nguyên và dữ liệu ký tự khả biến trong Java

## Mục tiêu

Các API tiện ích của Java có thể xử lý đúng giá trị phổ biến nhưng tạo ra kết quả bất ngờ tại **giá trị số nhỏ nhất/lớn nhất**, **vùng cắt rỗng**, **tham số null** hoặc khi dữ liệu ký tự nguồn bị sửa. Bài này hướng dẫn thiết kế và chạy kiểm thử cho các trường hợp đó qua API hiện hành:

- `String.valueOf(int)`, `String.valueOf(long)` và ranh giới với `Integer.parseInt(...)`.
- `String.valueOf(char[])`, `String.copyValueOf(char[])`, overload vùng cắt `offset/count`.
- Việc tạo `String` bất biến từ `char[]` và `StringBuilder` khả biến.
- Null, mảng rỗng, cặp surrogate UTF-16, và biên số lần lặp của `String.repeat(int)`.
- Cách viết kiểm thử có expected value rõ ràng, kiểm tra đúng exception và tránh gây cạn bộ nhớ.

Các API trong bài vẫn có hiệu lực ở Java hiện đại; mã hoàn chỉnh tương thích **JDK 17+** và phù hợp với bối cảnh Java 15. Không cần bật preview hay thư viện ngoài để chạy chương trình chính.

## 1. Lập ma trận trường hợp biên trước khi viết test

Kiểm thử `String.valueOf(42)` thành `"42"` là cần thiết nhưng chưa đủ. Một ma trận hữu ích cần bao gồm:

| Loại đầu vào | Ví dụ | Expected |
| --- | --- | --- |
| Biên dưới `int` | `Integer.MIN_VALUE` | `"-2147483648"` |
| Biên trên `int` | `Integer.MAX_VALUE` | `"2147483647"` |
| Số không, âm và dương nhỏ | `0`, `-1`, `1` | `"0"`, `"-1"`, `"1"` |
| Biên dưới `long` | `Long.MIN_VALUE` | `"-9223372036854775808"` |
| Biên trên `long` | `Long.MAX_VALUE` | `"9223372036854775807"` |
| Văn bản nằm ngoài `int` | `"2147483648"`, `"-2147483649"` | `NumberFormatException` khi parse |
| Mảng `char[]` khả biến | Lấy chuỗi rồi đổi phần tử | Snapshot cũ không đổi |
| Vùng cắt hợp lệ, rỗng | `offset=length,count=0` | Chuỗi rỗng |
| Vùng cắt ngoài biên | `offset=-1` hoặc `count` vượt phần còn lại | `IndexOutOfBoundsException` |
| Null theo từng overload | `(Object) null` hoặc `(char[]) null` | Chuỗi `"null"` hoặc `NullPointerException` |
| Unicode bổ sung | Cặp surrogate | Hai đơn vị `char` là một code point |

**Nguyên tắc:** Một ca kiểm thử phải chứng minh được hợp đồng cụ thể. Hãy so sánh với expected độc lập; so sánh `String.valueOf(n)` với chính `String.valueOf(n)` không xác minh điều gì có ích.

## 2. Chuyển số nguyên ở hai cực trị

`String.valueOf(int)` tạo biểu diễn thập phân có dấu của giá trị `int`. Giá trị `Integer.MIN_VALUE` là âm và có độ lớn tuyệt đối lớn hơn `Integer.MAX_VALUE` một đơn vị. API vẫn trả đúng chuỗi:

```java
String min = String.valueOf(Integer.MIN_VALUE);
String max = String.valueOf(Integer.MAX_VALUE);

System.out.println(min.equals("-2147483648")); // true
System.out.println(max.equals("2147483647"));  // true
```

Với `long`, miền giá trị rộng hơn:

```java
String min = String.valueOf(Long.MIN_VALUE);
String max = String.valueOf(Long.MAX_VALUE);

System.out.println(min.equals("-9223372036854775808")); // true
System.out.println(max.equals("9223372036854775807"));  // true
```

`String.valueOf(int/long)` không tự thêm dấu nhóm hàng nghìn theo locale. Nếu cần biểu diễn số cho người dùng, dùng formatter với `Locale` tường minh; còn khi kiểm tra định dạng thập phân chuẩn của số nguyên, các expected string trên ổn định.

### 2.1. Bẫy overflow khi tự xử lý số âm

`Math.abs(Integer.MIN_VALUE)` vẫn cho `Integer.MIN_VALUE` do biểu diễn dương tương ứng vượt miền `int`:

```java
int n = Integer.MIN_VALUE;
System.out.println(Math.abs(n) == n); // true
```

Vì vậy, không nên viết hàm đổi số nguyên thành chuỗi bằng cách lấy `Math.abs(n)` rồi tự ghép dấu mà không xét riêng biên dưới. Hãy dùng API đã có như `String.valueOf(n)` hoặc `Integer.toString(n)`. Kiểm thử tại `Integer.MIN_VALUE` sẽ phát hiện cách làm thủ công thiếu an toàn.

### 2.2. Chuyển số sang chuỗi khác với parse chuỗi thành số

```java
String text = String.valueOf(Integer.MAX_VALUE);
int parsed = Integer.parseInt(text);
System.out.println(parsed == Integer.MAX_VALUE); // true
```

Nhưng:

```java
Integer.parseInt("2147483648");  // NumberFormatException
Integer.parseInt("-2147483649"); // NumberFormatException
```

Hai dòng ngay trên **chỉ minh họa hành vi ném lỗi**, không phải một chương trình hoàn chỉnh để chạy liên tiếp mà không bắt exception. Khi kiểm thử parse, hãy khẳng định đúng `NumberFormatException`. Không nên tự suy luận rằng Java sẽ cắt bớt chữ số hoặc wrap giá trị khi `parseInt` gặp số nằm ngoài miền.

## 3. Vì sao cần kiểm thử dữ liệu ký tự khả biến?

`String` là bất biến (*immutable*): sau khi tạo, nội dung của chính đối tượng đó không thể bị sửa bằng các thao tác trên đối tượng nguồn. Trong khi đó:

- `char[]` cho phép cập nhật bất kỳ phần tử nào.
- `StringBuilder` có thể thay ký tự và thêm/bớt nội dung.
- `CharSequence` là interface mô tả chuỗi ký tự nhưng **không bảo đảm đối tượng triển khai là bất biến**; một biến `CharSequence` có thể trỏ tới `StringBuilder`.

Lỗi dễ xảy ra khi lập trình viên nghĩ đang lưu “một bản chụp” nhưng thực tế giữ tham chiếu sống đến một đối tượng khả biến. Test đúng cần **lấy giá trị trước**, **sửa dữ liệu nguồn sau**, rồi **kiểm tra cả hai**.

### 3.1. `String.valueOf(char[])` và `String.copyValueOf(char[])`

```java
char[] letters = {'J', 'a', 'v', 'a'};
String byValue = String.valueOf(letters);
String byCopy = String.copyValueOf(letters);
String byConstructor = new String(letters);

letters[0] = 'L';

System.out.println(byValue.equals("Java"));       // true
System.out.println(byCopy.equals("Java"));        // true
System.out.println(byConstructor.equals("Java")); // true
System.out.println(String.valueOf(letters));       // Lava
```

Cả ba chuỗi được tạo tại một thời điểm và lưu nội dung độc lập. Việc thay phần tử `letters[0]` không đổi các `String` cũ. `String.copyValueOf(char[])` tương đương về giá trị với `String.valueOf(char[])`; chọn cách viết thể hiện rõ mục đích trong code.

Trong tình huống **một luồng khác sửa mảng cùng lúc đang copy**, chương trình cần cơ chế đồng bộ nếu muốn snapshot nhất quán. Test tuần tự ở trên không chứng minh an toàn khi cập nhật đồng thời.

### 3.2. `StringBuilder.toString()` tạo snapshot

```java
StringBuilder builder = new StringBuilder("alpha");
String frozen = builder.toString();
builder.setCharAt(0, 'A');
builder.append('!');

System.out.println(frozen.equals("alpha"));           // true
System.out.println(builder.toString().equals("Alpha!")); // true
```

Lấy `String` từ `StringBuilder` không khiến hai đối tượng chia sẻ một vùng dữ liệu khả biến theo cách cho phép sửa chuỗi đã tạo. Chuỗi `frozen` giữ nội dung cũ; builder tiếp tục thay đổi.

Nhưng nếu giữ tham chiếu kiểu `CharSequence` đến builder:

```java
StringBuilder builder = new StringBuilder("old");
CharSequence live = builder;
String snapshot = live.toString();
builder.replace(0, builder.length(), "new");

// live.toString() -> "new", snapshot -> "old".
```

Chỉ đổi kiểu tham chiếu sang `CharSequence` **không sao chép dữ liệu**. Khi cần một chuỗi cố định cho cache, kết quả API hoặc expected của test, hãy thực sự tạo `String` ở đúng thời điểm.

## 4. Kiểm thử offset và count của vùng cắt char[]

Các overload:

```java
String.valueOf(char[] data, int offset, int count)
String.copyValueOf(char[] data, int offset, int count)
```

dùng `offset` là vị trí bắt đầu (đánh số từ 0) và `count` là **số ký tự được lấy**, không phải chỉ số kết thúc. Ví dụ:

```java
char[] data = {'x', 'y', 'z'};
String part = String.copyValueOf(data, 1, 2);
System.out.println(part.equals("yz")); // true
```

Một vùng hợp lệ thỏa mãn:

- `0 <= offset <= data.length`.
- `0 <= count`.
- `count <= data.length - offset`.

Vùng `offset=data.length,count=0` **hợp lệ** và trả chuỗi rỗng:

```java
String empty = String.valueOf(data, data.length, 0);
System.out.println(empty.isEmpty()); // true
```

Những vùng sau không hợp lệ và báo `IndexOutOfBoundsException`:

```java
String.valueOf(data, -1, 1);    // IndexOutOfBoundsException
String.copyValueOf(data, 1, 3); // IndexOutOfBoundsException
```

Đây là ví dụ mô tả exception dự kiến. Trong chương trình kiểm thử hoàn chỉnh, helper sẽ bắt đúng exception để chương trình tiếp tục thực hiện các test còn lại.

### 4.1. Vùng cắt cũng không giữ tham chiếu mảng nguồn

```java
char[] data = {'x', 'y', 'z'};
String part = String.copyValueOf(data, 1, 2);
data[1] = 'Q';

System.out.println(part.equals("yz"));            // true
System.out.println(String.valueOf(data).equals("xQz")); // true
```

Biên của slice được kiểm tra tại lúc tạo chuỗi; sau khi copy, những thay đổi của mảng không làm đổi chuỗi được tạo. Khi tự kiểm tra biên đầu vào, có thể kiểm tra offset trước rồi dùng `count <= length-offset` để tránh cộng hai số chưa được xác thực làm tràn `int`.

## 5. Overload và null: cùng tên API, hành vi khác nhau

`String.valueOf` có nhiều overload nên **kiểu đối số quyết định logic**:

```java
String objectValue = String.valueOf((Object) null);
System.out.println(objectValue.equals("null")); // true
```

Overload `Object` null trả một chuỗi gồm bốn ký tự `"null"`. Trong khi đó:

```java
String.valueOf((char[]) null); // NullPointerException
```

Overload `char[]` null phải đọc nội dung mảng để tạo chuỗi nên báo `NullPointerException`. Với literal `String.valueOf(null)`, trình biên dịch chọn overload `char[]` cụ thể hơn `Object`; vì vậy đừng mặc định null nào cũng thành `"null"`.

Trường hợp **mảng rỗng thực sự** khác hẳn null:

```java
String empty = String.valueOf(new char[0]);
System.out.println(empty.isEmpty()); // true
```

Cần thêm một bẫy overload:

```java
char[] letters = {'o', 'k'};
String direct = String.valueOf(letters);          // "ok"
String asObject = String.valueOf((Object) letters);
```

`asObject` là kết quả `toString()` của đối tượng mảng, thường trông như `"[C@..."` (mã định danh đối tượng khác giữa lần chạy), **không** phải `"ok"`. Khi dữ liệu kiểu `Object` có thể chứa `char[]`, hãy xử lý riêng nếu yêu cầu là biến mảng thành văn bản.

## 6. Biên Unicode: char không đồng nghĩa một ký tự nhìn thấy

Mỗi `char` lưu **một đơn vị mã UTF-16**. Một Unicode code point ngoài BMP có thể cần *hai* `char` liên tiếp (cặp surrogate). Ví dụ dùng escape để không phụ thuộc font terminal:

```java
String symbol = "\uD83D\uDE00"; // U+1F600
char[] units = symbol.toCharArray();

System.out.println(units.length == 2);                // true
System.out.println(symbol.codePointCount(0, 2) == 1);  // true
System.out.println(String.valueOf(units).equals(symbol)); // true
```

`String.valueOf(char[])` bảo toàn chuỗi mã UTF-16 của mảng. Nhưng lấy slice `offset=0,count=1` của cặp surrogate chỉ lấy **một nửa cặp**, không biểu diễn code point ban đầu. Đừng cắt văn bản theo chỉ số `char` nếu yêu cầu nghiệp vụ là cắt theo Unicode code point hoặc grapheme cluster; phải xác định đơn vị ký tự cần xử lý và có test cho dữ liệu Unicode.

Chuỗi tạo ra từ `char[]` có thể chứa surrogate đơn lẻ; việc tạo `String` **không tự bảo đảm dữ liệu hợp lệ với mọi yêu cầu mã hóa hoặc giao thức**.

## 7. Biên tham số int khác: String.repeat(count)

`String.repeat(int)` nhận một số lần lặp kiểu `int`:

```java
System.out.println("x".repeat(0).isEmpty());     // true
System.out.println("x".repeat(3).equals("xxx")); // true
```

Với `count < 0`, API báo `IllegalArgumentException`:

```java
"x".repeat(-1); // IllegalArgumentException
```

Đừng dùng `"x".repeat(Integer.MAX_VALUE)` trong bộ unit test bình thường để “thử biên trên”: việc cấp phát có thể tốn bộ nhớ cực lớn hoặc ném `OutOfMemoryError`. Đối với giới hạn do ứng dụng đặt ra, hãy kiểm thử quy tắc xác thực count **trước khi gọi** API cấp phát.

## 8. Chương trình kiểm thử hoàn chỉnh có thể chạy

Tạo tệp **`StringBoundaryDemo.java`** bằng UTF-8. Chương trình chỉ dùng thư viện chuẩn JDK; nó có helper tự kiểm tra điều kiện và kiểu exception, **không phụ thuộc cờ `-ea`** của Java assertions.

```java
public class StringBoundaryDemo {
    private static void check(String label, boolean condition) {
        if (!condition) {
            throw new AssertionError(label + " FAILED");
        }
        System.out.println(label + "=PASS");
    }

    private static void expectError(
            String label,
            Class<? extends RuntimeException> expected,
            Runnable action) {
        try {
            action.run();
        } catch (RuntimeException error) {
            if (!expected.isInstance(error)) {
                throw new AssertionError(
                        label + " wrong exception", error);
            }
            System.out.println(label + "=PASS");
            return;
        }
        throw new AssertionError(label + " did not throw");
    }

    public static void main(String[] args) {
        check("intMin",
                String.valueOf(Integer.MIN_VALUE).equals("-2147483648"));
        check("intMax",
                String.valueOf(Integer.MAX_VALUE).equals("2147483647"));
        check("longMin",
                String.valueOf(Long.MIN_VALUE)
                        .equals("-9223372036854775808"));
        check("longMax",
                String.valueOf(Long.MAX_VALUE)
                        .equals("9223372036854775807"));
        check("zero", String.valueOf(0).equals("0"));

        expectError("parseAboveMax", NumberFormatException.class,
                () -> Integer.parseInt("2147483648"));
        expectError("parseBelowMin", NumberFormatException.class,
                () -> Integer.parseInt("-2147483649"));

        char[] letters = {'J', 'a', 'v', 'a'};
        String byValue = String.valueOf(letters);
        String byCopy = String.copyValueOf(letters);
        String byConstructor = new String(letters);
        letters[0] = 'L';

        check("arraySnapshots",
                byValue.equals("Java")
                        && byCopy.equals("Java")
                        && byConstructor.equals("Java"));
        check("sourceUpdated",
                String.valueOf(letters).equals("Lava"));

        StringBuilder builder = new StringBuilder("alpha");
        String frozen = builder.toString();
        builder.setCharAt(0, 'A');
        builder.append('!');

        check("builderSnapshot",
                frozen.equals("alpha")
                        && builder.toString().equals("Alpha!"));

        char[] data = {'x', 'y', 'z'};
        String slice = String.copyValueOf(data, 1, 2);
        data[1] = 'Q';
        check("sliceSnapshot", slice.equals("yz"));
        check("emptySlice",
                String.valueOf(data, data.length, 0).isEmpty());

        expectError("badOffset", IndexOutOfBoundsException.class,
                () -> String.valueOf(data, -1, 1));
        expectError("badCount", IndexOutOfBoundsException.class,
                () -> String.copyValueOf(data, 1, 3));
        expectError("nullCharArray", NullPointerException.class,
                () -> String.valueOf((char[]) null));
        check("nullObject",
                String.valueOf((Object) null).equals("null"));

        String symbol = "\uD83D\uDE00";
        check("supplementaryCodePoint",
                symbol.length() == 2
                        && symbol.codePointCount(0, symbol.length()) == 1
                        && String.valueOf(symbol.toCharArray())
                                .equals(symbol));

        check("repeatZero", "x".repeat(0).isEmpty());
        expectError("repeatNegative", IllegalArgumentException.class,
                () -> "x".repeat(-1));
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac -encoding UTF-8 StringBoundaryDemo.java
java StringBoundaryDemo
```

**Stdout chính xác nếu tất cả kiểm thử đạt:**

```text
intMin=PASS
intMax=PASS
longMin=PASS
longMax=PASS
zero=PASS
parseAboveMax=PASS
parseBelowMin=PASS
arraySnapshots=PASS
sourceUpdated=PASS
builderSnapshot=PASS
sliceSnapshot=PASS
emptySlice=PASS
badOffset=PASS
badCount=PASS
nullCharArray=PASS
nullObject=PASS
supplementaryCodePoint=PASS
repeatZero=PASS
repeatNegative=PASS
```

Những dòng `PASS` không chỉ in giá trị mà xác nhận kiểm thử đúng **giá trị mong đợi** hoặc **kiểu lỗi được quy định**. Khi một case sai, chương trình ném `AssertionError` để việc chạy trong CI hay terminal không vô tình báo thành công.

## 9. Chuyển các kiểm thử thành JUnit 5

Trong dự án đã có dependency **JUnit Jupiter**, nên dùng `assertEquals` và `assertThrows` để framework báo cáo từng trường hợp. Đoạn này là **một lớp test cần JUnit 5 trên classpath**, không phải chương trình thuần JDK có thể chạy bằng hai lệnh ở trên:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class StringUtilityBoundaryTest {
    @Test
    void convertsIntExtremesExactly() {
        assertEquals("-2147483648",
                String.valueOf(Integer.MIN_VALUE));
        assertEquals("2147483647",
                String.valueOf(Integer.MAX_VALUE));
    }

    @Test
    void copyingCharsDoesNotExposeMutableArray() {
        char[] source = {'J', 'a', 'v', 'a'};
        String snapshot = String.copyValueOf(source);
        source[0] = 'L';

        assertEquals("Java", snapshot);
        assertEquals("Lava", String.valueOf(source));
    }

    @Test
    void invalidSliceFailsWithExpectedException() {
        char[] data = {'x', 'y', 'z'};
        assertThrows(IndexOutOfBoundsException.class,
                () -> String.valueOf(data, 1, 3));
    }

    @Test
    void integerTextOutsideRangeFails() {
        assertThrows(NumberFormatException.class,
                () -> Integer.parseInt("2147483648"));
    }
}
```

Nếu kiểm thử nhiều cặp dữ liệu, có thể dùng *parameterized tests* của JUnit Jupiter để gom bảng input và expected. Với kiểm thử hành vi cực biên, đừng chỉ xem test “không lỗi”: hãy khẳng định cả trạng thái của dữ liệu nguồn trước/sau và hợp đồng của chuỗi đã tạo.

## 10. Các lỗi thường gặp trong kiểm thử

| Sai lầm | Vì sao không ổn | Cách khắc phục |
| --- | --- | --- |
| Chỉ thử số dương nhỏ | Không phát hiện lỗi xử lý biên âm nhỏ nhất | Thử `MIN_VALUE`, `MAX_VALUE`, `-1`, `0`, `1` |
| Tính expected bằng chính hàm đang kiểm thử | Test có thể luôn qua | So sánh với literal đã xác định độc lập |
| Dùng `Math.abs(Integer.MIN_VALUE)` để format | `int` overflow | Dùng API chuyển số đã có và test cực trị |
| Chỉ đọc mảng ký tự trước khi thay | Không chứng minh snapshot độc lập | Sửa nguồn *sau khi* copy và kiểm tra chuỗi cũ |
| Giữ `CharSequence` rồi mặc định là bất biến | Có thể là `StringBuilder` | Gọi `toString()` để lấy snapshot khi cần |
| Nhầm `offset,count` thành start/end | Slice sai hoặc exception | Kiểm tra vùng đầy đủ, rỗng, ngoài biên |
| Cho mọi null thành `"null"` | Null `char[]` ném NPE | Chọn overload rõ kiểu; test riêng từng trường hợp |
| Gọi `String.valueOf((Object) chars)` | Nhận mô tả đối tượng mảng | Gọi overload `char[]` khi cần văn bản |
| Cắt ở giữa surrogate pair | Có thể tạo dữ liệu không biểu diễn code point mong muốn | Thiết kế theo code point/grapheme phù hợp |
| Thử `repeat` bằng count khổng lồ | Có thể gây cạn bộ nhớ | Thử count âm, 0, dương nhỏ; kiểm tra giới hạn nghiệp vụ riêng |
| Bắt mọi `Exception` và báo PASS | Che giấu exception sai loại | Dùng `assertThrows` hoặc helper kiểm tra class exception |
| Dùng `assert` nhưng không bật `-ea` | Assertion Java có thể bị tắt | Dùng JUnit hoặc helper luôn đánh giá điều kiện |

## 11. Bài tập tự kiểm tra

**Bài 1.** Sau đoạn mã sau, `first` và `second` là gì?

```java
char[] data = {'a', 'b', 'c'};
String first = String.valueOf(data);
data[1] = 'X';
String second = String.valueOf(data);
```

**Đáp án:** `first = "abc"`, `second = "aXc"`. Chúng là hai snapshot được tạo ở hai thời điểm khác nhau.

**Bài 2.** `String.valueOf(data, data.length, 0)` có hợp lệ khi `data` là mảng không null?

**Đáp án:** Có, đây là vùng rỗng tại cuối mảng và tạo `""`.

**Bài 3.** `String.valueOf((Object) null)` và `String.valueOf((char[]) null)` khác nhau thế nào?

**Đáp án:** Overload `Object` trả `"null"`; overload `char[]` ném `NullPointerException`.

**Bài 4.** Vì sao `Integer.parseInt("2147483648")` báo lỗi?

**Đáp án:** Chuỗi biểu diễn một giá trị lớn hơn `Integer.MAX_VALUE`, nên không thuộc miền `int`.

**Bài 5.** Sau khi lấy `String snapshot = builder.toString()` rồi gọi `builder.append("!")`, `snapshot` có đổi không?

**Đáp án:** Không. `String` là bất biến; `StringBuilder` vẫn có thể tiếp tục thay đổi.

## Ghi nhớ

**Số nguyên:** kiểm tra cả hai cực trị, dấu âm, số không và văn bản ngoài phạm vi; các API chuyển số thành chuỗi và parse từ chuỗi là hai hợp đồng riêng.

**Dữ liệu ký tự khả biến:** lấy snapshot bằng `String.valueOf(char[])`, `String.copyValueOf(char[])` hoặc `StringBuilder.toString()`, sửa dữ liệu nguồn, rồi xác nhận snapshot cũ không đổi. Chú ý overload `Object`/`char[]`, vùng `offset/count`, null và Unicode UTF-16.

**Kiểm thử tốt:** so sánh với expected độc lập, xác nhận đúng kiểu exception, giữ dữ liệu kiểm thử nhỏ và có thể chạy lặp lại ở mọi môi trường.

### Tài liệu Java chính thức

- [Java SE 21 — String: valueOf, copyValueOf, repeat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
- [Java SE 21 — Integer và parseInt](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html)
- [Java SE 21 — Long](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Long.html)
- [Java SE 21 — StringBuilder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StringBuilder.html)
- [Java SE 21 — Character, UTF-16 và code point](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Character.html)
