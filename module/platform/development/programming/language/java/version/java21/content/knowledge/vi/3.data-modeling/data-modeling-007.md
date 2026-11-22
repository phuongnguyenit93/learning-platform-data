# Type pattern với instanceof và phạm vi biến theo luồng điều khiển

Type pattern với toán tử `instanceof` cho phép kiểm tra kiểu của một đối tượng và khai báo biến đại diện cho giá trị đã được xác nhận thuộc kiểu đó trong cùng một biểu thức. Java 21 hỗ trợ tính năng này như một phần chính thức của ngôn ngữ; không cần bật preview. Khi kết hợp với flow scoping (phạm vi biến theo luồng điều khiển), trình biên dịch xác định chính xác đoạn mã nào có thể sử dụng biến pattern một cách an toàn.

Kỹ thuật này đặc biệt hữu ích khi xử lý dữ liệu có kiểu tổng quát như `Object`, đầu vào từ API, cấu trúc dữ liệu không đồng nhất hoặc kết quả trả về có thể thuộc nhiều kiểu. Thay vì kiểm tra kiểu rồi ép kiểu thủ công, mã nguồn có thể thực hiện cả hai bước trong một biểu thức và để trình biên dịch kiểm tra phạm vi sử dụng biến.

## 1. Cú pháp và cách hoạt động

Cú pháp type pattern cơ bản:

```java
expression instanceof ReferenceType variableName
```

Ví dụ:

```java
static String display(Object value) {
    if (value instanceof String text) {
        return text.strip();
    }
    return String.valueOf(value);
}
```

Trong biểu thức `value instanceof String text`, Java thực hiện các bước sau:

1. Đánh giá giá trị của `value`.
2. Kiểm tra giá trị có khác `null` và có thể được xem là một `String` tại runtime hay không.
3. Nếu phép kiểm tra thành công, tạo binding cho biến pattern `text` với kiểu khai báo là `String`.
4. Nếu phép kiểm tra thất bại, biểu thức cho kết quả `false` và biến `text` không được xem là đã khớp.

Biến `text` có kiểu tĩnh là `String`, vì vậy có thể gọi trực tiếp các method của `String` mà không cần cast. Type pattern không tạo một đối tượng String mới; nó đặt tên cho giá trị đã được kiểm tra kiểu.

Cách viết này gộp phép kiểm tra kiểu và binding biến trong cùng một biểu thức. Trình biên dịch cũng kiểm soát rằng biến chỉ được sử dụng ở nơi pattern chắc chắn đã khớp.

### 1.1. Type pattern khác phép kiểm tra kiểu thông thường như thế nào?

Biểu thức `value instanceof String` chỉ trả về kết quả boolean. Khi dùng type pattern, `value instanceof String text` vẫn thực hiện phép kiểm tra đó nhưng đồng thời cung cấp biến `text` đã có kiểu `String` trên nhánh mà phép kiểm tra thành công.

Ví dụ:

```java
static int lengthOf(Object value) {
    if (value instanceof CharSequence sequence) {
        return sequence.length();
    }
    return 0;
}
```

Ở đây kiểu pattern là `CharSequence`, không phải `String`. Vì vậy, biến `sequence` chỉ cho phép sử dụng các thao tác được khai báo trong `CharSequence`, dù đối tượng thực tế có thể là `String` hoặc một lớp triển khai khác.

Kiểu được khai báo trong pattern quyết định các thao tác mà mã nguồn được phép gọi. Hãy chọn kiểu đủ cụ thể cho công việc, đồng thời tránh giả định rằng kiểu runtime luôn là một lớp triển khai duy nhất.

### 1.2. Giá trị null và khả năng khớp kiểu

Với `instanceof`, giá trị `null` luôn làm phép kiểm tra trả về `false`. Vì vậy, pattern không khớp và biến pattern không được binding:

```java
Object value = null;

if (value instanceof String text) {
    // Nhánh này không được thực hiện khi value là null.
    System.out.println(text.length());
}
```

Không cần kiểm tra `value != null` riêng khi mục đích duy nhất là xác định giá trị có thuộc một kiểu tham chiếu hay không. Phép kiểm tra `instanceof` đã xử lý trường hợp null.

### 1.3. Khả năng áp dụng của kiểu pattern

Kiểu trong pattern phải có khả năng tương thích với kiểu tĩnh của biểu thức. Ví dụ, khi biến đã có kiểu `String`, kiểm tra lại chính kiểu `String` là dư thừa và bị trình biên dịch từ chối vì pattern luôn đúng:

```java
String name = "Lan";

// Không hợp lệ: kiểu của name đã là String.
// if (name instanceof String text) { ... }
```

Ngược lại, khi giá trị có kiểu tổng quát như `Object`, kiểm tra `instanceof String text` có ý nghĩa vì giá trị runtime có thể là String hoặc một kiểu khác.

Với generic, thông tin tham số kiểu thường bị xóa ở runtime (type erasure). Khi kiểm tra một giá trị có kiểu tổng quát như `Object`, dùng kiểu có thể kiểm tra tại runtime, chẳng hạn `List<?>`, rồi kiểm tra từng phần tử nếu cần xác định kiểu phần tử:

```java
if (value instanceof java.util.List<?> items) {
    for (Object item : items) {
        if (item instanceof String text) {
            System.out.println(text.strip());
        }
    }
}
```

Không thể dựa vào type pattern để kiểm tra tùy ý tham số generic đã bị xóa, chẳng hạn kiểm tra một giá trị `Object` có phải là `List<String>` hay không. Runtime không lưu đầy đủ thông tin đó cho phép kiểm tra kiểu như vậy.

## 2. Flow scoping là gì?

Flow scoping là cơ chế xác định phạm vi sử dụng biến pattern dựa trên luồng thực thi và kết quả khớp pattern. Phạm vi của biến không chỉ phụ thuộc vào cặp dấu ngoặc nhọn; trình biên dịch phân tích điều kiện để biết tại mỗi vị trí, pattern đã chắc chắn khớp hay chưa.

Với cấu trúc đơn giản:

```java
if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

Biến `text` được dùng trong thân nhánh `if`, bởi thân nhánh chỉ được thực hiện khi phép kiểm tra thành công.

Ở nhánh `else`, pattern không được bảo đảm đã khớp, do đó không thể sử dụng `text`:

```java
if (value instanceof String text) {
    System.out.println(text.length());
} else {
    // text không nằm trong phạm vi sử dụng tại đây.
    System.out.println("Giá trị không phải String");
}
```

Sau toàn bộ câu lệnh `if`, biến `text` cũng không được dùng trong trường hợp tổng quát, vì luồng có thể đi qua nhánh điều kiện sai mà không khớp pattern.

Điều này khác với một biến cục bộ được khai báo ở phạm vi bao quanh và gán giá trị sau đó. Biến pattern chỉ khả dụng ở nơi trình biên dịch chứng minh được rằng nó đã được binding.

## 3. Flow scoping với toán tử &&

Toán tử `&&` chỉ đánh giá vế phải khi vế trái có kết quả `true`. Vì vậy, nếu pattern ở vế trái khớp khi điều kiện đúng, biến pattern có thể được sử dụng trong vế phải.

```java
static boolean isNonBlankText(Object value) {
    return value instanceof String text && !text.isBlank();
}
```

Trong biểu thức trên:

- Nếu `value` không phải String hoặc là `null`, vế trái là `false`; vế phải không được đánh giá.
- Nếu vế trái là `true`, biến `text` đã được binding và có thể gọi `isBlank()`.
- Toàn bộ biểu thức chỉ trả về `true` khi giá trị là String và nội dung không blank.

Biến pattern cũng có thể được dùng trong thân nhánh:

```java
if (value instanceof String text && text.length() >= 3) {
    System.out.println("Mã hợp lệ: " + text);
}
```

Nếu điều kiện đầu tiên không khớp, Java không đánh giá điều kiện thứ hai. Nếu điều kiện đầu tiên khớp, `text` chắc chắn là String khi điều kiện thứ hai được đánh giá.

Không thể dùng biến pattern ở vế phải của `&&` nếu luồng đi đến vế phải không bảo đảm pattern đã khớp. Ví dụ sau không hợp lệ:

```java
// Không hợp lệ: vế phải được đánh giá khi pattern không khớp.
// if (!(value instanceof String text) && text.isBlank()) { ... }
```

Khi vế trái của biểu thức trên là `true`, điều đó có nghĩa là phép kiểm tra `instanceof` thất bại. Do vậy, không có binding hợp lệ cho `text` ở vế phải.

## 4. Flow scoping với toán tử || và phủ định !

Toán tử `||` chỉ đánh giá vế phải khi vế trái là `false`. Vì vậy, biến pattern có thể nằm trong phạm vi của vế phải nếu kết quả `false` ở vế trái chứng minh pattern đã khớp.

Ví dụ:

```java
static String requireText(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        throw new IllegalArgumentException("Cần một chuỗi không rỗng");
    }
    return text.strip();
}
```

Đây là một cách viết guard clause hữu ích:

1. Nếu `value` không phải String, biểu thức phủ định trả về `true`; vế phải của `||` không chạy và phương thức ném ngoại lệ.
2. Nếu `value` là String, biểu thức phủ định trả về `false`; pattern đã khớp nên vế phải được phép sử dụng `text`.
3. Nếu chuỗi blank, phương thức ném ngoại lệ.
4. Nếu câu lệnh `if` kết thúc bình thường, điều kiện đã phải là `false`; do đó `text` chắc chắn đã được binding và có thể dùng sau câu lệnh.

Ngược lại, pattern ở vế trái của `||` không làm biến khả dụng ở vế phải trong trường hợp thông thường:

```java
// Không hợp lệ: vế phải chạy khi phép kiểm tra ở vế trái là false.
// if (value instanceof String text || text.isBlank()) { ... }
```

Khi vế phải được đánh giá, `value instanceof String text` đã trả về `false`; biến `text` chưa được binding.

Phủ định `!` đảo kết quả boolean và cũng đảo nhánh mà pattern được bảo đảm đã khớp. Có thể dùng điều này để kiểm tra lỗi sớm rồi tiếp tục xử lý:

```java
static int countCharacters(Object value) {
    if (!(value instanceof String text)) {
        return 0;
    }

    // Nếu luồng chạy tới đây, pattern đã khớp.
    return text.length();
}
```

Câu lệnh `return` trong nhánh không khớp làm cho luồng không thể đi tiếp từ nhánh đó. Mọi luồng đi tới câu lệnh `return text.length()` đều đã vượt qua phép kiểm tra thành công, vì thế biến `text` hợp lệ tại vị trí này.

Nếu thân nhánh kiểm tra vẫn có thể kết thúc bình thường, trình biên dịch không thể kết luận rằng pattern đã khớp ở câu lệnh sau:

```java
if (!(value instanceof String text)) {
    System.out.println("Không phải String");
}

// Không hợp lệ: nhánh trên có thể kết thúc bình thường khi pattern chưa khớp.
// System.out.println(text.length());
```

## 5. Flow scoping trong biểu thức điều kiện và vòng lặp

### 5.1. Toán tử điều kiện ba ngôi

Trong biểu thức điều kiện ba ngôi, nhánh thứ hai chỉ được đánh giá khi điều kiện là `true`. Vì vậy, biến pattern có thể dùng trong nhánh này:

```java
String label = value instanceof String text
        ? text.strip()
        : "Giá trị không phải chuỗi";
```

Biến `text` không được dùng trong nhánh sau dấu `:`, vì nhánh đó được chọn khi pattern không khớp.

### 5.2. Câu lệnh while và for

Điều kiện của vòng lặp được kiểm tra trước mỗi lần thực hiện thân vòng lặp. Nếu pattern nằm trong điều kiện, biến pattern có thể dùng trong thân vòng lặp vì thân chỉ chạy khi điều kiện là `true`.

```java
Object current = "bản ghi thứ nhất";

while (current instanceof String text && !text.isBlank()) {
    System.out.println(text.strip());
    current = null;
}
```

Ở mỗi lần kiểm tra điều kiện, Java đánh giá lại biểu thức và tạo binding cho biến pattern nếu giá trị hiện tại khớp kiểu. Biến `text` chỉ dùng trong điều kiện phía sau nơi pattern đã khớp và trong thân vòng lặp tương ứng.

Cách hiểu tương tự áp dụng cho điều kiện của vòng lặp `for`. Khi vòng lặp kết thúc do điều kiện sai, không thể mặc định biến pattern đã khớp; vì vậy không sử dụng biến đó sau vòng lặp nếu luồng không chứng minh được điều kiện cần thiết.

## 6. Quy tắc đối với biến pattern

Biến được khai báo trong type pattern có một số đặc điểm cần ghi nhớ:

- **Có kiểu tĩnh rõ ràng:** kiểu khai báo trong pattern quyết định các thành viên có thể truy cập.
- **Chỉ khả dụng khi đã khớp:** flow scoping giới hạn biến vào những vùng mà pattern chắc chắn thành công.
- **Không thể gán lại:** pattern variable là biến cục bộ ngầm định `final`; không thể gán một giá trị mới cho nó.
- **Không tạo bản sao đối tượng:** biến tham chiếu tới chính giá trị đã được kiểm tra.
- **Không bảo đảm kiểu generic tại runtime:** type erasure giới hạn những tham số kiểu có thể kiểm tra bằng `instanceof`.

Ví dụ về tính chất không thể gán lại:

```java
if (value instanceof String text) {
    System.out.println(text);
    // text = "giá trị mới"; // Không hợp lệ: pattern variable là final.
}
```

Vì biến pattern không thể gán lại, nó cũng phù hợp để được sử dụng trong lambda bên trong phạm vi hợp lệ, miễn là các quy tắc capture của Java được đáp ứng.

Tên biến pattern nên thể hiện ý nghĩa của kiểu sau khi kiểm tra, ví dụ `text`, `sequence`, `number` hoặc `items`. Tránh tái sử dụng một tên đã có biến cục bộ khác trong phạm vi giao nhau, vì điều đó có thể gây lỗi khai báo trùng hoặc làm mã khó đọc.

## 7. Các lỗi thường gặp và cách xử lý

| Lỗi hoặc cách viết | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng biến pattern trong nhánh `else` của phép kiểm tra trực tiếp | Nhánh này chạy khi pattern không khớp | Chuyển thao tác cần biến vào nhánh khớp |
| Dùng biến ở vế phải của `&&` sau một điều kiện phủ định không phù hợp | Vế phải có thể chạy khi pattern chưa khớp | Sắp xếp điều kiện để vế phải chỉ chạy sau khi pattern khớp |
| Dùng biến ở vế phải của `||` dù vế trái có thể `true` khi pattern khớp | Vế phải chỉ chạy khi vế trái `false`; trạng thái binding có thể không được bảo đảm | Phân tích điều kiện false của vế trái hoặc đổi cấu trúc điều kiện |
| Dùng biến sau câu lệnh `if` mà nhánh không khớp vẫn có thể tiếp tục | Có luồng đi tới vị trí đó mà không khớp pattern | Kết thúc nhánh không khớp bằng `return`, `throw` hoặc cấu trúc điều khiển phù hợp |
| Kiểm tra một kiểu mà kiểu tĩnh đã bảo đảm | Pattern luôn đúng và không cần thiết | Dùng trực tiếp biến đã có kiểu hoặc kiểm tra một kiểu tổng quát phù hợp |
| Cố kiểm tra tham số generic đã bị xóa | Runtime không có đủ thông tin kiểu để thực hiện phép kiểm tra đó | Dùng wildcard có thể kiểm tra như `List<?>`, rồi kiểm tra phần tử riêng |

Khi gặp lỗi về phạm vi biến pattern, hãy lần theo các đường đi có thể xảy ra thay vì chỉ nhìn vị trí dấu ngoặc nhọn. Câu hỏi cần trả lời là: tại mọi đường đi đến vị trí sử dụng biến, phép kiểm tra pattern có chắc chắn thành công hay không?

## 8. Cách áp dụng trong thiết kế và xử lý dữ liệu

Type pattern phù hợp khi một phương thức nhận dữ liệu tổng quát nhưng cần xử lý theo kiểu thực tế của từng giá trị. Ví dụ, một hàm định dạng có thể nhận nhiều loại dữ liệu:

```java
static String formatValue(Object value) {
    if (value == null) {
        return "(trống)";
    }

    if (value instanceof String text) {
        return text.strip();
    }

    if (value instanceof Number number) {
        return number.toString();
    }

    if (value instanceof java.time.LocalDate date) {
        return date.toString();
    }

    return value.toString();
}
```

Mỗi nhánh xác định một kiểu dữ liệu và dùng biến pattern với kiểu tương ứng. Nhờ đó, phần xử lý của từng loại dữ liệu được kiểm tra kiểu tại compile time và không cần cast riêng.

Tuy vậy, không nên lạm dụng `Object` rồi kiểm tra kiểu ở nhiều nơi nếu mô hình miền nghiệp vụ đã có thể biểu diễn bằng interface, sealed hierarchy hoặc các kiểu dữ liệu cụ thể. Type pattern hữu ích tại ranh giới xử lý dữ liệu không đồng nhất; còn trong phần lõi của thiết kế, kiểu tĩnh rõ ràng thường giúp thể hiện hợp đồng và giới hạn trạng thái tốt hơn.

## 9. Phạm vi sử dụng trong Java 21

Pattern matching for `instanceof` đã là tính năng chính thức của Java từ Java 16 và tiếp tục được hỗ trợ trong Java 21. Khi viết ứng dụng Java 21, có thể sử dụng type pattern và flow scoping trực tiếp mà không bật `--enable-preview`.

Để áp dụng đúng, cần nhớ ba điểm:

1. Type pattern vừa kiểm tra kiểu runtime vừa binding một biến có kiểu tĩnh cụ thể.
2. Flow scoping cho phép dùng biến ở nơi luồng điều khiển chứng minh pattern đã khớp, bao gồm các biểu thức `&&`, `||`, phủ định, nhánh điều kiện và vòng lặp.
3. Một biến pattern không khả dụng trên mọi đường đi; trình biên dịch từ chối mã có thể sử dụng biến trước khi pattern chắc chắn thành công.

Hiểu các quy tắc này giúp viết mã Java 21 ngắn gọn, an toàn kiểu và dễ đọc hơn khi xử lý dữ liệu có nhiều kiểu runtime.
