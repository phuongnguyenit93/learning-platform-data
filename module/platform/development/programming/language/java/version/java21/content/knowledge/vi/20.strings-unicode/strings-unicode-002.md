# String.splitWithDelimiters và giữ lại dấu phân tách

`String.splitWithDelimiters(String regex, int limit)` là API được bổ sung trong Java 21 để tách chuỗi theo biểu thức chính quy (regular expression) và giữ lại cả các đoạn văn bản lẫn dấu phân tách khớp với biểu thức đó. Kết quả là một mảng `String[]` có các đoạn nội dung xen kẽ với delimiter theo đúng thứ tự xuất hiện trong chuỗi đầu vào.

Khác với `split(regex, limit)`, vốn loại bỏ delimiter khỏi kết quả, `splitWithDelimiters` giữ delimiter như một phần tử riêng. Điều này hữu ích khi phân tích cú pháp đơn giản, tô màu cú pháp, hiển thị dấu phân tách, xử lý log hoặc cần dựng lại chuỗi từ các token mà không phải tìm delimiter lần nữa.

## 1. Cú pháp và ý nghĩa

Cú pháp trong Java 21:

```java
String[] parts = input.splitWithDelimiters(regex, limit);
```

Tham số:

- `input`: chuỗi cần tách; đây là đối tượng String gọi phương thức.
- `regex`: biểu thức chính quy mô tả delimiter cần tìm.
- `limit`: giới hạn số lần áp dụng biểu thức và ảnh hưởng đến số phần tử kết quả.

Mảng trả về chứa các đoạn theo thứ tự:

1. Đoạn nội dung trước delimiter đầu tiên.
2. Toàn bộ chuỗi con khớp với delimiter.
3. Đoạn nội dung giữa delimiter hiện tại và delimiter tiếp theo.
4. Tiếp tục xen kẽ nội dung và delimiter.
5. Đoạn cuối cùng sau delimiter cuối, nếu có.

Phần tử cuối cùng luôn là phần nội dung còn lại và không có delimiter theo sau. Nếu regex không khớp ở bất kỳ vị trí nào, mảng chỉ có một phần tử là chuỗi ban đầu.

Ví dụ:

```java
import java.util.Arrays;

class Main {
    public static void main(String[] args) {
        String input = "red,green;blue";

        String[] parts = input.splitWithDelimiters("[,;]", -1);

        System.out.println(Arrays.toString(parts));
        // [red, ,, green, ;, blue]
    }
}
```

Kết quả có năm phần tử: `"red"`, `","`, `"green"`, `";"` và `"blue"`. Dấu phẩy và dấu chấm phẩy được giữ lại thành token riêng.

## 2. So sánh split và splitWithDelimiters

Hai phương thức đều tách chuỗi bằng regex, nhưng khác nhau ở việc có giữ delimiter trong mảng kết quả hay không.

```java
String input = "one,two;three";

String[] withoutDelimiters = input.split("[,;]", -1);
String[] withDelimiters = input.splitWithDelimiters("[,;]", -1);
```

| Phương thức | Kết quả |
|---|---|
| `split("[,;]", -1)` | `["one", "two", "three"]` |
| `splitWithDelimiters("[,;]", -1)` | `["one", ",", "two", ";", "three"]` |

Dùng `split` khi chỉ cần các trường dữ liệu. Dùng `splitWithDelimiters` khi delimiter cũng mang ý nghĩa cần được giữ lại, ví dụ dấu câu, toán tử, ký hiệu hoặc dấu phân cách trong một định dạng văn bản.

Không nên chọn `splitWithDelimiters` chỉ vì nó mới hơn. Nếu ứng dụng không cần delimiter, `split` tạo kết quả đơn giản hơn và tránh phải bỏ qua các phần tử delimiter ở bước xử lý sau.

## 3. Regex quyết định delimiter nào được giữ lại

Tham số `regex` là biểu thức chính quy, không phải chuỗi delimiter literal. Phần tử delimiter trong kết quả là toàn bộ chuỗi con khớp với regex tại vị trí đó.

Ví dụ dùng một hoặc nhiều dấu hai chấm làm delimiter:

```java
String input = "name:::value::status";

String[] parts = input.splitWithDelimiters(":+", -1);

// ["name", ":::", "value", "::", "status"]
```

Regex `:+` khớp một hoặc nhiều dấu hai chấm liên tiếp. Vì vậy, ba dấu hai chấm liên tiếp được giữ thành một token `":::"`, không bị tách thành ba token riêng.

### 3.1. Delimiter gồm nhiều ký tự

Có thể dùng regex mô tả delimiter dài hơn một ký tự:

```java
String input = "A<->B<->C";

String[] parts = input.splitWithDelimiters("<->", -1);

// ["A", "<->", "B", "<->", "C"]
```

Toàn bộ chuỗi `"<->"` được giữ lại trong mỗi lần khớp.

### 3.2. Dùng literal delimiter an toàn

Một số ký tự có ý nghĩa đặc biệt trong regex, chẳng hạn dấu chấm `.`, dấu cộng `+`, dấu ngoặc vuông và dấu ngoặc tròn. Nếu muốn tách theo chính ký tự đó, cần escape hoặc quote ký tự.

Ví dụ dấu chấm literal:

```java
String version = "21.0.2";

String[] parts = version.splitWithDelimiters("\\.", -1);

// ["21", ".", "0", ".", "2"]
```

Nếu delimiter đến từ biến hoặc dữ liệu người dùng, có thể dùng `Pattern.quote` để biến chuỗi đó thành regex literal:

```java
import java.util.regex.Pattern;

String delimiter = ".*";
String input = "left.*middle.*right";

String[] parts = input.splitWithDelimiters(
        Pattern.quote(delimiter),
        -1
);

// ["left", ".*", "middle", ".*", "right"]
```

Cách này tránh việc các ký tự regex trong delimiter đầu vào bị diễn giải thành toán tử hoặc mẫu đặc biệt.

### 3.3. Regex có khoảng trắng trong delimiter

Regex quyết định chính xác phần nào được xem là delimiter. Nếu mẫu bao gồm khoảng trắng xung quanh dấu phẩy, các khoảng trắng đó cũng nằm trong token delimiter:

```java
String input = "alpha , beta , gamma";

String[] parts = input.splitWithDelimiters("\\s*,\\s*", -1);

// ["alpha", " , ", "beta", " , ", "gamma"]
```

Nếu muốn giữ khoảng trắng như nội dung riêng, hãy dùng regex chỉ khớp dấu phẩy:

```java
String[] parts = input.splitWithDelimiters(",", -1);

// ["alpha ", ",", " beta ", ",", " gamma"]
```

Vì vậy, khi thiết kế regex, cần quyết định delimiter có bao gồm khoảng trắng hoặc ký tự lân cận hay không.

## 4. Quy tắc limit

Tham số `limit` điều khiển số lần regex được áp dụng. Đây là điểm quan trọng vì `splitWithDelimiters` giữ cả delimiter nên số phần tử kết quả có thể nhiều hơn số lần tách.

| Giá trị limit | Cách hoạt động |
|---|---|
| `limit > 0` | Regex được áp dụng tối đa `limit - 1` lần; mảng có tối đa `2 * limit - 1` phần tử; phần tử cuối chứa toàn bộ nội dung còn lại |
| `limit == 0` | Tách nhiều lần nhất có thể; các chuỗi rỗng ở cuối kết quả, gồm token nội dung hoặc delimiter rỗng, bị loại bỏ |
| `limit < 0` | Tách nhiều lần nhất có thể; giữ cả các chuỗi rỗng ở cuối kết quả |

Ví dụ với chuỗi:

```java
String input = "boo:::and::foo";
```

Và regex:

```java
String regex = ":+";
```

Các kết quả tiêu biểu:

| Lệnh | Kết quả |
|---|---|
| `input.splitWithDelimiters(regex, 2)` | `["boo", ":::", "and::foo"]` |
| `input.splitWithDelimiters(regex, 5)` | `["boo", ":::", "and", "::", "foo"]` |
| `input.splitWithDelimiters(regex, -1)` | `["boo", ":::", "and", "::", "foo"]` |

Với `limit = 2`, regex chỉ được áp dụng tối đa một lần. Mảng có thể có ba phần tử: đoạn trước delimiter, delimiter và phần còn lại. Đây là lý do giới hạn số phần tử của phương thức là `2 * limit - 1`, thay vì `limit` như `split`.

### 4.1. limit bằng 0 và số phần tử rỗng ở cuối

Giả sử chuỗi kết thúc bằng delimiter:

```java
String input = "a,b,";
```

Kết quả:

```java
input.splitWithDelimiters(",", 0);
// ["a", ",", "b", ","]

input.splitWithDelimiters(",", -1);
// ["a", ",", "b", ",", ""]
```

Với `limit = 0`, phần tử rỗng ở cuối bị loại bỏ. Với `limit = -1`, phần tử rỗng đó được giữ lại. Token delimiter cuối cùng vẫn được giữ vì nó không phải chuỗi rỗng.

Nếu cần giữ chính xác cả trường rỗng cuối cùng để phân biệt dữ liệu thiếu với dữ liệu không có, hãy dùng `limit = -1`.

### 4.2. limit bằng 1

Với `limit = 1`, số lần áp dụng regex tối đa là 0:

```java
String input = "a,b,c";

String[] parts = input.splitWithDelimiters(",", 1);

// ["a,b,c"]
```

Kết quả là toàn bộ chuỗi đầu vào trong một phần tử. Không có delimiter nào được tìm và tách.

## 5. Delimiter liên tiếp và phần nội dung rỗng

Khi hai delimiter xuất hiện liền nhau, đoạn nội dung nằm giữa chúng có độ dài bằng 0. `splitWithDelimiters` giữ đoạn rỗng này khi limit cho phép.

```java
String input = "a,,b";

String[] parts = input.splitWithDelimiters(",", -1);

// ["a", ",", "", ",", "b"]
```

Phần tử rỗng ở giữa là kết quả có ý nghĩa: nó cho biết hai dấu phẩy không có nội dung nào nằm giữa.

Nếu ứng dụng loại bỏ mọi chuỗi rỗng sau khi tách, cần cân nhắc vì có thể làm mất thông tin về trường trống hoặc delimiter liên tiếp.

### 5.1. Delimiter ở đầu chuỗi

Nếu regex khớp một delimiter có độ dài dương ngay tại đầu chuỗi, kết quả có một phần tử rỗng ở đầu trước delimiter:

```java
String input = ",alpha,beta";

String[] parts = input.splitWithDelimiters(",", -1);

// ["", ",", "alpha", ",", "beta"]
```

Phần tử rỗng biểu thị rằng chuỗi bắt đầu bằng delimiter, tức không có nội dung trước nó.

Một regex khớp độ dài bằng 0 tại đầu chuỗi có quy tắc khác: nó không tạo phần tử nội dung rỗng ở đầu và cũng không tạo token delimiter rỗng. Đây là quy tắc quan trọng khi dùng lookahead, lookbehind hoặc các regex zero-width.

## 6. Xử lý mảng kết quả theo cặp nội dung và delimiter

Với kết quả thông thường, các phần tử xen kẽ giữa nội dung và delimiter. Khi không có delimiter ở đầu chuỗi, chỉ số chẵn thường là nội dung và chỉ số lẻ là delimiter:

```java
String input = "A+B-C";
String[] parts = input.splitWithDelimiters("[+-]", -1);

for (int i = 0; i < parts.length; i++) {
    if (i % 2 == 0) {
        System.out.println("Nội dung: " + parts[i]);
    } else {
        System.out.println("Delimiter: " + parts[i]);
    }
}
```

Kết quả được phân loại:

- Nội dung: `A`
- Delimiter: `+`
- Nội dung: `B`
- Delimiter: `-`
- Nội dung: `C`

Nếu delimiter khớp ngay ở đầu chuỗi, phần tử đầu tiên là nội dung rỗng và delimiter đầu tiên nằm ở chỉ số 1. Vì vậy, quy tắc xen kẽ vẫn giữ nguyên: chỉ số chẵn là đoạn nội dung, chỉ số lẻ là delimiter, miễn là kết quả được tạo theo quy tắc positive-width match của API.

Không nên giả định rằng mảng luôn có số phần tử lẻ. Nếu chuỗi kết thúc bằng delimiter và dùng `limit = -1`, phần tử rỗng cuối cùng cũng được giữ, làm số phần tử có thể thay đổi theo dữ liệu đầu vào.

## 7. Dùng Pattern khi cần tách nhiều chuỗi theo cùng regex

Nếu phải áp dụng cùng một biểu thức chính quy cho nhiều chuỗi, có thể biên dịch regex một lần thành `Pattern`, sau đó gọi `Pattern.splitWithDelimiters`:

```java
import java.util.regex.Pattern;

class Main {
    private static final Pattern SEPARATOR =
            Pattern.compile("([,;])");

    static String[] tokenize(String input) {
        return SEPARATOR.splitWithDelimiters(input, -1);
    }
}
```

`Pattern.splitWithDelimiters(CharSequence input, int limit)` có semantics tương ứng với `String.splitWithDelimiters`. Cách này giúp tái sử dụng đối tượng Pattern thay vì biên dịch regex lại cho từng chuỗi.

Trong ví dụ, dấu ngoặc capture quanh `[,;]` không làm nhóm con trở thành các phần tử riêng trong mảng. Token delimiter là toàn bộ chuỗi con khớp với pattern. Nếu pattern khớp cả nhiều ký tự, toàn bộ phần khớp được giữ làm một token.

## 8. Tái tạo chuỗi ban đầu từ kết quả

Vì kết quả chứa cả đoạn nội dung lẫn delimiter theo đúng thứ tự, có thể nối các phần tử lại để thu được chuỗi đầu vào:

```java
String input = "alpha::beta:::gamma";

String[] parts = input.splitWithDelimiters(":+", -1);
String reconstructed = String.join("", parts);

System.out.println(reconstructed.equals(input)); // true
```

Kết quả tái tạo đúng khi dùng limit âm để giữ cả phần nội dung rỗng ở cuối. Với `limit = 0`, các chuỗi rỗng cuối bị loại bỏ, nên nếu chuỗi gốc kết thúc bằng delimiter, việc nối kết quả có thể không còn tái tạo đúng chuỗi ban đầu.

Khả năng tái tạo hữu ích cho bộ phân tích văn bản đơn giản, formatter hoặc công cụ cần sửa một số token nhưng vẫn giữ delimiter gốc. Nếu thay đổi token nội dung, chỉ cần giữ nguyên các token delimiter còn lại rồi ghép theo thứ tự.

## 9. Giới hạn khi dùng regex để phân tích văn bản

`splitWithDelimiters` là công cụ tách theo regex, không phải parser tổng quát cho mọi định dạng.

Ví dụ, tách CSV bằng dấu phẩy đơn giản có thể sai khi trường dữ liệu chứa dấu phẩy bên trong dấu ngoặc kép:

```text
id,name,description
1,Alice,"Engineer, Platform"
```

Regex tách theo dấu phẩy sẽ coi dấu phẩy trong `"Engineer, Platform"` là delimiter, dù trong CSV nó thuộc nội dung trường. Với CSV, JSON, ngôn ngữ lập trình hoặc định dạng có escape/nesting, nên dùng parser hiểu đầy đủ grammar của định dạng.

Ngoài ra:

- Regex delimiter có thể khớp nhiều ký tự hoặc zero-width; cần hiểu chính xác mẫu trước khi xử lý kết quả.
- Một regex không hợp lệ sẽ gây `PatternSyntaxException`.
- `splitWithDelimiters` không tự chuẩn hóa Unicode, không bỏ dấu và không phân đoạn văn bản thành grapheme cluster.
- Nếu delimiter được lấy từ dữ liệu người dùng, dùng `Pattern.quote` khi ý định là khớp literal.
- Với dữ liệu lớn hoặc regex phức tạp, cần cân nhắc chi phí biên dịch regex và số lượng token được tạo ra.

## 10. Các lỗi thường gặp

| Vấn đề | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng `split` nhưng mong delimiter xuất hiện trong kết quả | `split` loại delimiter khỏi mảng | Dùng `splitWithDelimiters` |
| Dùng delimiter literal như regex mà không escape | Ký tự có ý nghĩa đặc biệt trong regex | Escape ký tự hoặc dùng `Pattern.quote` |
| Cho rằng limit là số phần tử tối đa | Với splitWithDelimiters, delimiter cũng là phần tử | Nhớ giới hạn tối đa là `2 * limit - 1` khi limit dương |
| Mất trường rỗng cuối | Dùng `limit = 0` | Dùng `limit = -1` nếu cần giữ trailing empty strings |
| Bỏ qua chuỗi rỗng giữa hai delimiter | Không kiểm tra các token rỗng | Giữ và xử lý chúng theo quy tắc dữ liệu |
| Coi nhóm capture là các token riêng | API giữ toàn bộ delimiter match | Dùng parser hoặc xử lý riêng nếu cần từng nhóm |
| Dùng regex đơn giản để parse CSV/JSON | Định dạng có quote, escape hoặc cấu trúc lồng nhau | Dùng parser chuyên dụng |

## 11. Hướng dẫn sử dụng trong Java 21

Khi cần giữ delimiter trong quá trình tách chuỗi, có thể áp dụng các nguyên tắc sau:

1. Dùng `splitWithDelimiters(regex, limit)` khi delimiter cần tồn tại trong mảng kết quả.
2. Viết regex sao cho toàn bộ phần khớp đúng bằng delimiter mà ứng dụng muốn giữ.
3. Dùng `limit = -1` nếu cần bảo toàn cả các token rỗng ở cuối.
4. Dùng `limit = 0` khi muốn tách tối đa nhưng bỏ các chuỗi rỗng cuối.
5. Dùng `Pattern.quote` khi delimiter là dữ liệu literal thay vì regex.
6. Xử lý chuỗi rỗng giữa các delimiter và delimiter ở đầu chuỗi một cách có chủ đích.
7. Chọn parser chuyên dụng nếu định dạng có quy tắc quote, escape hoặc nesting phức tạp.
8. Dùng `Pattern.splitWithDelimiters` khi cần tái sử dụng cùng regex cho nhiều chuỗi.

`String.splitWithDelimiters` là API chính thức từ Java 21. Nó mở rộng khả năng tách chuỗi bằng regex bằng cách giữ lại delimiter như token riêng, giúp xử lý văn bản có cấu trúc dễ dàng hơn khi cần bảo toàn thứ tự và ký hiệu phân cách. Hiểu rõ quy tắc limit, chuỗi rỗng và cách regex khớp sẽ giúp tránh mất dữ liệu hoặc phân loại nhầm token.

## Tài liệu tham khảo

- [Oracle Java SE 21 API — String.splitWithDelimiters](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html#splitWithDelimiters(java.lang.String,int))
- [Oracle Java SE 21 API — Pattern.splitWithDelimiters](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html#splitWithDelimiters(java.lang.CharSequence,int))
