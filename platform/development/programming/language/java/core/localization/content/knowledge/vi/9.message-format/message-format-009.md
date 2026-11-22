# MessageFormat: đối số thiếu, giá trị null, parse và giới hạn đảo ngược thông điệp

## Mục tiêu

`java.text.MessageFormat` giúp tạo thông điệp có các đối số đánh số như `{0}`, `{1}` và các tùy chọn định dạng số, ngày, giờ hoặc lựa chọn. Khi trình bày thông điệp cho người dùng, điều dễ bỏ sót là **đầu vào bị thiếu hoặc là null không nhất thiết gây exception**, còn `parse(...)` không phải thao tác đảo ngược đáng tin cậy của `format(...)`.

Sau bài học, bạn có thể:

- Phân biệt **không có phần tử đối số** và **phần tử có mặt nhưng bằng `null`** trong `Object[]`.
- Dự đoán kết quả của `MessageFormat` khi placeholder trỏ đến index vượt quá số đối số được cung cấp.
- Hiểu cách `MessageFormat.parse(...)` dùng pattern để nhận lại một mảng `Object[]` và lúc nào nó thất bại.
- Kiểm tra `ParsePosition`, phân biệt parse thành công với parse hết toàn bộ chuỗi.
- Giải thích những trường hợp không thể khôi phục chính xác đầu vào: placeholder lặp, phép làm tròn, `choice`, nội dung nhập có dấu phân cách, đối số không được nhắc trong pattern.
- Thiết kế xử lý lỗi và kiểm thử cho bản địa hóa mà không phụ thuộc giả định `parse(format(args)) == args`.

Bài tập trung vào **hành vi biên của MessageFormat trong Java 17+**. Các cơ chế chọn `Locale`, dịch bản gốc và quản lý `ResourceBundle` chỉ được đề cập tại nơi chúng ảnh hưởng đến tính đúng đắn của pattern.

## 1. MessageFormat làm gì với đối số?

Một mẫu thông điệp:

```text
Hello {0}! Your order {1} is ready.
```

Các thành phần:

- Phần văn bản tĩnh `Hello` và `Your order ... is ready.` được chép ra kết quả theo pattern.
- `{0}` lấy đối số ở vị trí **0** trong mảng đối số.
- `{1}` lấy đối số ở vị trí **1**.
- Phần tử mở rộng như `{2,number,integer}` hoặc `{3,date,short}` yêu cầu bộ định dạng tương ứng.

Ví dụ:

```java
MessageFormat mf = new MessageFormat(
        "Hello {0}! Your order {1} is ready.",
        Locale.US
);
String text = mf.format(new Object[] {"Ana", "A-42"});
```

Đây là đoạn minh họa trong phương thức với `import java.text.MessageFormat;` và `import java.util.Locale;`. Giá trị `text` là:

```text
Hello Ana! Your order A-42 is ready.
```

Các index trong pattern không phải tên biến. Chúng chỉ vị trí trong mảng `Object[]` được cung cấp khi `format`. Pattern có thể đảo thứ tự hiển thị: `{1}` có thể xuất hiện trước `{0}`; điều này hữu ích cho ngữ pháp của các ngôn ngữ.

**Hợp đồng của MessageFormat là trình bày chuỗi theo pattern**, không phải đảm bảo chuỗi kết quả có thể được phân tích để khôi phục dữ liệu ban đầu.

## 2. Đối số thiếu: giữ nguyên dấu {n}, không tự ném lỗi

Giả sử pattern tham chiếu đến `{0}` và `{1}`, nhưng mã gọi chỉ truyền một phần tử:

```java
MessageFormat mf = new MessageFormat(
        "Hello {0}! State={1}.", Locale.US);

System.out.println(mf.format(new Object[] {"Ana"}));
```

Kết quả:

```text
Hello Ana! State={1}.
```

`{1}` **không được thay thế** vì mảng không có phần tử index 1. Theo hợp đồng Java 17 của `MessageFormat`, nếu đối số không có sẵn (mảng `null` hoặc không đủ phần tử), phần định dạng tương ứng được phát ra như `{argumentIndex}`.

Các trường hợp đáng phân biệt:

| Mảng truyền vào | Kết quả với pattern `Hello {0}! State={1}.` |
| --- | --- |
| `new Object[] {"Ana", "ready"}` | `Hello Ana! State=ready.` |
| `new Object[] {"Ana"}` | `Hello Ana! State={1}.` |
| `new Object[] {}` | `Hello {0}! State={1}.` |
| `new Object[] {"Ana", null}` | `Hello Ana! State=null.` |
| `new Object[] {null, "ready"}` | `Hello null! State=ready.` |

**Không nhầm với `String.format` hoặc `Formatter`.** Các API dùng cú pháp format khác (ví dụ `%s`) và có hợp đồng riêng đối với thiếu đối số. Với `MessageFormat`, placeholder thiếu trong trường hợp trên còn nguyên dưới dạng `{n}`; không tự suy rằng nó sẽ ném `MissingFormatArgumentException`.

Hệ quả:

1. Nếu một màn hình bất ngờ hiển thị `{1}`, cần kiểm tra mảng đối số và pattern đã được dịch.
2. Đừng hiểu việc `format(...)` chạy thành công là bằng chứng ứng dụng đã cung cấp đủ dữ liệu.
3. Đừng coi chuỗi `{1}` xuất hiện là phương pháp kiểm tra thiếu đối số duy nhất: văn bản tĩnh cũng có thể chứa ký tự tương tự nếu pattern có escape hợp lệ.

### Phát hiện thiếu đối số trước khi format

Khi hợp đồng nội dung cố định, cách rõ ràng là kiểm tra số lượng và kiểu đầu vào ở API nghiệp vụ:

```java
static String orderNotice(String customer, String orderId, Locale locale) {
    if (customer == null || orderId == null) {
        throw new IllegalArgumentException("Customer and orderId are required");
    }

    MessageFormat mf = new MessageFormat(
            "Hello {0}, order {1} is ready.", locale);
    return mf.format(new Object[] {customer, orderId});
}
```

Đây là **phương thức minh họa**, đặt trong một lớp có import `MessageFormat` và `Locale`. Kiểm tra đầu vào dựa trên ý nghĩa nghiệp vụ, không phải dựa vào việc MessageFormat có ném exception hay không.

Với pattern nhận từ `ResourceBundle` và có khả năng được người dịch thay đổi thứ tự các index, không nên đếm “có hai dấu ngoặc” bằng regex đơn giản. Pattern có escape, định dạng lồng (đặc biệt với `choice`) và index lặp. Hãy định nghĩa **hợp đồng các tham số** độc lập, dùng parser/kiểm tra pattern thích hợp và test ở từng locale.

## 3. Đối số null: một trường hợp khác với thiếu đối số

`new Object[] {"Ana"}` không có phần tử index 1. Ngược lại, `new Object[] {"Ana", null}` có đủ hai phần tử nhưng **giá trị ở index 1 là `null`**.

Theo quy tắc `MessageFormat.format`, một đối số có mặt nhưng bằng `null` được biểu diễn bằng chuỗi ký tự `"null"`.

```java
MessageFormat mf = new MessageFormat(
        "Item={0}; Quantity={1,number,integer}",
        Locale.US);

System.out.println(mf.format(new Object[] {null, null}));
```

Stdout:

```text
Item=null; Quantity=null
```

Trước khi áp dụng một subformat cụ thể như `number`, `MessageFormat` đã xử lý đối số `null` thành văn bản `null`. Do đó trường hợp null ở `{1,number,integer}` trong ví dụ không tự động tạo số 0 hay buộc ném lỗi kiểu dữ liệu.

Điều này có nhiều hệ quả:

- `null` không có nghĩa “dùng chuỗi rỗng”.
- `null` không có nghĩa “không hiển thị phần tử thông điệp”.
- `null` không có nghĩa “lấy giá trị mặc định từ ResourceBundle”.
- Chuỗi `"null"` xuất hiện trong thông điệp là dấu hiệu cần điều tra dữ liệu, **không phải thông báo thân thiện để hiển thị cho người dùng**.

Nếu nghiệp vụ yêu cầu thông báo khác khi dữ liệu thiếu, hãy lựa chọn có chủ đích ở tầng ứng dụng:

```java
String nameToShow = (name == null || name.isBlank())
        ? "guest"
        : name;

String text = new MessageFormat(
        "Hello {0}", Locale.US)
        .format(new Object[] {nameToShow});
```

Đây là đoạn minh họa bên trong phương thức, đã khai báo biến `name` kiểu `String`. Với ứng dụng đa ngôn ngữ, từ `guest` nên được cung cấp từ tài nguyên bản địa hóa hoặc dùng pattern thông điệp riêng, không nên gắn cứng tiếng Anh vào code production.

### null và chuỗi "null" không thể phân biệt ở đầu ra

So sánh:

```java
MessageFormat mf = new MessageFormat("{0}", Locale.US);
String fromNull = mf.format(new Object[] {null});
String fromText = mf.format(new Object[] {"null"});
```

Hai chuỗi kết quả đều là `"null"`. Thông tin “đây là null hay chuỗi gốc có bốn chữ n-u-l-l” đã bị mất. Ngay cả khi có parser, không có cách suy ngược chắc chắn từ đầu ra này để nhận lại đối tượng ban đầu.

Đây là một ví dụ đơn giản cho thấy format không nhất thiết là phép biến đổi một-một.

## 4. parse(String) và parse(String, ParsePosition) khác nhau thế nào?

`MessageFormat` có khả năng **parse**: phân tích một chuỗi dựa trên các phần văn bản tĩnh và format element trong pattern để trả về mảng `Object[]`.

Hai API chính:

| API | Khi thành công | Khi thất bại |
| --- | --- | --- |
| `parse(String source)` | Trả `Object[]` lấy từ phần đầu chuỗi được parse | Ném `ParseException` nếu không parse được từ đầu vào |
| `parse(String source, ParsePosition pos)` | Trả `Object[]` và cập nhật `pos.getIndex()` | Trả `null`, cập nhật `pos.getErrorIndex()`; vị trí hiện tại không được tiến qua đoạn lỗi |
| `parseObject(String, ParsePosition)` | Cũng parse ra một `Object[]` nhưng kiểu trả về là `Object` theo hợp đồng `Format` | Trả `null` khi parse thất bại |

Ví dụ đơn giản:

```java
MessageFormat fmt = new MessageFormat(
        "ID={0};", Locale.US);

Object[] values = fmt.parse("ID=42;");
System.out.println(values[0]);
```

Đây là đoạn minh họa trong một phương thức khai báo hoặc xử lý `ParseException`, đã import `MessageFormat`, `ParseException` và `Locale`. Stdout là `42` (một `String` vì placeholder `{0}` không chỉ định subformat).

Nếu pattern dùng `{0,number}`, kết quả parse có thể là đối tượng kiểu `Number` do bộ định dạng số xác định; đừng ép kiểu thành `String` trong mọi trường hợp.

### parse có thể chỉ tiêu thụ tiền tố

Đối với `ParsePosition`:

```java
MessageFormat fmt = new MessageFormat("ID={0};", Locale.US);
String input = "ID=42;tail";
ParsePosition pos = new ParsePosition(0);
Object[] values = fmt.parse(input, pos);

System.out.println(values[0]);
System.out.println(pos.getIndex());
System.out.println(input.length());
```

Đây là đoạn minh họa trong một phương thức, với import `java.text.ParsePosition` và các loại tương ứng. Stdout:

```text
42
6
10
```

Parser khớp phần `ID=42;` (6 ký tự) và **chưa tiêu thụ** `tail`. `parse(String)` cũng **không cam kết** tiêu thụ toàn bộ đầu vào: nó chỉ cố phân tích từ đầu chuỗi.

Nếu ứng dụng yêu cầu toàn bộ input phải khớp, hãy dùng `ParsePosition` rồi kiểm tra:

```java
ParsePosition pos = new ParsePosition(0);
Object[] parsed = fmt.parse(input, pos);
boolean complete = parsed != null && pos.getIndex() == input.length();
```

Đây chỉ là một **điều kiện cần cho việc parse trọn chuỗi**, không đảm bảo dữ liệu khôi phục chính xác đối số gốc; các trường hợp mất thông tin sẽ được trình bày bên dưới.

### Khi parse thất bại

Giả sử pattern `"ID={0};"` nhưng input `"BAD=42;"`. Phần đầu không khớp `ID=`, nên:

```java
ParsePosition pos = new ParsePosition(0);
Object[] parsed = fmt.parse("BAD=42;", pos);

System.out.println(parsed == null);
System.out.println(pos.getIndex());
System.out.println(pos.getErrorIndex());
```

Với `fmt` đã tạo ở ví dụ trên, kết quả là:

```text
true
0
0
```

`getErrorIndex()` cho biết vị trí mà parser phát hiện lỗi (ở đây là ký tự đầu tiên). Khi dùng các subformat phức tạp, chỉ số lỗi không phải báo cáo ngữ nghĩa hoàn chỉnh: nó hỗ trợ chẩn đoán, không thay thế thông báo lỗi do ứng dụng định nghĩa.

Nếu dùng `parse(String)` thay vì overload có `ParsePosition`, cùng trường hợp này sẽ ném `ParseException`. Hãy bắt lỗi và báo lý do phù hợp khi xử lý đầu vào thực.

## 5. Vì sao parse không phải phép đảo ngược đáng tin của format?

Một phép biến đổi được gọi là đảo ngược hoàn toàn nếu từ kết quả cuối có thể xác định duy nhất đầu vào ban đầu. `MessageFormat` không đảm bảo tính chất này vì nó dành cho **hiển thị thông điệp**, còn các format element có thể rút gọn hoặc kết hợp nhiều giá trị thành cùng một chuỗi.

Có năm nhóm vấn đề quan trọng.

### 5.1. Phần tử không xuất hiện trong pattern bị mất

Giả sử mảng gốc có ba phần tử:

```java
Object[] args = {"Ana", "A-42", "hidden"};
MessageFormat mf = new MessageFormat(
        "Hello {0}, order {1}", Locale.US);
String result = mf.format(args);
```

Không có `{2}` trong pattern, nên `hidden` không xuất hiện trong output. Parser không thể tái tạo phần tử đó từ chuỗi. **Mọi phần tử không được biểu diễn đều bị mất thông tin**.

Tương tự, có thể có hai mảng khác nhau cùng tạo một thông điệp vì một số đối số không được sử dụng.

### 5.2. Một đối số xuất hiện nhiều lần: kết quả parse cuối ghi đè

Pattern có thể tái sử dụng `{0}` nhiều lần:

```java
MessageFormat repeated = new MessageFormat("{0}|{0}", Locale.US);
Object[] parsed = repeated.parse("A|B");
System.out.println(Arrays.toString(parsed));
```

Đây là đoạn minh họa trong một phương thức có import `java.util.Arrays`, với xử lý hoặc khai báo `ParseException`. Stdout:

```text
[B]
```

Cùng index `{0}` được parse hai lần; **lần khớp sau có giá trị cuối cùng**. Parser không kiểm chứng rằng `A` và `B` là cùng một giá trị. Đây cũng không phải quy tắc validate dữ liệu lặp; cần kiểm tra riêng nếu văn bản đầu vào yêu cầu hai vị trí giống nhau.

Các format element cùng index nhưng dùng định dạng khác nhau càng dễ làm mất dữ liệu; chỉ một phần của kết quả được trả về theo index.

### 5.3. Dấu phân cách nằm trong dữ liệu gây nhập nhằng

Với pattern:

```text
{0},{1}
```

Nếu `args[0]` là `"a,b"` và `args[1]` là `"c"`, kết quả format là:

```text
a,b,c
```

Nhưng khi parse, dấu phẩy đầu tiên có thể được hiểu là dấu phân tách của pattern:

```java
MessageFormat mf = new MessageFormat("{0},{1}", Locale.US);
String rendered = mf.format(new Object[] {"a,b", "c"});
Object[] restored = mf.parse(rendered);

System.out.println(rendered);
System.out.println(restored[0] + "|" + restored[1]);
```

Kết quả:

```text
a,b,c
a|b,c
```

Đối số gốc là `["a,b", "c"]`, nhưng parse trả `["a", "b,c"]`. Cả hai cách tách đều có thể dẫn tới cùng thông điệp hiển thị. Không thể xác định cách tách mong muốn khi dấu phân cách cũng được phép trong dữ liệu mà không có cơ chế escape/độ dài rõ ràng.

Nếu ứng dụng cần truyền dữ liệu có cấu trúc, hãy dùng JSON hoặc một định dạng dữ liệu có hợp đồng parse rõ ràng; đừng dùng thông điệp bản địa hóa làm protocol.

### 5.4. Subformat làm mất độ chính xác hoặc danh tính kiểu

`{0,number,integer}` có thể tạo chuỗi số đã làm tròn hoặc bỏ chi tiết phần thập phân; `{0,number,#.##}` có thể bỏ các chữ số sau dấu thập phân thứ hai. `{0,date,short}` có thể không giữ giờ/phút/giây và thông tin múi giờ gốc.

Ví dụ, hai số `3.141` và `3.142` khi định dạng theo pattern giới hạn một chữ số thập phân đều có thể thành `3.1`. Phân tích `3.1` không thể biết số nào là đầu vào ban đầu.

`MessageFormat` có thể gọi các subformat trả `Number` hoặc `Date` khi parse. Nhưng **cùng giá trị hiển thị không có nghĩa cùng kiểu dữ liệu hoặc cùng độ chính xác**. Đừng tự giả định đối tượng trả về có chính xác kiểu Java gốc (`BigDecimal`, `Integer`, `Long`, v.v.).

### 5.5. ChoiceFormat gom nhiều giá trị thành một thông điệp

Một pattern `choice` có thể ánh xạ cả một khoảng giá trị sang một nhãn:

```java
MessageFormat choice = new MessageFormat(
        "{0,choice,0#none|1#one|2#many}",
        Locale.US
);

String text = choice.format(new Object[] {999});
Object[] parsed = choice.parse(text);

System.out.println(text);
System.out.println(parsed[0]);
```

Đây là đoạn minh họa trong một phương thức với xử lý `ParseException`. Stdout:

```text
many
2.0
```

Đầu vào `999` trở thành `many`, nhưng khi parse Java trả giá trị giới hạn gắn với nhánh đó (`2.0`), **không phải `999`**. Đây là mất thông tin có chủ đích của phép chọn thông điệp theo khoảng.

`ChoiceFormat` còn có trường hợp pattern lồng tham chiếu như `{0}`. Tài liệu `MessageFormat` cảnh báo parser không xử lý đầy đủ trường hợp đệ quy; không xây hợp đồng parse đối xứng dựa trên pattern choice lồng phức tạp.

## 6. null cũng gây giới hạn đảo ngược

Xét:

```java
MessageFormat plain = new MessageFormat("{0}", Locale.US);

String a = plain.format(new Object[] {null});
String b = plain.format(new Object[] {"null"});

System.out.println(a.equals(b));
```

Kết quả:

```text
true
```

Khi gọi `plain.parse("null")`, với placeholder không có subformat, phần đối số nhận được là chuỗi `"null"`, không thể chứng minh đầu vào trước kia là tham chiếu `null`. Ngược lại, nếu pattern là `"{0,number,integer}"`, lệnh format đối số `null` vẫn có thể tạo văn bản `null`, nhưng parse thông điệp chữ `null` bằng subformat số có thể thất bại.

Nói cách khác:

- **Hiển thị được** không đồng nghĩa **có thể parse về dạng ban đầu**.
- **Parse được** không đồng nghĩa **giữ được nghĩa null**.
- Pattern có kiểu vẫn không tạo bảo đảm round-trip hoàn hảo.

Đối với dữ liệu đầu vào có trạng thái “chưa biết”, “không cung cấp” hay “không áp dụng”, hãy lưu trạng thái đó trong model (ví dụ `Optional` hoặc field trạng thái riêng) và chọn câu thông báo tương ứng. Đừng yêu cầu người dùng hoặc hệ thống khác suy ra trạng thái từ chữ `null` trong UI.

## 7. Ví dụ tổng hợp Java 17+: quan sát các trường hợp biên

Tạo tệp `MessageFormatEdgeDemo.java`:

```java
import java.text.MessageFormat;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.Arrays;
import java.util.Locale;

public class MessageFormatEdgeDemo {
    public static void main(String[] args) throws ParseException {
        Locale locale = Locale.US;

        MessageFormat greeting = new MessageFormat(
                "Hello {0}! State={1}.", locale);

        System.out.println(greeting.format(new Object[] {"Ana"}));
        System.out.println(greeting.format(new Object[] {"Ana", null}));
        System.out.println(greeting.format(new Object[] {}));

        MessageFormat repeated = new MessageFormat("{0}|{0}", locale);
        System.out.println(Arrays.toString(repeated.parse("A|B")));

        MessageFormat ambiguous = new MessageFormat("{0},{1}", locale);
        String message = ambiguous.format(new Object[] {"a,b", "c"});
        Object[] recovered = ambiguous.parse(message);
        System.out.println(message);
        System.out.println(recovered[0] + "|" + recovered[1]);

        MessageFormat choice = new MessageFormat(
                "{0,choice,0#none|1#one|2#many}", locale);
        String text = choice.format(new Object[] {999});
        System.out.println(text + " -> " + choice.parse(text)[0]);

        MessageFormat id = new MessageFormat("ID={0};", locale);
        String input = "ID=42;tail";
        ParsePosition pos = new ParsePosition(0);
        Object[] values = id.parse(input, pos);
        System.out.println("value=" + values[0]
                + ", consumed=" + pos.getIndex()
                + "/" + input.length());

        ParsePosition bad = new ParsePosition(0);
        Object[] failed = id.parse("BAD=42;", bad);
        System.out.println("failed=" + (failed == null)
                + ", errorIndex=" + bad.getErrorIndex());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 MessageFormatEdgeDemo.java
java MessageFormatEdgeDemo
```

Stdout xác định với pattern và `Locale.US` nêu trên:

```text
Hello Ana! State={1}.
Hello Ana! State=null.
Hello {0}! State={1}.
[B]
a,b,c
a|b,c
many -> 2.0
value=42, consumed=6/10
failed=true, errorIndex=0
```

Điểm quan sát:

1. `{1}` còn nguyên khi mảng không có phần tử index 1; khi index đó tồn tại và là `null`, kết quả hiện `null`.
2. `parse("A|B")` chỉ trả phần tử `B` đối với hai lần dùng index 0.
3. `"a,b,c"` bị phân tích thành hai phần `a` và `b,c`, khác mảng gốc.
4. `choice` biến số lớn thành nhãn `many`; parse nhãn nhận lại `2.0`, không phải `999`.
5. `ParsePosition` dừng ở index 6 trong chuỗi dài 10; parse một phần không được tự xem là dữ liệu đầu vào hợp lệ hoàn toàn.
6. `BAD=42;` không khớp văn bản tĩnh `ID=` nên parse trả `null` với `errorIndex=0`.

Đây là ví dụ minh họa hành vi API, không phải đề xuất dùng `MessageFormat.parse` để xử lý dữ liệu từ người dùng trong ứng dụng thực tế.

## 8. Kiểm tra parse thành công một cách đúng đắn

Khi thật sự cần dùng `parse` cho một thông điệp có cấu trúc tương đối đơn giản, nên kiểm tra ít nhất:

1. **Có kết quả:** `parsed != null` (với overload có `ParsePosition`).
2. **Đã tiêu thụ hết input:** `position.getIndex() == input.length()`.
3. **Số lượng và kiểu giá trị:** kết quả gồm các đối số cần thiết và đúng kiểu kỳ vọng; nhớ rằng index không xuất hiện trong pattern không thể khôi phục.
4. **Quy tắc nghiệp vụ:** chẳng hạn số lượng nằm trong miền cho phép, mã ID đúng cú pháp, ngày giờ hợp lệ với yêu cầu thật.
5. **Không có nhập nhằng thiết kế:** pattern có dấu phân cách nằm trong giá trị hay subformat mất thông tin có thể làm parse “thành công” với kết quả sai.

Có thể viết một helper kiểm tra parse toàn phần:

```java
import java.text.MessageFormat;
import java.text.ParsePosition;

public final class CompleteMessageParse {
    private CompleteMessageParse() {}

    public static Object[] parseFully(
            MessageFormat format, String input) {
        if (input == null) {
            throw new IllegalArgumentException("Input is required");
        }

        ParsePosition position = new ParsePosition(0);
        Object[] result = format.parse(input, position);

        if (result == null || position.getIndex() != input.length()) {
            throw new IllegalArgumentException(
                    "Message does not match the full pattern");
        }
        return result;
    }
}
```

Đây là một lớp có thể biên dịch thành `CompleteMessageParse.java`, nhưng không có `main` để chạy trực tiếp. Hàm này giúp **từ chối input không khớp đầy đủ**; nó **không giải quyết** trường hợp dấu phân cách nhập nhằng, mất độ chính xác, đối số lặp hoặc null. Đừng gọi nó là parser tổng quát không mất dữ liệu.

Với đầu vào quan trọng (API, lưu trữ, tài chính, cấu hình), nên dùng schema, parser và kiểu dữ liệu được thiết kế dành riêng cho đầu vào. Thông điệp đã dịch là **định dạng trình bày**, có thể được chỉnh sửa bởi người dịch và thay đổi theo locale; nó không phải giao thức dữ liệu ổn định.

## 9. MessageFormat, ResourceBundle và rủi ro bản địa hóa

Ứng dụng thường tải pattern theo locale:

```properties
# messages.properties
order.status=Order {0} contains {1,number,integer} items.
```

```properties
# messages_vi.properties
order.status=Đơn hàng {0} có {1,number,integer} sản phẩm.
```

Khi code format:

```java
ResourceBundle bundle =
        ResourceBundle.getBundle("messages", locale);
String pattern = bundle.getString("order.status");
String text = new MessageFormat(pattern, locale)
        .format(new Object[] {"A-42", 3});
```

Đây là đoạn minh họa trong một phương thức có `locale` kiểu `Locale`; tệp properties phải nằm trên classpath với base name `messages`.

Có những nguy cơ đặc biệt với missing/null/parse:

- Người dịch có thể vô tình xóa `{1}` hoặc đổi thành `{2}`. Khi chạy, một placeholder bị thiếu có thể hiện nguyên dạng; nếu bỏ placeholder khỏi pattern thì phần tử tương ứng không còn hiển thị.
- Người dịch có thể thay cách đặt dấu câu, thứ tự từ hoặc dấu phân cách. Pattern vẫn format đúng nhưng parse thông điệp dịch có thể đổi cách tách và đối tượng được trả về.
- Dấu nháy đơn `'` và ngoặc nhọn có nghĩa đặc biệt trong cú pháp `MessageFormat`. Một chuỗi dịch chứa apostrophe chưa escape có thể làm placeholder bị coi là văn bản tĩnh. Trong MessageFormat, để biểu diễn nháy đơn literal thường cần `''`; phải test bằng parser thật, không chỉ nhìn file.
- Số/ngày phụ thuộc locale và dữ liệu định dạng. Chuỗi xuất ra từ `Locale.US` không đảm bảo parse đúng bằng `Locale.FRANCE`.
- Đầu vào `null` có thể in thành từ `null` ở bất cứ locale nào; hãy chọn thông điệp fallback riêng phù hợp văn phong ứng dụng.

Vì vậy, pipeline kiểm thử cần đánh giá **pattern từng locale**, số index, subformat, placeholder lặp và các trường hợp missing/null. Đặc biệt không dùng “format thử thành công” làm kiểm tra duy nhất: API có thể chấp nhận đầu vào thiếu và trả placeholder `{n}`.

### Quản lý hợp đồng tham số

Một hợp đồng tốt cho key thông điệp nên ghi:

| Key | Đối số | Ý nghĩa |
| --- | --- | --- |
| `order.status` | `{0}` | Mã đơn hàng, `String`, bắt buộc |
| `order.status` | `{1}` | Số lượng sản phẩm, `Number`, bắt buộc, định dạng integer |
| `account.greeting` | `{0}` | Tên hiển thị, bắt buộc; có nhánh riêng cho khách chưa đăng nhập |

Điều này giúp phát hiện bản dịch lược nhầm index hoặc đưa sai kiểu dữ liệu. Số lượng đối số **không thể được xác thực đầy đủ chỉ bằng việc chạy format** vì missing index không luôn gây exception.

Khi người dùng có thể gửi tên chứa dấu phẩy, dấu nháy hoặc ký tự tùy ý, thông điệp vẫn có thể dùng để hiển thị bình thường; hạn chế parse đảo ngược lại càng quan trọng. Nếu cần đọc dữ liệu máy, giữ đối tượng gốc bên cạnh thông điệp.

## 10. Sai lầm phổ biến và cách sửa

| Sai lầm | Kết quả/rủi ro | Cách đúng |
| --- | --- | --- |
| Nghĩ thiếu `{1}` sẽ ném exception | MessageFormat có thể hiển thị `{1}` nguyên dạng | Validate hợp đồng tham số trước khi format |
| Nghĩ đối số `null` tạo chuỗi rỗng | Java thường in chữ `null` | Chọn thông báo dự phòng hoặc xử lý giá trị thiếu rõ ràng |
| Coi chữ `null` là bằng chứng dữ liệu gốc null | Chuỗi literal `"null"` cũng hiển thị giống vậy | Giữ trạng thái nguồn trong model |
| Dùng `parse(String)` và không kiểm tra phần dư | Parser có thể chỉ đọc một tiền tố | Dùng `ParsePosition` và kiểm tra index cuối |
| Coi parse thành công là đảo ngược chính xác | Dấu phân cách, choice, rounding làm mất dữ liệu | Dùng dữ liệu có cấu trúc cho các thao tác cần round-trip |
| Nhắc `{0}` hai lần rồi tin parser đối chiếu chúng bằng nhau | Lần parse sau ghi đè lần trước | Tự validate tính nhất quán nếu cần |
| Thấy parse trả `Number` rồi cast chắc chắn `Integer` | NumberFormat/ChoiceFormat có thể trả kiểu số khác | Kiểm tra kiểu/giá trị và chuyển đổi có kiểm soát |
| Dùng pattern dịch làm protocol | Người dịch có thể thay dấu câu, thứ tự và ngữ pháp | Tách định dạng giao diện khỏi giao thức dữ liệu |
| Dùng parser MessageFormat để kiểm chứng placeholder trọn vẹn trong bản dịch | Parser không có hợp đồng validate toàn bộ nội dung i18n | Lint pattern và đối chiếu hợp đồng đối số từng locale |
| Không chú ý nháy đơn hoặc `{ }` | Placeholder có thể trở thành literal hoặc lỗi pattern | Kiểm thử pattern thực tế qua MessageFormat |
| Dùng locale mặc định ẩn trong test | Kết quả số/ngày có thể khác CI | Truyền `Locale` tường minh |
| Chia sẻ và sửa cùng một MessageFormat trong nhiều luồng | Format instance có trạng thái mutable, format/parse không được đảm bảo thread-safe | Dùng instance riêng, đồng bộ hợp lý hoặc thiết kế không chia sẻ mutable object |

## 11. Bài tập tự kiểm tra

**Bài 1 — thiếu và null.** Với pattern `"Name={0}; Age={1,number,integer}"`, dự đoán kết quả khi truyền `new Object[] {"Linh"}` và `new Object[] {"Linh", null}`. Vì sao các kết quả khác nhau dù đều “không có tuổi” về mặt nghiệp vụ?

**Bài 2 — parse phần dư.** Với pattern `"ID={0};"` và chuỗi `"ID=42;ignored"`, hãy dùng `ParsePosition` xác định số ký tự được tiêu thụ. Vì sao chỉ kiểm tra `parsed != null` là chưa đủ?

**Bài 3 — repeated index.** Với pattern `"{0}|{0}"`, parse input `"A|B"` trả gì? Có cơ chế tự động nào buộc hai lần xuất hiện của `{0}` phải giống nhau không?

**Bài 4 — dấu phân cách.** Dùng `"{0},{1}"` để format `["x,y", "z"]`. Tại sao parse kết quả không thể chắc chắn tìm được mảng gốc? Nêu một định dạng dữ liệu thích hợp hơn cho trao đổi giữa hai dịch vụ.

**Bài 5 — precision.** Dùng `{0,number,#.#}` với `3.14` và `3.11`. Hai kết quả đều có thể thành `3.1`; khi parse, có thể lấy lại phần thập phân đã bị bỏ không?

**Bài 6 — choice.** Với pattern `"{0,choice,0#none|1#one|2#many}"` và đầu vào `999`, kết quả format/parse thế nào? Vì sao parser trả một mốc của nhánh chứ không trả số ban đầu?

**Bài 7 — bản địa hóa.** Một dịch giả thay `"Order {0}: {1,number,integer} items"` bằng `"Đơn hàng {0}: {2} sản phẩm"`. Hãy chỉ ra hợp đồng đối số nào bị phá vỡ và cách phát hiện qua kiểm thử.

## 12. Ghi nhớ

`MessageFormat` được thiết kế để **tạo thông điệp đã định dạng**, không phải để làm trình mã hóa/giải mã dữ liệu đảo ngược hoàn toàn. Nếu mảng đối số thiếu index được tham chiếu, Java có thể giữ `{n}` nguyên dạng; nếu phần tử tồn tại và là `null`, Java hiển thị văn bản `null`. Hai trường hợp mang ý nghĩa khác nhau và cần xử lý ở lớp nghiệp vụ.

`parse` có thể nhận lại một số đối số theo pattern, nhưng **thành công không đồng nghĩa đúng toàn bộ, càng không đồng nghĩa không mất dữ liệu**. Phải kiểm tra `ParsePosition` khi cần tiêu thụ hết chuỗi, đồng thời nhận diện các trường hợp nhập nhằng, index lặp, subformat làm tròn, choice, dữ liệu bị lược và null. Với dữ liệu phải giữ nguyên, hãy truyền/lưu **đối tượng nguồn có cấu trúc**, dùng `MessageFormat` ở lớp trình bày, và kiểm thử mọi pattern đã dịch theo hợp đồng tham số.

Tài liệu API: [`MessageFormat` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html), [`ParsePosition` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html).
