# Khai báo biến cục bộ không tên và yêu cầu về biểu thức khởi tạo

Từ Java 22, bạn có thể khai báo một biến cục bộ bằng ký tự gạch dưới `_` khi chương trình cần tạo biến nhưng không cần đọc giá trị của biến đó. Cú pháp này thuộc tính năng **Unnamed Variables and Patterns**, được chuẩn hóa qua JEP 456. Trong Java SE 22, đây là tính năng chính thức, vì vậy chương trình không cần bật preview feature.

Bài học này tập trung vào biến cục bộ không tên và quy tắc khởi tạo của chúng. Cùng ký tự `_` còn được dùng trong unnamed patterns; pattern có quy tắc khớp dữ liệu riêng, không phải một khai báo biến thông thường.

## 1. Biến cục bộ không tên là gì?

Biến cục bộ không tên là một biến được khai báo và khởi tạo nhưng không có tên để chương trình tham chiếu. Thay vì đặt tên như `result`, `item` hoặc `ignored`, ta viết `_`:

```java
int _ = calculateTotal();
```

Biểu thức `calculateTotal()` vẫn được thực thi và giá trị trả về được gán cho biến không tên. Tuy nhiên, chương trình không thể đọc giá trị đó ở câu lệnh tiếp theo vì `_` không tạo ra một tên có thể tham chiếu.

```java
int _ = calculateTotal();
System.out.println(_); // Lỗi biên dịch: không thể tham chiếu biến không tên
```

`_` là từ khóa dành riêng của Java từ Java 9. Từ Java 22, nó được phép xuất hiện trong một số ngữ cảnh khai báo biến và pattern được quy định rõ. Không thể dùng `_` làm tên tùy ý cho field, tham số method hoặc tham số constructor.

Vì biến không tên không đưa một tên vào phạm vi khai báo, cùng một block có thể chứa nhiều biến không tên, kể cả khi kiểu của chúng khác nhau:

```java
void process() {
    int _ = loadConfigurationVersion();
    String _ = readDiagnosticMessage();
    boolean _ = validateInput();
}
```

Các khai báo trên độc lập với nhau. Chúng không xung đột tên vì không có tên biến nào được thêm vào scope. Điều này hữu ích khi mỗi thao tác cần được thực hiện nhưng kết quả không được sử dụng.

## 2. Những vị trí có thể khai báo biến cục bộ không tên

Java cho phép khai báo biến cục bộ không tên trong các vị trí khai báo local variable được quy định trong ngôn ngữ:

| Vị trí | Ví dụ | Giá trị được cung cấp như thế nào? |
| --- | --- | --- |
| Câu lệnh khai báo biến trong block | `Order _ = loadOrder();` | Biểu thức khởi tạo ở bên phải dấu `=` |
| Phần khởi tạo của vòng lặp `for` cơ bản | `for (int _ = begin(); ... )` | Biểu thức khởi tạo của vòng lặp |
| Biến lặp của enhanced `for` | `for (Order _ : orders)` | Phần tử hiện tại của iterable hoặc array |
| Khai báo resource trong try-with-resources | `try (var _ = acquireLock())` | Biểu thức tạo resource |
| Type pattern | `if (value instanceof String _)` | Giá trị được khớp với pattern |

Ví dụ enhanced `for` dưới đây đếm số phần tử mà không cần dùng giá trị của từng phần tử:

```java
static int countOrders(Iterable<Order> orders) {
    int count = 0;

    for (Order _ : orders) {
        count++;
    }

    return count;
}
```

Mỗi lượt lặp, phần tử hiện tại được gán cho biến lặp không tên. Thân vòng lặp chỉ tăng bộ đếm nên không cần một tên như `order`.

Trong try-with-resources, biến không tên vẫn giữ nguyên cơ chế quản lý tài nguyên. Ví dụ, giả sử `acquireLock()` trả về một đối tượng guard triển khai `AutoCloseable`:

```java
try (var _ = acquireLock()) {
    updateInventory();
}
```

Java gọi `close()` cho resource khi rời khỏi block, kể cả khi block kết thúc do exception. Chương trình không cần tên biến nếu không gọi trực tiếp phương thức nào khác trên guard.

Các tham số `catch` và tham số lambda cũng có thể không tên, nhưng chúng là những ngữ cảnh khai báo riêng. Ví dụ:

```java
import java.util.function.BiConsumer;

class UnnamedParametersExample {
    void run() {
        try {
            performOptionalOperation();
        } catch (UnsupportedOperationException _) {
            // Bỏ qua loại exception này theo chính sách của ứng dụng.
        }

        BiConsumer<String, Integer> logger = (_, code) ->
            System.out.println("Code: " + code);
    }

    void performOptionalOperation() { }
}
```

Trong lambda, nếu khai báo kiểu tường minh hoặc dùng `var` cho một tham số thì các tham số còn lại phải tuân theo cùng kiểu hình thức khai báo theo quy tắc lambda của Java. Dùng `_` giúp thể hiện rõ tham số đầu tiên được nhận nhưng không được sử dụng.

## 3. Quy tắc bắt buộc có initializer

Điểm quan trọng của biến cục bộ không tên là: trong một số vị trí, khai báo bắt buộc phải có biểu thức khởi tạo. Quy tắc này chặt hơn khai báo biến cục bộ có tên.

### 3.1. Khai báo trong block phải có initializer

Khi khai báo biến cục bộ không tên trực tiếp trong block, phải khởi tạo biến ngay tại khai báo:

```java
void example() {
    int _ = calculateValue();  // Hợp lệ
    String _ = readMessage();  // Hợp lệ

    // int _;                  // Lỗi biên dịch: thiếu initializer
}
```

Với biến có tên, Java cho phép khai báo trước rồi gán sau, miễn là mọi lần đọc đều được bảo đảm đã gán giá trị (definite assignment):

```java
void example() {
    int result;
    result = calculateValue();
    System.out.println(result);
}
```

Không thể áp dụng cách này cho biến không tên. Sau khai báo, chương trình không có tên để thực hiện phép gán tiếp theo. Vì vậy, Java quy định khai báo không tên trong block phải có initializer ngay từ đầu.

### 3.2. Khai báo trong phần khởi tạo của basic `for` cũng phải có initializer

Quy tắc tương tự áp dụng cho biến không tên được khai báo trong phần khởi tạo của vòng lặp `for` cơ bản:

```java
for (int _ = initializeCounter(); hasNext(); advance()) {
    processNext();
}
```

`initializeCounter()` được gọi đúng một lần khi bắt đầu vòng lặp. Giá trị trả về được gán cho biến không tên và không được sử dụng. Khai báo sau không hợp lệ vì thiếu initializer:

```java
for (int _; hasNext(); advance()) { // Lỗi biên dịch
    processNext();
}
```

Quy tắc này được áp dụng riêng cho khai báo không tên. Với một biến có tên, việc không viết initializer có thể hợp lệ nếu quy tắc definite assignment vẫn được thỏa mãn.

### 3.3. Enhanced `for` và try-with-resources có cách khởi tạo riêng

Trong enhanced `for`, giá trị của biến lặp được cung cấp bởi phần tử của array hoặc iterable ở mỗi lượt lặp. Do đó, cú pháp không có initializer `=`:

```java
for (var _ : orders) {
    count++;
}
```

Trong try-with-resources, khai báo resource phải có biểu thức khởi tạo hoặc tham chiếu đến resource đã tồn tại theo cú pháp try-with-resources. Với resource không tên, thường dùng dạng khai báo có initializer:

```java
try (var _ = openResource()) {
    useOtherResources();
}
```

Với pattern, giá trị được khớp và gán theo quy tắc pattern matching. Unnamed pattern không tạo biến để đọc, nên không có biểu thức khởi tạo theo cách của local variable declaration statement.

## 4. Dùng kiểu tường minh và `var`

Biến không tên có thể khai báo với kiểu cụ thể hoặc dùng `var` để trình biên dịch suy luận kiểu từ initializer.

### 4.1. Khai báo với kiểu tường minh

Khi kiểu dữ liệu đã rõ, có thể ghi kiểu trực tiếp:

```java
int _ = computeScore();
String _ = readLabel();
int[] _ = {10, 20, 30};
```

Với kiểu mảng, có thể dùng array initializer vì kiểu phần tử và kiểu mảng đã được khai báo tường minh.

### 4.2. Khai báo bằng `var`

`var` yêu cầu initializer để trình biên dịch xác định kiểu. Quy tắc này vẫn áp dụng khi tên biến là `_`:

```java
var _ = computeScore();       // Suy luận thành kiểu int nếu phương thức trả về int
var _ = readLabel();          // Suy luận theo kiểu trả về của readLabel()
var _ = new int[] {10, 20};   // Hợp lệ: initializer là biểu thức tạo mảng
```

Khai báo bằng `var` phải tuân thủ các giới hạn sau:

- Chỉ khai báo một biến trong một declarator; `var _ = 1, _ = 2;` và `var first = 1, second = 2;` đều không hợp lệ.
- Phải có initializer; `var _;` không hợp lệ.
- Không thêm cặp dấu ngoặc vuông vào phần khai báo biến, ví dụ `var _[] = ...` không hợp lệ.
- Initializer không thể là array initializer độc lập. `var _ = {1, 2};` không hợp lệ; hãy dùng `var _ = new int[] {1, 2};`.
- Kiểu của initializer phải suy luận được. `var _ = null;` không hợp lệ vì `null` không cung cấp một kiểu cụ thể để suy luận.
- Lambda expression và method reference đứng độc lập cũng không thể làm initializer cho `var` vì chúng cần một target type, ví dụ `var _ = () -> 42;` không hợp lệ.

Các giới hạn này là quy tắc chung của local variable dùng `var`, không phải ngoại lệ riêng cho `_`.

## 5. Điều gì xảy ra khi initializer được thực thi?

Biến không tên không làm mất tác dụng phụ của biểu thức khởi tạo. Khi câu lệnh khai báo được thực thi:

1. Java đánh giá biểu thức initializer.
2. Nếu biểu thức hoàn tất bình thường, giá trị của nó được gán cho biến không tên.
3. Chương trình không thể đọc giá trị thông qua `_` ở các câu lệnh sau.
4. Nếu initializer ném exception, câu lệnh khai báo kết thúc đột ngột theo exception đó.

Ví dụ:

```java
static int writeAuditRecord(Request request) {
    System.out.println("Audit request: " + request.id());
    return request.id().length();
}

void handle(Request request) {
    int _ = writeAuditRecord(request);
    continueProcessing(request);
}
```

`writeAuditRecord` vẫn chạy và ghi audit. Giá trị `int` trả về được bỏ qua. Nếu phương thức ném exception, `continueProcessing` sẽ không chạy trừ khi exception được xử lý ở nơi phù hợp.

Nếu một lời gọi method có thể viết trực tiếp thành expression statement và không cần khai báo biến, cách viết ngắn hơn thường dễ đọc hơn:

```java
writeAuditRecord(request);
```

Hãy dùng biến không tên khi vị trí cú pháp cần một khai báo hoặc khi khai báo làm rõ ý định bỏ qua kết quả, chẳng hạn biến lặp, resource hoặc tham số không dùng.

## 6. Những điều cần nhớ

- `_` là từ khóa dành riêng, không phải tên biến thông thường.
- Biến cục bộ không tên được khởi tạo nhưng không thể được tham chiếu trong code.
- Có thể khai báo nhiều biến không tên trong cùng scope vì chúng không tạo ra tên để xung đột.
- Khai báo không tên trong block và phần khởi tạo của basic `for` bắt buộc có initializer.
- Enhanced `for` lấy giá trị từ phần tử đang lặp; try-with-resources khởi tạo resource theo biểu thức resource.
- Khi dùng `var`, initializer luôn cần thiết và phải đủ thông tin để suy luận kiểu; `var` chỉ cho phép một declarator.
- Unnamed pattern cũng dùng `_`, nhưng có ngữ nghĩa khớp dữ liệu và quy tắc riêng.
- Tính năng đã chính thức từ Java 22 theo JEP 456; không cần `--enable-preview` để sử dụng trên Java 22 trở lên.

## Tài liệu tham khảo

- [JEP 456: Unnamed Variables & Patterns](https://openjdk.org/jeps/456)
- [Java SE 26 Language Guide — Unnamed Variables and Patterns](https://docs.oracle.com/en/java/javase/26/language/unnamed-variables-patterns.html)
- [Java Language Specification, Java SE 26 — §14.4 Local Variable Declarations](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-14.html#jls-14.4)
- [Java Language Specification, Java SE 26 — §6.1 Declarations](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-6.html#jls-6.1)
- [Java SE 22 — Changes to the Java Language Specification for Unnamed Variables and Patterns](https://docs.oracle.com/en/java/javase/22/docs/specs/unnamed-jls.html)
