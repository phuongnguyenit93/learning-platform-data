# Phân biệt biến không tên, mẫu không tên và biến mẫu có tên

## 1. Vì sao cần phân biệt?

Java dùng dấu gạch dưới đơn (`_`) cho nhiều cấu trúc có ý nghĩa khác nhau. Khi đọc mã nguồn, cần nhìn vào vị trí của `_` và phần cú pháp đứng trước nó để xác định chương trình đang khai báo một biến, bỏ qua một thành phần bản ghi hay kiểm tra kiểu của một giá trị.

Ba khái niệm chính trong bài là:

- **Biến không tên (*unnamed variable*):** một khai báo biến có kiểu và có thể được khởi tạo, nhưng không có tên để đọc giá trị.
- **Mẫu không tên (*unnamed pattern*):** dấu `_` đứng riêng trong danh sách thành phần của record pattern. Nó bỏ qua thành phần tương ứng mà không đặt điều kiện kiểu và không khai báo biến mẫu.
- **Biến mẫu có tên (*named pattern variable*):** một type pattern như `Color color`. Nó kiểm tra kiểu của giá trị và đặt giá trị khớp vào biến `color` để dùng trong phạm vi mà phép khớp đã được xác nhận.

Ngoài ba khái niệm này, cần nhận ra dạng `Color _`. Đây là **type pattern có biến mẫu không tên (*unnamed pattern variable*)**: vẫn kiểm tra kiểu `Color`, nhưng không tạo tên để chương trình tham chiếu. Dạng này thường bị nhầm với mẫu không tên `_` đứng riêng.

## 2. Bảng so sánh nhanh

| Cú pháp | Loại cấu trúc | Có kiểm tra kiểu? | Có tên để đọc giá trị? | Vị trí điển hình |
|---|---|---|---|---|
| `Order _ = nextOrder();` | Biến không tên | Không phải phép thử kiểu; kiểu khai báo vẫn là `Order` | Không | Khai báo biến cục bộ |
| `TaggedPoint(Point p, _)` | Mẫu không tên | Không thêm điều kiện kiểu cho thành phần bị bỏ qua | Không khai báo biến mẫu | Thành phần của record pattern |
| `TaggedPoint(Point p, Color _)` | Type pattern có biến mẫu không tên | Có, kiểm tra thành phần khớp `Color` | Không | Thành phần của record pattern |
| `TaggedPoint(Point p, Color color)` | Type pattern có biến mẫu tên `color` | Có, kiểm tra thành phần khớp `Color` | Có, trong phạm vi pattern variable hợp lệ | Thành phần của record pattern |
| `value instanceof Color color` | Type pattern có biến mẫu tên `color` | Có, kiểm tra `Color` | Có, khi phép khớp thành công | `instanceof`, `switch` |
| `value instanceof Color _` | Type pattern có biến mẫu không tên | Có, kiểm tra `Color` | Không | `instanceof`, `switch` |

Điểm quan trọng nhất: `Color _` vẫn là một **type pattern**. Chỉ có tên biến mẫu bị bỏ đi. Trong khi đó, `_` đứng riêng là một **unnamed pattern**, chỉ dùng làm thành phần của record pattern và không đưa ra điều kiện kiểu riêng.

## 3. Biến không tên: khai báo có giá trị nhưng không có tên sử dụng

Biến không tên vẫn là một khai báo biến. Khai báo có kiểu tường minh hoặc kiểu suy luận, và biểu thức khởi tạo vẫn được đánh giá. Khác biệt nằm ở chỗ chương trình không thể tham chiếu đến giá trị qua tên `_`.

Ví dụ, vòng lặp chỉ cần đếm số đơn hàng mà không cần đọc từng đơn hàng:

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

`Order _` khai báo biến nhận từng phần tử của vòng lặp. Mỗi vòng lặp vẫn lấy phần tử tiếp theo và thực thi thân vòng lặp; chỉ có giá trị phần tử không được đặt một tên để sử dụng.

Biến không tên cũng hữu ích khi lời gọi có tác dụng phụ hoặc khi một cấu trúc cú pháp yêu cầu khai báo:

```java
static void processQueue(Queue<Order> queue) {
    Order _ = queue.remove(); // Lấy và bỏ qua đơn hàng đầu tiên.
    Order _ = queue.remove(); // Có thể khai báo một biến không tên khác.
    Order next = queue.remove();

    System.out.println("Đang xử lý: " + next.id());
}
```

Hai khai báo `Order _` trong cùng khối không xung đột tên. Tuy nhiên, nếu một lời gọi phương thức có thể được viết thành câu lệnh độc lập và không cần khai báo biến, không cần tạo biến không tên chỉ để bỏ qua kết quả.

Trong Java 22, biến không tên được hỗ trợ ở các vị trí sau:

- Khai báo biến cục bộ trong một khối, ví dụ `var _ = iterator.next();`.
- Khai báo tài nguyên trong `try-with-resources`, ví dụ `try (var _ = openResource()) { ... }`.
- Phần khởi tạo của vòng lặp `for` thông thường.
- Biến nhận phần tử trong vòng lặp `for-each`.
- Tham số ngoại lệ của `catch`.
- Tham số hình thức của lambda.

Ví dụ `catch (IOException _)` vẫn bắt `IOException`, và `try (var _ = openResource())` vẫn đóng tài nguyên theo quy tắc `try-with-resources`. Biến không tên không phải cách viết thay thế cho field hoặc tham số hình thức của phương thức thông thường.

## 4. Mẫu không tên: bỏ qua một thành phần của record pattern

Mẫu không tên là dấu `_` đứng riêng trong danh sách mẫu thành phần của record pattern. Nó có nghĩa là chương trình không cần kiểm tra thành phần này bằng một type pattern riêng và cũng không cần giữ thành phần trong biến mẫu.

Xét các kiểu dữ liệu sau:

```java
record Point(int x, int y) {}
record TaggedPoint(Point point, Object tag) {}
enum Color { RED, GREEN, BLUE }
```

Nếu chỉ cần lấy điểm, có thể bỏ qua thành phần `tag`:

```java
static boolean hasPoint(Object value) {
    return value instanceof TaggedPoint(Point point, _);
}
```

Mẫu `Point point` kiểm tra và ràng buộc thành phần thứ nhất vào biến `point`. Mẫu `_` ở vị trí thứ hai khớp với thành phần `tag` mà không áp đặt thêm điều kiện về kiểu. Mẫu này không khai báo một biến mẫu nào cho `tag`.

Một mẫu không tên luôn khớp với giá trị thành phần tương ứng, kể cả khi giá trị đó là `null`. Vì thế, `TaggedPoint(Point point, _)` vẫn có thể khớp khi `tag` là `null`, miễn là đối tượng ngoài cùng là một `TaggedPoint` và mẫu `Point point` khớp.

Mẫu không tên chỉ được dùng trong danh sách thành phần của record pattern. Không thể dùng nó làm mẫu cấp cao nhất như `value instanceof _`.

## 5. Type pattern có biến mẫu không tên: `Type _`

Khi viết `Color _`, phần `Color` vẫn là kiểu của type pattern. Java vẫn kiểm tra giá trị có khớp với kiểu `Color` hay không; dấu `_` chỉ nói rằng chương trình không cần tên để tham chiếu đến giá trị đã khớp.

Với `TaggedPoint` ở trên, có thể yêu cầu `tag` phải là một `Color` nhưng không cần đọc màu đó:

```java
static boolean hasColorTag(Object value) {
    return value instanceof TaggedPoint(Point point, Color _);
}
```

So sánh hai mẫu:

```java
// Thành phần tag có thể là bất kỳ giá trị nào, kể cả null.
value instanceof TaggedPoint(Point point, _)

// Thành phần tag phải khớp kiểu Color.
value instanceof TaggedPoint(Point point, Color _)
```

Vì kiểu khai báo của `tag` là `Object`, mẫu `Color _` chỉ khớp khi giá trị thực sự là một `Color`; nó không khớp `null`. Dù phép khớp thành công, chương trình vẫn không thể truy cập màu thông qua `_`.

Dạng `Type _` cũng dùng được ở vị trí type pattern cấp cao nhất:

```java
if (value instanceof Color _) {
    System.out.println("Giá trị là một màu");
}
```

Đây là type pattern có biến mẫu không tên, khác với mẫu không tên `_` đứng riêng. Cú pháp `value instanceof _` vẫn không hợp lệ vì unnamed pattern không được dùng làm mẫu cấp cao nhất.

## 6. Biến mẫu có tên: kiểm tra kiểu và giữ giá trị để sử dụng

Khi phần sau của chương trình cần đọc giá trị đã khớp, hãy dùng một biến mẫu có tên:

```java
static String colorName(Object value) {
    if (value instanceof TaggedPoint(Point point, Color color)) {
        return color.name();
    }

    return "Không có thẻ màu phù hợp";
}
```

`Color color` vừa kiểm tra thành phần `tag` có kiểu phù hợp với `Color`, vừa ràng buộc giá trị vào biến `color`. Trong nhánh `if` nơi điều kiện đã khớp, chương trình có thể gọi `color.name()`.

Biến mẫu cũng có thể xuất hiện ở cấp cao nhất:

```java
static String describe(Object value) {
    if (value instanceof Color color) {
        return "Màu: " + color.name();
    }

    return "Không phải màu";
}
```

Phạm vi của biến mẫu tuân theo quy tắc flow scoping của Java. Ví dụ, trong điều kiện `value instanceof Color color && color != Color.RED`, biến `color` được dùng ở vế phải vì vế phải chỉ được đánh giá khi phép thử kiểu ở vế trái thành công. Một biến mẫu có tên không thể được sử dụng ở nhánh mà Java chưa xác nhận phép khớp.

## 7. Khác biệt về kiểm tra kiểu và giá trị `null`

Không nên suy luận rằng mọi type pattern đều xử lý `null` giống nhau. Quy tắc phụ thuộc vào vị trí của pattern:

| Mẫu | Vị trí | `null` có khớp không? | Lý do |
|---|---|---|---|
| `_` | Thành phần của record pattern | Có | Unnamed pattern luôn là null-matching. |
| `Color color` | Type pattern cấp cao nhất, ví dụ `value instanceof Color color` | Không | Type pattern cấp cao nhất không khớp `null`. |
| `Color _` | Type pattern cấp cao nhất, ví dụ `value instanceof Color _` | Không | Đây vẫn là type pattern; chỉ tên biến mẫu bị bỏ đi. |
| `Color color` | Thành phần record pattern có kiểu khai báo `Color` | Có | Type pattern lồng là null-matching nếu nó unconditional đối với kiểu thành phần. |
| `Color _` | Thành phần record pattern có kiểu khai báo `Object` | Không | `Color` không unconditional đối với `Object`, nên `null` không khớp. |

Ví dụ, nếu record khai báo thành phần màu có kiểu `Color`:

```java
record ColoredPoint(Point point, Color color) {}

static boolean acceptsNullColor(Object value) {
    return value instanceof ColoredPoint(Point point, Color _);
}
```

Trong trường hợp này, `Color _` là type pattern lồng và unconditional đối với kiểu khai báo `Color` của thành phần. Theo quy tắc pattern matching của Java, nó là null-matching. Nếu kiểu khai báo của thành phần là `Object`, cùng type pattern `Color _` không unconditional và không khớp `null`.

Biến mẫu có tên và biến mẫu không tên có cùng quy tắc kiểm tra kiểu và null-matching khi chúng là cùng một type pattern. Việc thêm hoặc bỏ tên chỉ ảnh hưởng khả năng tham chiếu đến giá trị sau khi khớp.

## 8. Chọn cú pháp nào trong mã thực tế?

- Dùng **biến không tên** (`Order _`) khi vị trí khai báo cần một biến nhưng chương trình không cần đọc giá trị đó.
- Dùng **mẫu không tên** (`TaggedPoint(Point point, _)`) khi muốn bỏ qua hoàn toàn một thành phần của record pattern, không cần thêm điều kiện kiểu.
- Dùng **type pattern có biến mẫu không tên** (`Color _`) khi vẫn cần kiểm tra kiểu nhưng không cần giữ giá trị để sử dụng.
- Dùng **biến mẫu có tên** (`Color color`) khi cần đọc giá trị đã khớp trong điều kiện, nhánh `if` hoặc nhánh `switch`.

Trong `switch`, các type pattern không khai báo biến mẫu có tên có thể được gộp trong cùng nhãn `case`, ví dụ `case Integer _, Long _ -> ...`. Nếu cần dùng giá trị của một trong các mẫu, hãy đặt tên và xử lý các nhánh theo quy tắc pattern-variable của Java.

Những lỗi thường gặp cần tránh:

1. Dùng `value instanceof _` với ý định kiểm tra một giá trị bất kỳ. Mẫu không tên đứng riêng chỉ hợp lệ trong danh sách thành phần của record pattern.
2. Dùng `_` như một biến thông thường, chẳng hạn `System.out.println(_)`. `_` là từ khóa dành riêng, không phải tên có thể tham chiếu.
3. Dùng `Color _` khi thực sự cần gọi phương thức trên giá trị màu. Hãy đổi thành `Color color` và sử dụng `color`.
4. Nghĩ rằng `Color _` và `_` đứng riêng có cùng ý nghĩa. Dạng thứ nhất vẫn kiểm tra kiểu; dạng thứ hai không thêm điều kiện kiểu cho thành phần bị bỏ qua.

## 9. Phiên bản Java và tài liệu tham khảo

Unnamed Variables and Patterns được giới thiệu dưới dạng preview ở Java 21 với JEP 443 và trở thành tính năng chính thức trong Java 22 với JEP 456. Các ví dụ trong bài dùng cú pháp đã hoàn thiện từ Java 22; khi biên dịch với JDK 22 trở lên không cần bật `--enable-preview` cho tính năng này.

- [JEP 456: Unnamed Variables & Patterns](https://openjdk.org/jeps/456) — mục tiêu và thiết kế của tính năng.
- [Oracle Java SE 27: Unnamed Variables and Patterns](https://docs.oracle.com/en/java/javase/27/language/unnamed-variables-patterns.html) — ví dụ hiện hành về biến không tên, unnamed pattern và unnamed pattern variable.
- [Java SE 22: Unnamed Variables and Patterns — JLS changes](https://docs.oracle.com/en/java/javase/22/docs/specs/unnamed-jls.html) — quy tắc cú pháp, khai báo và pattern matching của Java 22.
- [Oracle Java SE 27: Java Language Changes Summary](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-summary.html) — lịch sử phát hành và trạng thái permanent từ Java 22.
