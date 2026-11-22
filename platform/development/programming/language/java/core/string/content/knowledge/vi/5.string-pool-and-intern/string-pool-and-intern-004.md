# `new String` tạo đối tượng và quan hệ với literal có sẵn trong Java

Khi gặp hai cách viết `String a = "Java";` và `String b = new String("Java");`, cả `a` và `b` đều biểu diễn nội dung `Java`, nhưng **khác nhau về danh tính đối tượng (object identity)**. Literal được Java quản lý theo cơ chế **string pool**; biểu thức `new String(...)` tạo một đối tượng `String` mới theo ngữ nghĩa của ngôn ngữ, ngay cả khi pool đã có một đối tượng chứa cùng nội dung.

Bài này làm rõ điều gì được tái sử dụng, điều gì được tạo mới, cách `==`, `equals()` và `intern()` liên quan với nhau, và khi nào thực sự cần dùng constructor `String`.

## 1. Hai kiểu khởi tạo: literal và `new String(...)`

### Dùng literal

```java
String a = "Java";
String b = "Java";
```

- `"Java"` là một **string literal** (chuỗi literal) trong mã nguồn.
- Các string literal có cùng dãy ký tự được **intern**: trong cùng một lần chạy chương trình Java, các tham chiếu đến giá trị literal tương đương sẽ sử dụng đại diện chuẩn (canonical representation) của string pool.
- Với ví dụ này, `a == b` là `true` vì cả hai biến cùng tham chiếu một đối tượng `String` chuẩn.
- Việc gán `b = "Java"` không yêu cầu tạo thêm một đối tượng `String` mới có nội dung `Java`.

### Dùng constructor `new String(String original)`

```java
String a = "Java";
String b = new String("Java");
```

- Literal `"Java"` là đầu vào của constructor và có đại diện trong string pool.
- `new String("Java")` biểu thị việc **tạo một đối tượng `String` khác** với đối tượng tham chiếu bởi literal. Giá trị nội dung của đối tượng mới bằng giá trị literal.
- `a == b` là `false`, còn `a.equals(b)` là `true`.
- Constructor không tự đưa đối tượng `b` trở thành đại diện chuẩn của pool. Muốn lấy đại diện chuẩn, có thể gọi `b.intern()`.

Cần phân biệt **ngữ nghĩa tạo đối tượng** với việc JVM phải cấp phát bao nhiêu bộ nhớ tại thời điểm thực thi. Trình biên dịch JIT có thể loại bỏ một cấp phát không quan sát được khi tối ưu hóa, nhưng chương trình vẫn phải biểu hiện đúng quy tắc danh tính và so sánh đối tượng của Java. Vì thế không nên khẳng định chung chung rằng một dòng `new String("Java")` *luôn* làm JVM cấp phát chính xác hai đối tượng mới: literal có thể đã tồn tại trong pool từ trước, còn cách cấp phát vật lý có thể được tối ưu.

## 2. String pool, heap và tham chiếu: sơ đồ tư duy

Hình dung ví dụ:

```java
String literal = "Java";
String sameLiteral = "Java";
String constructed = new String("Java");
String copied = new String(literal);
```

Quan hệ tham chiếu theo **ngữ nghĩa Java**:

```text
literal -----------+
                   |
sameLiteral -------+----> [String chuẩn: "Java"]  (đại diện trong pool)

constructed ------------> [String khác: "Java"]

copied -----------------> [String khác nữa: "Java"]
```

Hai đối tượng tạo bởi `new` có nội dung bằng với literal nhưng là các đối tượng `String` riêng biệt về danh tính. Không được nhầm sơ đồ danh tính đối tượng với sơ đồ cấp phát vùng nhớ nội bộ. Trên các JVM hiện đại, đối tượng trong pool cũng được quản lý như những đối tượng Java; pool không phải một khu vực bộ nhớ “ngoài heap” dành riêng cho literal. Ngoài ra, các đối tượng `String` bất biến có thể sử dụng các cách lưu trữ dữ liệu bên trong tùy JVM mà không làm thay đổi hợp đồng API.

**Điểm cốt lõi:** String pool lưu và trả về tham chiếu đại diện cho nội dung chuỗi, còn `new String(...)` là yêu cầu tạo một đối tượng khác để giữ cùng giá trị.

## 3. Ví dụ Java 17+: kiểm tra `==`, `equals()` và `intern()`

Tạo tệp `NewStringVsLiteral.java`:

```java
public class NewStringVsLiteral {
    public static void main(String[] args) {
        String literal = "Java";
        String sameLiteral = "Java";
        String constructed = new String("Java");
        String copied = new String(literal);

        System.out.println("literal == sameLiteral: "
                + (literal == sameLiteral));
        System.out.println("literal == constructed: "
                + (literal == constructed));
        System.out.println("literal == copied: "
                + (literal == copied));
        System.out.println("constructed == copied: "
                + (constructed == copied));

        System.out.println("literal.equals(constructed): "
                + literal.equals(constructed));
        System.out.println("constructed.equals(copied): "
                + constructed.equals(copied));

        System.out.println("constructed.intern() == literal: "
                + (constructed.intern() == literal));
        System.out.println("copied.intern() == literal: "
                + (copied.intern() == literal));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 NewStringVsLiteral.java
java NewStringVsLiteral
```

Kết quả:

```text
literal == sameLiteral: true
literal == constructed: false
literal == copied: false
constructed == copied: false
literal.equals(constructed): true
constructed.equals(copied): true
constructed.intern() == literal: true
copied.intern() == literal: true
```

Giải thích từng nhóm kết quả:

1. Hai biến dùng cùng literal `"Java"` cùng trỏ đến tham chiếu chuẩn nên `==` trả về `true`.
2. Mỗi lần thực thi biểu thức `new String(...)` tạo một đối tượng riêng theo ngữ nghĩa Java; `constructed` và `copied` khác tham chiếu nhau và khác `literal`.
3. `equals()` do `String` triển khai để so sánh **chuỗi ký tự**; vì ba đối tượng có cùng nội dung nên kết quả bằng `true`.
4. `intern()` trả về tham chiếu chuẩn trong pool cho chuỗi cùng nội dung. Vì literal `"Java"` đã có đại diện chuẩn, `constructed.intern()` và `copied.intern()` cùng trỏ đến đối tượng đó.

Bạn có thể thay chuỗi `"Java"` bằng một nội dung khác và áp dụng cùng quy tắc. Điều được đảm bảo là **quan hệ giữa các tham chiếu**, không phải một con số cố định về đối tượng thực tế nằm trong bộ nhớ JVM tại mọi thời điểm.

## 4. Vì sao `==` và `equals()` cho kết quả khác nhau?

| Phép kiểm tra | So sánh gì? | Ví dụ với literal và đối tượng `new` |
| --- | --- | --- |
| `a == b` | Hai biến có trỏ đến **cùng một đối tượng** không? | `"Java"` và `new String("Java")` → `false` |
| `a.equals(b)` | Hai chuỗi có **cùng dãy ký tự** không? | `"Java"` và `new String("Java")` → `true` |
| `a.equalsIgnoreCase(b)` | Nội dung có tương đương theo quy tắc so sánh không phân biệt hoa/thường của phương thức không? | `"Java"` và `"JAVA"` → `true` |
| `a.intern() == b.intern()` | Hai giá trị có cùng đại diện chuẩn trong pool không? | Hai chuỗi bằng nội dung → `true` sau khi intern |

Trong phần lớn logic nghiệp vụ, mục tiêu là so sánh **giá trị văn bản**, nên dùng `equals()` hoặc `Objects.equals(a, b)` nếu có thể có `null`. Sự tình cờ `==` trả về `true` với literal không khiến `==` trở thành cách đúng để so sánh nội dung mọi `String`.

Ví dụ dễ gây lỗi:

```java
String expected = "OK";
String actual = new String("OK");

// Sai mục đích nếu muốn so sánh nội dung:
if (actual == expected) {
    System.out.println("Match");
}

// Đúng mục đích:
if (expected.equals(actual)) {
    System.out.println("Match");
}
```

Đây là đoạn minh họa đặt trong một phương thức. Chỉ nhánh dùng `equals()` in `Match`. Việc `expected.equals(actual)` đặt literal/giá trị đã biết không null ở phía trước cũng tránh lỗi `NullPointerException` nếu `actual` bất ngờ là `null`.

## 5. `String.intern()` trả về gì khi đã có literal?

Phương thức `String.intern()` tìm đại diện chuẩn trong string pool cho **nội dung** của đối tượng nhận lời gọi:

- Nếu pool đã có một `String` có nội dung bằng nhau theo `equals()`, `intern()` trả về đối tượng đã có.
- Nếu chưa có, đối tượng tương ứng sẽ được đưa vào pool và trở thành đại diện chuẩn, theo hợp đồng `intern()`.
- `intern()` **không đổi nội dung** của `String` và không có nghĩa rằng biến nhận lời gọi tự chuyển sang tham chiếu mới.

Với `String a = new String("Java");`, literal `"Java"` đã có trong mã nguồn và được intern. Do đó:

```java
String literal = "Java";
String differentObject = new String("Java");
String canonical = differentObject.intern();

System.out.println(differentObject == literal); // false
System.out.println(canonical == literal);       // true
System.out.println(differentObject == canonical); // false
```

Các dòng trên là ví dụ minh họa có thể đặt trong `main`. Nếu muốn biến `differentObject` sau đó trỏ đến tham chiếu chuẩn, cần **gán lại**: `differentObject = differentObject.intern();`. Lời gọi `intern()` đơn lẻ không thay đổi biến gốc.

Khi không có literal tương ứng trong mã và nội dung được tạo động, không nên đoán trước **đại diện chuẩn là đối tượng nào** hoặc cố xác định chính xác thời điểm một chuỗi bắt đầu có trong pool. Điều chắc chắn để dùng là: hai chuỗi bằng nội dung, sau khi intern, sẽ tham chiếu đến cùng một đại diện chuẩn.

**Không nên gọi `intern()` cho mọi chuỗi** theo thói quen. Pool cần quản lý các giá trị chuẩn, và intern một tập rất lớn các chuỗi động ít trùng lặp có thể làm tăng chi phí bộ nhớ hoặc xử lý. Hãy chỉ cân nhắc khi có nhu cầu thực tế về chuẩn hóa tham chiếu cho nhiều giá trị lặp và đã đo lường tác động.

## 6. Literal, biểu thức hằng lúc biên dịch và nối chuỗi khi chạy

Java có thêm quy tắc quan trọng: **string constant expressions** (biểu thức hằng kiểu `String`) cũng được intern. Ví dụ `"Ja" + "va"` là biểu thức hằng tại thời điểm biên dịch nên tương ứng với literal `"Java"`.

Nhưng phép nối có một toán hạng không phải biểu thức hằng được thực hiện lúc chạy, tạo ra giá trị `String` có nội dung tương ứng và thường khác tham chiếu với literal, cho đến khi bạn chủ động `intern()`.

Tệp `ConstantVsRuntime.java`:

```java
public class ConstantVsRuntime {
    public static void main(String[] args) {
        String literal = "Java";
        String folded = "Ja" + "va";

        String suffix = new String("va");
        String joinedAtRuntime = "Ja" + suffix;

        System.out.println("folded == literal: "
                + (folded == literal));
        System.out.println("joinedAtRuntime == literal: "
                + (joinedAtRuntime == literal));
        System.out.println("joinedAtRuntime.equals(literal): "
                + joinedAtRuntime.equals(literal));
        System.out.println("joinedAtRuntime.intern() == literal: "
                + (joinedAtRuntime.intern() == literal));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ConstantVsRuntime.java
java ConstantVsRuntime
```

Kết quả:

```text
folded == literal: true
joinedAtRuntime == literal: false
joinedAtRuntime.equals(literal): true
joinedAtRuntime.intern() == literal: true
```

Lý do: `folded` là kết quả nối **hai literal**; trình biên dịch xác định giá trị hằng `"Java"` và dùng đại diện chuẩn. Ngược lại, `suffix` được nhận từ biểu thức khởi tạo đối tượng `new String("va")`, nên `"Ja" + suffix` không phải biểu thức hằng theo quy tắc ngôn ngữ. Kết quả nối có nội dung `"Java"` nhưng không tự trở thành tham chiếu chuẩn của literal.

Một biến `final String` được khởi tạo bằng biểu thức hằng cũng có thể là **constant variable**:

```java
final String prefix = "Ja";
String stillConstant = prefix + "va";
System.out.println(stillConstant == "Java"); // true
```

Ngược lại, không phải cứ đặt `final` là mọi phép nối đều trở thành hằng tại lúc biên dịch: giá trị khởi tạo còn phải thỏa điều kiện *constant expression*. Đây là nguyên nhân khiến một số bài kiểm tra `==` với nối chuỗi có vẻ cho kết quả “lúc true, lúc false”. Vì thế, hãy dùng `equals()` cho nội dung.

## 7. `new String` với nguồn không phải literal

Phạm vi của constructor không chỉ có literal. Java cũng hỗ trợ tạo `String` từ một đối tượng `String` đã có, từ `char[]`, từ các đoạn của mảng hoặc từ byte kèm bộ mã hóa phù hợp.

### Tạo từ một `String` có sẵn

```java
String original = "data";
String copy = new String(original);

System.out.println(original == copy);      // false
System.out.println(original.equals(copy)); // true
```

Cả hai có nội dung bằng nhau, nhưng constructor vẫn tạo một đối tượng mới theo ngữ nghĩa Java. Tuy vậy, vì `String` **bất biến**, việc tạo đối tượng mới chỉ để “bảo vệ nội dung” khỏi bị sửa là không cần thiết. Cũng không nên tự suy luận rằng constructor này bắt buộc tạo bản sao độc lập của toàn bộ vùng nhớ chứa ký tự nội bộ; đó là chi tiết triển khai JVM, không phải lý do để dùng constructor.

### Tạo từ `char[]`: lấy một bản nội dung tại thời điểm tạo

Một mảng `char[]` **có thể thay đổi**, nên trường hợp này có ý nghĩa khác.

Tệp `NewStringFromArray.java`:

```java
public class NewStringFromArray {
    public static void main(String[] args) {
        char[] letters = {'J', 'a', 'v', 'a'};
        String fromArray = new String(letters);
        String literal = "Java";

        letters[0] = 'X';

        System.out.println("array=" + new String(letters));
        System.out.println("fromArray=" + fromArray);
        System.out.println("sameContent=" + fromArray.equals(literal));
        System.out.println("sameReference=" + (fromArray == literal));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 NewStringFromArray.java
java NewStringFromArray
```

Kết quả:

```text
array=Xava
fromArray=Java
sameContent=true
sameReference=false
```

`new String(letters)` lấy nội dung mảng tại thời điểm tạo. Sửa `letters` sau đó không sửa `fromArray`; đây là hợp đồng quan trọng giữa nguồn mutable `char[]` và đích immutable `String`. Giá trị `fromArray` vẫn bằng literal `"Java"`, nhưng vì được tạo qua `new` nên không cùng tham chiếu với literal.

Tương tự, có constructor `new String(StringBuilder)` hoặc `new String(StringBuffer)` để tạo `String` từ nội dung hiện tại của vùng đệm. Tuy nhiên, khi đã có một `String` hợp lệ, `new String(existingString)` thường không cung cấp thêm giá trị.

### Tạo từ byte cần biết charset

`new String(bytes, StandardCharsets.UTF_8)` có nhiệm vụ **giải mã byte** theo UTF-8; đây không phải là thao tác “copy một literal”. Khi sử dụng các constructor từ byte, cần truyền charset rõ ràng phù hợp với dữ liệu đầu vào để tránh sai ký tự. Các constructor nhận `String` và `char[]` không giải quyết bài toán giải mã byte.

## 8. Có nên dùng `new String("literal")` trong ứng dụng?

**Thông thường không cần.** Nếu chỉ muốn sử dụng một nội dung văn bản cố định, gán trực tiếp literal vừa ngắn gọn vừa tận dụng cơ chế tái sử dụng đại diện chuẩn:

```java
String status = "READY"; // Phù hợp cho giá trị hằng đã biết
```

Nếu đã có đối tượng `String` từ một phương thức hay tham số, chỉ cần dùng lại giá trị đó:

```java
static String normalizeStatus(String status) {
    return status == null ? "UNKNOWN" : status.trim();
}
```

Đây là phương thức minh họa đặt trong một lớp. Dùng `new String(status)` trước hoặc sau `trim()` không giúp so sánh chuỗi an toàn hơn và không ngăn người khác sửa nội dung của `String` (vì nội dung vốn đã bất biến).

Các lý do **không hợp lệ** để thêm `new String("...")` tùy tiện:

- “Để chuỗi không bị sửa từ bên ngoài”: `String` vốn bất biến.
- “Để luôn tạo chuỗi khác nội dung”: constructor tạo khác **đối tượng**, không làm nội dung khác.
- “Để so sánh bằng `==` cho chính xác”: làm việc so sánh tham chiếu khác đi; so sánh giá trị vẫn cần `equals()`.
- “Để tiết kiệm bộ nhớ nhờ string pool”: `new` không phải cơ chế tái sử dụng đại diện chuẩn.
- “Để copy chắc chắn các byte/char nội bộ”: chi tiết chia sẻ hay sao chép dữ liệu bên trong `String` không phải hợp đồng của constructor nhận `String`.

**Dùng constructor khi đầu vào thực sự cần chuyển đổi sang `String`**, như `char[]`, `StringBuilder`, `StringBuffer`, hay byte đã xác định charset. Với nguồn đã là `String`, constructor sao chép theo ngữ nghĩa đối tượng hiếm khi cần thiết.

## 9. `null`, identity và các lỗi thường gặp

### Truyền `null` vào constructor

Một tham chiếu `String` bằng `null` không phải đối tượng chuỗi rỗng:

```java
String absent = null;
// String copy = new String(absent); // Ném NullPointerException khi chạy
```

Đây là đoạn minh họa bên trong một phương thức. Việc viết trực tiếp `new String(null)` cũng không nên dùng để thử nghiệm, bởi `String` có nhiều constructor quá tải nên literal `null` trần có thể gây lỗi **không xác định được overload** ngay lúc biên dịch. Nếu cần chuỗi rỗng theo quy ước nghiệp vụ, hãy kiểm tra `null` và trả về `""` một cách tường minh.

### Những lỗi thiết kế phổ biến

1. **Giả định hai chuỗi bằng nội dung luôn `==` nhau.** Chỉ có thể dựa vào quan hệ tham chiếu khi bạn chủ động làm việc với pool/identity; để so sánh văn bản, dùng `equals()`.
2. **Tưởng `new String("x")` làm xuất hiện một nội dung mới.** Giá trị vẫn là `"x"`; khác biệt là danh tính đối tượng.
3. **Đếm số đối tượng từ số literal và số chữ `new` trong mã nguồn.** Pool có thể đã chứa giá trị, literal có thể xuất hiện nhiều nơi, và JVM có quyền tối ưu hóa cấp phát nếu không thay đổi hành vi quan sát được.
4. **Tưởng `intern()` thay đổi biến gốc.** `intern()` trả về một tham chiếu; cần nhận và dùng giá trị trả về nếu mục tiêu là dùng tham chiếu chuẩn.
5. **Dùng `new String(existingString)` để phòng vệ với dữ liệu immutable.** Bản thân `String` không bị sửa tại chỗ; việc tạo object mới thường thừa.
6. **Tưởng mọi phép nối chuỗi đều dùng string pool.** Biểu thức hằng được intern; nối có toán hạng động tuân theo quy tắc khác và không tự chuyển thành đại diện chuẩn.
7. **Tự động intern tất cả giá trị đầu vào.** Cần cân nhắc số chuỗi duy nhất, số lượng trùng lặp và tài nguyên thực tế; intern không thay thế việc thiết kế cache/deduplication có giới hạn.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Đoạn sau in gì?

```java
String a = "hello";
String b = new String("hello");

System.out.println(a == b);
System.out.println(a.equals(b));
System.out.println(a == b.intern());
```

**Trả lời:** lần lượt là `false`, `true`, `true`. Constructor tạo đối tượng khác; nội dung bằng nhau; `intern()` trả về đại diện chuẩn của literal có sẵn.

**Câu 2.** Tại sao `String a = "J" + "ava";` có thể `==` với `"Java"` nhưng `String b = "J" + someVariable;` thì không nên kiểm tra theo cách này?

**Trả lời:** `"J" + "ava"` là biểu thức hằng tại lúc biên dịch và có đại diện chuẩn trong pool. Nếu `someVariable` không phải constant variable, phép nối được thực hiện lúc chạy, cho nội dung có thể bằng `"Java"` nhưng tham chiếu không nên dùng làm điều kiện so sánh nội dung.

**Câu 3.** `new String("Java")` có tự trả về đúng đối tượng nằm trong pool không?

**Trả lời:** Không. `new String("Java")` tạo đối tượng `String` riêng; gọi `intern()` trên đối tượng đó mới lấy đại diện chuẩn đã có cho literal `"Java"`.

**Câu 4.** Vì sao `new String(charArray)` hữu ích hơn `new String(existingString)` khi mục tiêu là bảo toàn nội dung trước thay đổi của nguồn?

**Trả lời:** `char[]` có thể bị sửa sau khi truyền, còn `String` bất biến. Constructor nhận mảng cung cấp một giá trị chuỗi độc lập với các thay đổi tiếp theo của mảng; tạo thêm `String` từ một `String` đã có thường không cần thiết.

**Ghi nhớ:** Literal và biểu thức hằng kiểu `String` được intern, có thể tái sử dụng tham chiếu chuẩn. `new String("...")` tạo một đối tượng chuỗi khác nhưng có nội dung bằng literal. Dùng `equals()` cho so sánh văn bản; chỉ dùng `intern()` khi thật sự cần đại diện chuẩn và đã cân nhắc chi phí.
