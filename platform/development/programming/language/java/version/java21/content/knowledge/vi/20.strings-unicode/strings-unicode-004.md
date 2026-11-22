# Ảnh hưởng của limit và kết quả rỗng khi tách chuỗi

Trong Java, `String.split(regex, limit)` tách chuỗi theo các vị trí khớp với biểu thức chính quy `regex`. Tham số `limit` quyết định số lần áp dụng regex và cách giữ hoặc loại bỏ các phần tử rỗng ở cuối kết quả. Đây là khác biệt quan trọng khi đọc CSV đơn giản, tách đường dẫn, xử lý dòng văn bản hoặc phân tích dữ liệu Unicode.

Ba giá trị `limit` có ý nghĩa khác nhau:

- `limit > 0`: tách tối đa `limit - 1` lần; phần còn lại được giữ trong phần tử cuối.
- `limit == 0`: tách nhiều nhất có thể rồi loại bỏ các phần tử rỗng ở cuối mảng.
- `limit < 0`: tách nhiều nhất có thể và giữ lại cả các phần tử rỗng ở cuối.

Không có giá trị `limit` nào có nghĩa là “giữ tối đa N phần tử không rỗng”. `limit` kiểm soát số lần tách, và với giá trị 0 còn quy định việc loại bỏ các kết quả rỗng ở cuối.

## 1. split() nhận regex, không nhận delimiter dạng ký tự thông thường

`String.split(String regex)` tương đương với `split(regex, 0)`. Tham số đầu tiên là regular expression, vì vậy một số ký tự có ý nghĩa đặc biệt trong regex.

```java
String csv = "An,Bình,Chi";
String[] names = csv.split(",");

System.out.println(Arrays.toString(names));
// [An, Bình, Chi]
```

Với dấu phẩy, regex `,` cũng chính là dấu phân cách mong muốn. Nhưng dấu chấm `.` là ký hiệu regex khớp với một ký tự bất kỳ (ngoại trừ một số line terminator theo chế độ mặc định), không phải dấu chấm literal:

```java
String version = "21.0.2";

String[] wrong = version.split(".");
String[] correct = version.split("\\.");

System.out.println(Arrays.toString(correct));
// [21, 0, 2]
```

Với delimiter literal bất kỳ, dùng `Pattern.quote()` để chuyển toàn bộ chuỗi delimiter thành một regex literal an toàn:

```java
String text = "red|green|blue";
String delimiter = "|";

String[] colors = text.split(Pattern.quote(delimiter), -1);
System.out.println(Arrays.toString(colors));
// [red, green, blue]
```

Nếu delimiter là một regex có chủ đích, hãy viết regex tương ứng. Nếu delimiter là dữ liệu do người dùng cung cấp, không ghép trực tiếp vào regex mà chưa quote hoặc kiểm tra; chuỗi đặc biệt có thể làm thay đổi cách tách hoặc gây lỗi cú pháp regex.

## 2. limit dương: giới hạn số lần tách

Khi `limit` là số dương, regex được áp dụng tối đa `limit - 1` lần. Mảng kết quả có tối đa `limit` phần tử; phần tử cuối chứa toàn bộ phần còn lại sau lần tách cuối cùng, kể cả khi phần đó vẫn chứa delimiter.

```java
String value = "A,B,C,D";

System.out.println(Arrays.toString(value.split(",", 1)));
// [A,B,C,D]

System.out.println(Arrays.toString(value.split(",", 2)));
// [A, B,C,D]

System.out.println(Arrays.toString(value.split(",", 3)));
// [A, B, C,D]

System.out.println(Arrays.toString(value.split(",", 4)));
// [A, B, C, D]
```

`limit = 1` không thực hiện lần tách nào. `limit = 2` chỉ tách ở dấu phẩy đầu tiên; phần còn lại `B,C,D` được giữ nguyên trong phần tử thứ hai.

Limit dương cũng giữ phần tử rỗng ở cuối nếu lần tách tạo ra chúng:

```java
String value = "A,B,,";

System.out.println(Arrays.toString(value.split(",", 3)));
// [A, B, ,]

System.out.println(Arrays.toString(value.split(",", 4)));
// [A, B, , ]
```

Để tránh cách hiển thị khó đọc của `Arrays.toString()` với chuỗi rỗng, có thể in độ dài và đặt dấu ngoặc cho từng token:

```java
static void printTokens(String[] tokens) {
    System.out.println("length = " + tokens.length);
    for (int i = 0; i < tokens.length; i++) {
        System.out.printf("[%d] = <%s>%n", i, tokens[i]);
    }
}
```

Khi phân tích một dòng có số cột cố định, limit dương có thể giữ phần cuối như một trường duy nhất. Ví dụ `line.split(",", 3)` tách tối đa hai dấu phẩy và để toàn bộ phần còn lại trong cột thứ ba. Nếu cần kiểm tra chính xác số cột, phải kiểm tra `tokens.length` và quy tắc định dạng của dữ liệu.

## 3. limit bằng 0: loại bỏ phần tử rỗng ở cuối

Khi `limit == 0`, Java áp dụng regex nhiều nhất có thể rồi loại bỏ các chuỗi rỗng ở cuối mảng. Các chuỗi rỗng nằm giữa những token không rỗng vẫn được giữ.

```java
String value = "A,B,,C,,";

String[] tokens = value.split(",", 0);
System.out.println(Arrays.toString(tokens));
// [A, B, , C]
```

Hai dấu phẩy liên tiếp giữa `B` và `C` tạo ra một trường rỗng ở giữa, nên trường đó vẫn có trong kết quả. Các dấu phẩy cuối tạo ra token rỗng ở cuối và những token này bị loại bỏ.

Overload không truyền `limit` có cùng hành vi:

```java
String[] a = "A,B,,".split(",");
String[] b = "A,B,,".split(",", 0);

System.out.println(Arrays.equals(a, b)); // true
```

### Khi mọi token đều rỗng, mảng có thể không còn phần tử

Một trường hợp dễ gây lỗi là chuỗi chỉ gồm delimiter:

```java
String value = ",,";

String[] tokens = value.split(",", 0);
System.out.println(tokens.length); // 0
System.out.println(Arrays.toString(tokens)); // []
```

Mỗi lần tách tạo ra một chuỗi rỗng; tất cả đều nằm ở cuối kết quả nên bị loại bỏ. Kết quả là mảng có độ dài 0, không phải mảng có một phần tử là chuỗi rỗng.

Vì vậy, không nên truy cập `tokens[0]` ngay sau `split(regex)` nếu đầu vào có thể rỗng hoặc chỉ chứa delimiter. Hãy kiểm tra độ dài trước:

```java
String[] tokens = input.split(",");

if (tokens.length == 0) {
    System.out.println("Không có token sau khi tách");
} else {
    System.out.println("Token đầu tiên: " + tokens[0]);
}
```

## 4. limit âm: giữ tất cả phần tử rỗng ở cuối

Khi `limit < 0`, Java áp dụng regex nhiều nhất có thể và giữ các token rỗng ở cuối. Đây là lựa chọn phù hợp khi vị trí delimiter cuối cùng mang ý nghĩa dữ liệu, chẳng hạn một dòng CSV có trường cuối bị bỏ trống.

```java
String value = "A,B,,";

String[] tokens = value.split(",", -1);
System.out.println(tokens.length); // 4

for (String token : tokens) {
    System.out.println("<" + token + ">");
}
// <A>
// <B>
// <>
// <>
```

Hai dấu phẩy cuối biểu diễn hai trường rỗng ở cuối và cả hai đều được giữ. So sánh ba chế độ trên cùng một chuỗi:

```java
String value = "A,B,,";

System.out.println("limit 0:");
printTokens(value.split(",", 0));
// length = 2; <A>, <B>

System.out.println("limit -1:");
printTokens(value.split(",", -1));
// length = 4; <A>, <B>, <>, <>

System.out.println("limit 3:");
printTokens(value.split(",", 3));
// length = 3; <A>, <B>, <,>
```

| Biểu thức | Số lần tách tối đa | Token rỗng ở cuối |
|---|---:|---|
| `split(",", 0)` | Không giới hạn bởi limit | Bị loại bỏ |
| `split(",", -1)` | Không giới hạn bởi limit | Được giữ |
| `split(",", 3)` | 2 | Được giữ trong phần còn lại |

Nếu định dạng đầu vào có số trường cố định, dùng `-1` thường an toàn hơn khi muốn phát hiện trường cuối bị thiếu. Nếu dùng limit 0, thông tin về các trường rỗng ở cuối sẽ bị mất.

## 5. Phân biệt chuỗi rỗng với mảng kết quả rỗng

Hai trạng thái sau khác nhau:

- `new String[] { "" }`: mảng có một token; token đó là chuỗi rỗng.
- `new String[0]`: mảng không có token nào.

Ví dụ:

```java
String[] oneEmptyToken = "".split(",", -1);
String[] noTokens = ",,".split(",", 0);

System.out.println(oneEmptyToken.length); // 1
System.out.println(noTokens.length);      // 0
```

Với chuỗi rỗng và regex delimiter không khớp, `split` trả về một phần tử chứa chính chuỗi đầu vào. Ngược lại, nếu đầu vào chỉ có các delimiter và `limit` bằng 0, mọi token rỗng cuối cùng có thể bị loại bỏ, tạo ra mảng rỗng.

Khi xử lý dữ liệu, hãy phân biệt ít nhất ba trường hợp: đầu vào không có ký tự; đầu vào có delimiter nhưng không có nội dung giữa các delimiter; và đầu vào có token không rỗng. Nếu nghiệp vụ cần phân biệt “không có trường” với “có trường nhưng giá trị rỗng”, phải chọn limit và quy tắc xác thực phù hợp.

## 6. Chuỗi rỗng ở đầu và quy tắc zero-width match

Nếu regex khớp ở đầu chuỗi bằng một match có độ dài dương, `split` có thể tạo token rỗng ở đầu. Nhưng nếu match ở đầu là zero-width (khớp mà không tiêu thụ ký tự nào), Java không tạo token rỗng ở đầu chỉ vì match đó.

```java
String value = ",A,B";
System.out.println(Arrays.toString(value.split(",", -1)));
// [, A, B]
```

Dấu phẩy ở vị trí đầu là match có độ dài một ký tự, nên token đầu tiên là chuỗi rỗng.

Ngược lại, regex zero-width như lookahead có thể xác định ranh giới mà không tiêu thụ ký tự:

```java
String value = "AB";
String[] tokens = value.split("(?=B)", -1);

System.out.println(Arrays.toString(tokens));
// [A, B]
```

Lookahead `(?=B)` khớp ngay trước `B` nhưng không tiêu thụ `B`; nó không tạo token rỗng ở đầu chuỗi. Khi dùng regex phức tạp hoặc lookaround, hãy kiểm tra vị trí và độ dài match thay vì suy luận chỉ từ hình thức delimiter.

## 7. Chọn limit theo định dạng dữ liệu

| Dữ liệu | Cách tách thường phù hợp | Lý do |
|---|---|---|
| Danh sách đơn giản, không quan tâm trường rỗng ở cuối | `split(regex)` hoặc `split(regex, 0)` | Cú pháp ngắn và bỏ token rỗng cuối |
| CSV đơn giản cần giữ trường rỗng cuối | `split(",", -1)` | Không làm mất cột cuối trống |
| Chỉ muốn tách một số phần đầu, phần còn lại giữ nguyên | `split(regex, positiveLimit)` | Tối đa `limit - 1` lần tách |
| Chuỗi chỉ chứa delimiter và cần phát hiện trường rỗng | `split(regex, -1)` | Kết quả giữ các token rỗng |
| Giao thức yêu cầu đúng số trường | Limit dương hoặc `-1`, sau đó kiểm tra số lượng | Có thể phát hiện thiếu hoặc thừa trường theo hợp đồng |

`String.split` chỉ là công cụ tách theo regex; nó không phải parser CSV hoàn chỉnh. CSV thực tế có thể có dấu phẩy bên trong dấu nháy, escape quote, xuống dòng bên trong trường và quy tắc encoding. Với định dạng CSV cần tuân thủ đầy đủ, hãy dùng parser CSV chuyên dụng thay vì `split(",", -1)`.

## 8. Tách theo dấu phân cách Unicode

`String.split` nhận regex của Java, vì vậy có thể dùng các lớp ký tự và mẫu line break hỗ trợ Unicode. Điều này hữu ích khi xử lý văn bản có ký tự xuống dòng hoặc khoảng trắng ngoài ASCII.

### Tách dòng bằng `\R`

Trong regex Java, `\R` khớp một Unicode line-break sequence. Nó xử lý các dạng xuống dòng phổ biến như LF (`\n`), CRLF (`\r\n`), CR (`\r`) và các line separator Unicode:

```java
String text = "Dòng 1\r\nDòng 2\u2028Dòng 3\u2029Dòng 4";
String[] lines = text.split("\\R", -1);

System.out.println(Arrays.toString(lines));
// [Dòng 1, Dòng 2, Dòng 3, Dòng 4]
```

CRLF được xem là một line-break sequence, không tạo hai dòng rỗng liên tiếp. Dùng limit `-1` nếu muốn giữ dòng cuối rỗng khi văn bản kết thúc bằng line break.

### Tách theo khoảng trắng Unicode

Trong Java regex, `\s` mặc định tương ứng với nhóm whitespace ASCII. Nếu cần lớp whitespace theo Unicode, bật `UNICODE_CHARACTER_CLASS` bằng embedded flag `(?U)` hoặc cờ `Pattern.UNICODE_CHARACTER_CLASS`:

```java
String text = "Java\u00A021\u2003Unicode";

String[] words = text.split("(?U)\\s+");
System.out.println(Arrays.toString(words));
// [Java, 21, Unicode]
```

Trong ví dụ, `\u00A0` là NO-BREAK SPACE và `\u2003` là EM SPACE. Nếu chỉ muốn tách khoảng trắng ngang, regex `\h+` là một lựa chọn phù hợp; nếu muốn tách line break, dùng `\R` thay vì tự liệt kê từng ký tự xuống dòng.

### Unicode không làm thay đổi quy tắc limit

Việc delimiter là dấu phẩy ASCII, khoảng trắng Unicode hay line-break Unicode không thay đổi quy tắc của `limit`. Các token rỗng ở cuối vẫn bị loại khi limit bằng 0 và được giữ khi limit âm hoặc dương. Hãy chọn regex để nhận diện ranh giới, sau đó chọn limit theo yêu cầu giữ trường rỗng.

## 9. Ví dụ xử lý record có trường cuối rỗng

Giả sử một dòng dữ liệu nội bộ có ba trường: mã đơn hàng, trạng thái và ghi chú. Ghi chú có thể rỗng:

```java
record OrderRow(String id, String status, String note) { }

static OrderRow parseOrderRow(String line) {
    String[] fields = line.split("\\|", -1);

    if (fields.length != 3) {
        throw new IllegalArgumentException(
                "Cần đúng 3 trường, nhận được " + fields.length);
    }

    return new OrderRow(fields[0], fields[1], fields[2]);
}

OrderRow row = parseOrderRow("ORD-42|PAID|");
System.out.println(row.note().isEmpty()); // true
```

Nếu dùng `line.split("\\|")` với limit mặc định bằng 0, trường `note` rỗng ở cuối bị loại bỏ. Mảng chỉ còn hai phần tử và kiểm tra số trường sẽ thất bại. Dùng `-1` giữ đủ ba trường, cho phép phân biệt một ghi chú rỗng với một dòng thiếu delimiter cuối.

Ví dụ này dùng delimiter `|` như format đơn giản do ứng dụng kiểm soát. Nếu dữ liệu có escaping, quote hoặc delimiter xuất hiện bên trong trường, cần một parser theo grammar của định dạng thay vì split trực tiếp.

## 10. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng `split(",")` khi cần giữ trường cuối rỗng | Token rỗng cuối bị loại | Dùng `split(",", -1)` |
| Nghĩ `limit = 2` trả tối đa hai token không rỗng | Phần tử thứ hai có thể chứa delimiter còn lại và token rỗng | Hiểu limit là số lần tách tối đa cộng một phần còn lại |
| Gọi `tokens[0]` mà không kiểm tra độ dài | `ArrayIndexOutOfBoundsException` khi kết quả là mảng rỗng | Kiểm tra `tokens.length` |
| Dùng `split(".")` để tách dấu chấm | Regex `.` khớp ký tự bất kỳ | Dùng `split("\\.")` hoặc `Pattern.quote(".")` |
| Dùng `split("\\s+")` nhưng mong mọi whitespace Unicode | Một số whitespace ngoài ASCII không được khớp theo chế độ mặc định | Dùng `(?U)\\s+` hoặc regex Unicode phù hợp |
| Dùng split để phân tích CSV đầy đủ | Không xử lý đúng quote, escaped delimiter và multiline field | Dùng parser CSV chuyên dụng |
| Cho rằng chuỗi rỗng và mảng rỗng là một | Mất phân biệt giữa một trường rỗng và không có token | Kiểm tra cả `length` và nội dung token |

## 11. Quy trình chọn limit

1. Xác định regex có phải delimiter literal hay một mẫu regex thực sự.
2. Xác định dữ liệu có cho phép trường rỗng ở đầu, giữa hoặc cuối hay không.
3. Nếu cần giữ tất cả trường rỗng, dùng limit âm, thường là `-1`.
4. Nếu cần bỏ các trường rỗng cuối theo quy tắc định dạng, dùng limit `0`.
5. Nếu muốn giới hạn số lần tách và giữ phần còn lại, dùng limit dương.
6. Kiểm tra `tokens.length` trước khi truy cập index và xác thực số trường theo hợp đồng dữ liệu.
7. Với Unicode whitespace hoặc line break, chọn regex như `(?U)\\s+`, `\\h+` hoặc `\\R` phù hợp.
8. Nếu dữ liệu có grammar phức tạp như CSV, dùng parser chuyên dụng thay vì regex split đơn giản.

## Tài liệu tham khảo chính thức

- [Java SE 21 API — String.split(String, int)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html#split(java.lang.String,int))
- [Java SE 21 API — Pattern](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html)
- [Java SE 21 API — Pattern.quote(String)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html#quote(java.lang.String))
- [Java SE 21 API — Pattern.UNICODE_CHARACTER_CLASS](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html#UNICODE_CHARACTER_CLASS)
- [Java Language Specification, Java SE 21 — String Literals and Escape Sequences](https://docs.oracle.com/javase/specs/jls/se21/html/jls-3.html#jls-3.10.5)
