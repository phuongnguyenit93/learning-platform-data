# JEP 456: mục đích và phạm vi sử dụng dấu gạch dưới làm biến hoặc mẫu không tên

## 1. Vấn đề JEP 456 giải quyết

Trong Java, có những vị trí cú pháp bắt buộc phải khai báo một biến hoặc một mẫu, dù chương trình không cần đọc giá trị tương ứng. Ví dụ:

- Vòng lặp `for-each` cần một biến nhận từng phần tử, nhưng thân vòng lặp có thể chỉ đếm số phần tử.
- Khối `catch` cần tham số ngoại lệ, nhưng chương trình chỉ cần thực hiện nhánh xử lý lỗi và không cần đọc đối tượng ngoại lệ.
- Lambda cần tham số đầu vào, nhưng phần thân chỉ trả về một kết quả cố định.
- Mẫu bản ghi cần mô tả các thành phần theo đúng thứ tự, nhưng chương trình chỉ quan tâm đến một vài thành phần.

Trong mã nguồn chưa bật preview JEP 443 ở Java 21 (hoặc ở các phiên bản trước đó), lập trình viên thường đặt một tên tạm như `ignored`, `unused`, `ex` hoặc `color`, rồi để biến đó không được sử dụng. Tên tạm vẫn là một tên có thể được tham chiếu, khiến người đọc phải tự suy luận rằng giá trị ấy bị bỏ qua có chủ ý.

JEP 456 đưa ký tự gạch dưới đơn (`_`) vào các vị trí được hỗ trợ để thể hiện rõ ý định: giá trị hoặc thành phần này cần tồn tại theo yêu cầu của cú pháp, nhưng chương trình không cần đặt tên để sử dụng nó. Nhờ vậy, mã nguồn bớt tên giả, dễ đọc hơn và thể hiện chính xác phần dữ liệu nào được quan tâm.

## 2. Trạng thái của tính năng trong Java hiện đại

Unnamed Variables and Patterns được giới thiệu ở Java 21 dưới dạng preview với JEP 443. JEP 456 hoàn thiện tính năng trong Java 22; từ Java 22, có thể sử dụng mà không bật preview. Tài liệu ngôn ngữ Java SE 27 vẫn có chương riêng cho tính năng này và bảng tổng kết của Oracle ghi nhận đây là tính năng permanent từ Java 22.

Vì vậy, các ví dụ trong bài sử dụng cú pháp chuẩn của Java 22 trở lên. Khi biên dịch mã nguồn với JDK 22 hoặc mới hơn, không cần thêm `--enable-preview` cho riêng tính năng này.

## 3. Hai nhóm cú pháp dùng dấu gạch dưới

JEP 456 bao gồm hai nhóm có liên quan nhưng có vai trò khác nhau:

| Nhóm | Ý nghĩa | Ví dụ |
|---|---|---|
| Biến không tên (*unnamed variable*) | Khai báo một biến nhưng không cung cấp tên để đọc giá trị về sau; nếu có biểu thức khởi tạo, biểu thức đó vẫn được đánh giá. | `for (Order _ : orders)` |
| Mẫu không tên (*unnamed pattern*) | Bỏ qua một thành phần trong mẫu bản ghi mà không tạo biến mẫu để giữ thành phần đó. | `case Point(double x, _) -> ...` |

Trong mẫu kiểu, `_` cũng có thể thay cho tên biến mẫu khi vẫn cần kiểm tra kiểu. Ví dụ `case Freelancer _ -> ...` kiểm tra đối tượng có kiểu `Freelancer`, nhưng không tạo một tên để tham chiếu đối tượng đó trong nhánh `case`.

Điểm chung là chương trình không thể đọc giá trị thông qua `_`. Đây là một từ khóa dành cho các vị trí được quy định, không phải tên biến thông thường và cũng không phải ký hiệu đại diện có thể đặt tùy ý trong mọi biểu thức.

## 4. Biến không tên: những vị trí được phép khai báo

Java cho phép khai báo biến không tên trong sáu ngữ cảnh sau.

| Ngữ cảnh | Ví dụ | Khi nào hữu ích |
|---|---|---|
| Câu lệnh khai báo biến cục bộ trong một khối | `var _ = iterator.next();` | Khi ngữ cảnh cần một khai báo biến nhưng giá trị khởi tạo không được dùng tiếp. |
| Phần khai báo tài nguyên của `try-with-resources` | `try (var _ = openResource()) { ... }` | Khi cần mở và tự động đóng tài nguyên, nhưng không cần gọi phương thức trên biến tài nguyên. |
| Phần khởi tạo của vòng lặp `for` thông thường | `for (int i = 0, _ = start(); i < 3; i++)` | Khi cần đánh giá một biểu thức khởi tạo có kết quả trả về nhưng không cần giữ kết quả đó. |
| Biến nhận phần tử của vòng lặp `for-each` | `for (Order _ : orders)` | Khi cần duyệt từng phần tử để thực hiện công việc khác, chẳng hạn đếm số phần tử. |
| Tham số của khối `catch` | `catch (IOException _)` | Khi cần xử lý loại ngoại lệ đó nhưng không cần đọc đối tượng ngoại lệ. |
| Tham số hình thức của lambda | `_ -> "N/A"` | Khi lambda phải nhận tham số nhưng phần thân không cần giá trị đầu vào. |

Có thể khai báo nhiều biến không tên `_` trong cùng một khối. Chẳng hạn, nếu một thuật toán cần lấy bỏ qua một số phần tử từ hàng đợi trước khi chọn phần tử tiếp theo, mỗi khai báo `Caller _ = q.remove();` biểu thị rõ rằng kết quả của lần lấy đó không được dùng. Các khai báo này không xung đột như những biến có tên trùng nhau vì không có tên để tham chiếu.

### 4.1. Vòng lặp chỉ cần số lần lặp

Giả sử chương trình cần đếm số đơn hàng trong một tập hợp. Giá trị của từng đơn hàng không được dùng trong thân vòng lặp:

```java
record Order(String id) {}

static int countOrders(Iterable<Order> orders) {
    int count = 0;

    for (Order _ : orders) {
        count++;
    }

    return count;
}
```

Khai báo `Order _` cho biết vòng lặp vẫn nhận từng phần tử, nhưng thân vòng lặp không cần tham chiếu đến phần tử đó. Vòng lặp vẫn duyệt toàn bộ `orders`; `_` không làm thay đổi số lần lặp hoặc cách thực thi thân vòng lặp.

### 4.2. Xử lý ngoại lệ mà không cần đối tượng ngoại lệ

Nếu chương trình chỉ cần chuyển sang một nhánh xử lý khi dữ liệu không hợp lệ, có thể bỏ tên tham số ngoại lệ:

```java
static boolean isValidNumber(String value) {
    try {
        Integer.parseInt(value);
        return true;
    } catch (NumberFormatException _) {
        return false;
    }
}
```

`catch (NumberFormatException _)` vẫn bắt ngoại lệ `NumberFormatException`. Chương trình chỉ bỏ qua việc đặt tên cho đối tượng ngoại lệ; loại ngoại lệ được bắt và luồng điều khiển của `try-catch` không thay đổi.

Nếu cần ghi log, lấy thông điệp hoặc kiểm tra nguyên nhân, hãy dùng một tên có ý nghĩa thay vì `_`:

```java
catch (NumberFormatException exception) {
    logger.warn("Giá trị không phải số: {}", exception.getMessage());
}
```

### 4.3. Lambda không sử dụng tham số

Một lambda có thể cần khớp với kiểu hàm nhận đầu vào, dù kết quả của nó không phụ thuộc vào đầu vào đó:

```java
Function<Order, String> defaultLabel = _ -> "Chưa phân loại";
```

Tham số vẫn thuộc chữ ký của lambda và vẫn được truyền vào khi hàm được gọi. Tuy nhiên, phần thân không có tên để tham chiếu đến giá trị này.

### 4.4. Quản lý vòng đời tài nguyên

`try-with-resources` yêu cầu khai báo tài nguyên hoặc cung cấp một biến tài nguyên phù hợp. Nếu mục tiêu chỉ là xác nhận tài nguyên có thể được mở rồi đóng tự động, có thể dùng biến không tên:

```java
static boolean canOpen(Path path) {
    try (var _ = Files.newBufferedReader(path)) {
        return true;
    } catch (IOException _) {
        return false;
    }
}
```

Khi thoát khỏi khối `try`, tài nguyên vẫn được đóng theo quy tắc của `try-with-resources`, kể cả khi biến tài nguyên không có tên để sử dụng trong thân khối. Ví dụ này cần các import `java.io.IOException`, `java.nio.file.Files` và `java.nio.file.Path`.

### 4.5. Khai báo cục bộ và vòng lặp `for` thông thường

Biến không tên cũng có thể xuất hiện trong câu lệnh khai báo biến cục bộ hoặc danh sách khởi tạo của vòng lặp `for`:

```java
static int initializeCounter() {
    System.out.println("Bắt đầu vòng lặp");
    return 0;
}

static void printThreeNumbers() {
    for (int i = 0, _ = initializeCounter(); i < 3; i++) {
        System.out.println(i);
    }
}
```

`initializeCounter()` vẫn được gọi và vẫn trả về một giá trị `int`; giá trị trả về được khởi tạo vào biến không tên rồi không được sử dụng. Trong thực tế, chỉ nên khai báo biến không tên khi ngữ cảnh thực sự cần một khai báo. Nếu một lời gọi phương thức có thể đứng độc lập thành câu lệnh, không cần tạo biến giả chỉ để bỏ qua kết quả.

## 5. Mẫu không tên trong Record Patterns

Record pattern cho phép kiểm tra một đối tượng có thuộc kiểu bản ghi hay không, đồng thời tách các thành phần của bản ghi thành các mẫu con. Khi một thành phần không liên quan đến phép tính hoặc quyết định hiện tại, có thể thay mẫu con tương ứng bằng `_`.

Ví dụ, bản ghi `ColoredPoint` chứa một điểm và một màu:

```java
record Point(double x, double y) {}

enum Color {
    RED, GREEN, BLUE
}

record ColoredPoint(Point point, Color color) {}
```

Giả sử chương trình chỉ cần tính khoảng cách giữa hai điểm, không cần màu sắc:

```java
static double distance(Object first, Object second) {
    if (first instanceof ColoredPoint(Point p1, _) &&
        second instanceof ColoredPoint(Point p2, _)) {
        return Math.hypot(p2.x() - p1.x(), p2.y() - p1.y());
    }

    return -1;
}
```

Trong `ColoredPoint(Point p1, _)`, mẫu `Point p1` vẫn kiểm tra và lấy thành phần điểm để sử dụng. Mẫu `_` ở vị trí thứ hai cho biết thành phần màu không cần được đặt tên hoặc kiểm tra bằng một mẫu kiểu riêng. Mẫu không tên không tạo biến có thể tham chiếu.

### 5.1. Bỏ qua hoàn toàn thành phần hay chỉ bỏ tên?

Có hai cách viết tùy theo yêu cầu kiểm tra:

```java
// Không cần ràng buộc kiểu riêng cho thành phần thứ hai.
if (value instanceof ColoredPoint(Point point, _)) {
    // Dùng point.
}

// Vẫn yêu cầu thành phần thứ hai có kiểu Color,
// nhưng không cần giữ thành phần đó trong một biến có tên.
if (value instanceof ColoredPoint(Point point, Color _)) {
    // Dùng point.
}
```

Hai cách viết có ý nghĩa khác nhau:

- `_` đứng riêng là mẫu không tên cho thành phần bản ghi. Mẫu này khớp với giá trị thành phần tương ứng, kể cả `null`, và không áp đặt thêm phép kiểm tra kiểu.
- `Color _` là mẫu kiểu có biến mẫu không tên. Nó vẫn kiểm tra thành phần có thể khớp với kiểu `Color`; vì đây là mẫu kiểu, giá trị `null` không khớp.

Do đó, hãy chọn dạng mẫu dựa trên điều kiện cần kiểm tra. Không nên bỏ kiểu nếu kiểu của thành phần vẫn là một phần quan trọng của điều kiện.

## 6. Mẫu kiểu không tên trong `switch`

Khi chỉ cần phân nhánh theo kiểu đối tượng, không cần giữ đối tượng khớp mẫu trong một biến, có thể dùng `_` thay cho tên biến mẫu:

```java
sealed interface Employee
    permits Salaried, Freelancer, Intern {}

record Salaried(String name, long salary) implements Employee {}
record Freelancer(String name) implements Employee {}
record Intern(String name) implements Employee {}

static String category(Employee employee) {
    return switch (employee) {
        case Salaried salaried -> "Nhân viên hưởng lương";
        case Freelancer _, Intern _ -> "Nhân sự hợp đồng hoặc thực tập";
    };
}
```

`case Freelancer _` vẫn kiểm tra kiểu `Freelancer`, nhưng không tạo biến để dùng trong nhánh. Tương tự, `case Intern _` kiểm tra kiểu `Intern`. Vì các mẫu trong nhãn `case` không khai báo biến mẫu có tên, hai nhánh có thể được gộp trong cùng một nhãn.

Lưu ý rằng `case Freelancer _` không phải mẫu khớp mọi kiểu đối tượng. Nó chỉ khớp đối tượng phù hợp với kiểu `Freelancer`. Nếu cần nhánh mặc định cho các trường hợp còn lại, vẫn dùng `default` theo quy tắc của `switch`.

## 7. Những giới hạn cần nhớ

1. **Chỉ dùng `_` ở vị trí được ngôn ngữ cho phép.** Biến không tên được hỗ trợ trong sáu ngữ cảnh ở mục 4. Mẫu không tên đứng riêng được dùng trong danh sách thành phần của record pattern. Mẫu kiểu như `Freelancer _` có thể dùng ở vị trí pattern phù hợp, chẳng hạn nhãn `case` của `switch`.
2. **Không thể đọc giá trị thông qua `_`.** Các biểu thức như `System.out.println(_)` hoặc việc dùng `_` làm đối số không hợp lệ vì `_` không phải một tên biến có thể tham chiếu.
3. **`instanceof _` không phải mẫu tổng quát.** Mẫu không tên đứng riêng không thể dùng làm mẫu cấp cao nhất, ví dụ `value instanceof _` là không hợp lệ. Hãy dùng một kiểu cụ thể hoặc một cấu trúc pattern phù hợp với mục đích kiểm tra.
4. **Không thay thế tên của mọi loại khai báo.** JEP 456 không biến `_` thành cách đặt tên chung cho field, tham số hình thức của phương thức hoặc mọi định danh khác. Hãy giới hạn nó trong các ngữ cảnh đã được đặc tả.
5. **Việc khởi tạo và tác dụng phụ vẫn diễn ra.** `for (Order _ : orders)` vẫn duyệt từng phần tử; `var _ = nextValue()` vẫn đánh giá `nextValue()`; tài nguyên được khai báo bằng `_` vẫn được đóng tự động. Dấu gạch dưới chỉ thể hiện rằng mã không cần tham chiếu đến giá trị bằng tên.
6. **Không phải lúc nào cũng cần khai báo biến không tên.** Nếu có thể viết trực tiếp một câu lệnh gọi phương thức mà không cần giữ kết quả, hãy ưu tiên cách viết trực tiếp. `_` hữu ích khi cấu trúc cú pháp cần một khai báo hoặc một mẫu.

Ngoài ra, dấu gạch dưới đơn đã là từ khóa dành riêng từ Java 9. Không thể dùng `_` làm tên biến thông thường trong mã Java hiện đại. Các tên có thêm ký tự, chẳng hạn `_ignored`, vẫn là định danh khác; tuy nhiên, chúng không mang ý nghĩa biến không tên của JEP 456.

## 8. Cách áp dụng trong dự án

Với mã nguồn yêu cầu Java 22 trở lên, có thể biên dịch ví dụ bằng JDK tương ứng mà không bật preview:

```bash
javac --release 22 Example.java
```

Nếu dự án dùng phiên bản Java mới hơn, hãy đặt `--release` theo phiên bản ngôn ngữ và nền tảng mà dự án hỗ trợ. Cần nhớ rằng `--release 22` chỉ định mức tương thích Java 22; nó không làm cho bytecode chạy được trên runtime cũ hơn Java 22.

Khi rà soát mã hiện có, có thể thay tên tạm bằng `_` nếu giá trị thật sự không được sử dụng và vị trí khai báo thuộc phạm vi hỗ trợ. Giữ tên có nghĩa nếu giá trị cần xuất hiện trong log, điều kiện, phép tính hoặc xử lý tiếp theo. Mục tiêu là làm rõ ý định của mã, không phải thay mọi tên biến ít được dùng bằng dấu gạch dưới.

## 9. Tài liệu tham khảo

- [JEP 456: Unnamed Variables & Patterns](https://openjdk.org/jeps/456) — mục tiêu và phạm vi thiết kế của tính năng.
- [Oracle Java SE 27: Unnamed Variables and Patterns](https://docs.oracle.com/en/java/javase/27/language/unnamed-variables-patterns.html) — hướng dẫn cú pháp và ví dụ trên phiên bản Java hiện hành.
- [Oracle Java SE 27: Java Language Changes Summary](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-summary.html) — xác nhận JEP 456 là tính năng permanent từ Java 22.
- [Java SE 22: Unnamed Variables and Patterns — JLS changes](https://docs.oracle.com/en/java/javase/22/docs/specs/unnamed-jls.html) — đặc tả các thay đổi ngôn ngữ liên quan đến khai báo không tên và mẫu không tên.
