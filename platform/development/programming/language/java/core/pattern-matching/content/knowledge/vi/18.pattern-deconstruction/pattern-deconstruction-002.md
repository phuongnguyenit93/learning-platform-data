# Lấy nhiều component thay cho gọi accessor lặp lại

## Mục tiêu

Khi xử lý một `record` có nhiều thành phần, nhất là record chứa record khác, mã Java thường phải gọi nhiều accessor như `rect.origin().x()`, `rect.origin().y()`, `rect.size().width()`. **Record pattern (deconstruction pattern)** cho phép mô tả cấu trúc cần lấy ngay trong phép khớp và ràng buộc nhiều component vào biến cùng lúc.

Sau bài học, bạn sẽ biết:
- Vì sao chuỗi accessor lặp lại làm mã xử lý dữ liệu nhiều cấp khó đọc.
- Cách dùng `record pattern` để tách nhiều component, kể cả record lồng nhau.
- Cách chọn `if`/`instanceof` hoặc `switch` để đưa các biến đã bóc tách vào phần xử lý.
- Cách sử dụng `var` để suy luận kiểu, dùng `when` hoặc `&&` để bổ sung điều kiện.
- Những khác biệt cần nhớ: kiểu record, `null`, nhánh không khớp, thứ tự `case`, phạm vi biến và chi phí thực thi.

**Phiên bản:** Record patterns được chuẩn hóa trong **Java 21** (JEP 440). Từ Java 21, pattern matching cho `switch` (JEP 441) cũng là tính năng chính thức. Các ví dụ dùng JDK 21 trở lên, không cần `--enable-preview`.

## 1. Vấn đề: đọc nhiều component bằng accessor

Giả sử có ba record mô tả một hình chữ nhật:

```java
record Point(int x, int y) {}
record Size(int width, int height) {}
record Rectangle(String id, Point origin, Size size) {}
```

Để lấy mã hình chữ nhật, vị trí và kích thước, cách gọi accessor truyền thống là:

```java
// Giả sử rect, rect.origin() và rect.size() đều khác null.
String id = rect.id();
int x = rect.origin().x();
int y = rect.origin().y();
int width = rect.size().width();
int height = rect.size().height();

System.out.println(id + " @ (" + x + ", " + y + ") - "
    + width + "x" + height);
```

Cách này **đúng và phù hợp** khi cần vài thành phần. Nhưng khi phải xử lý nhiều cấp, cụm `rect.origin()` và `rect.size()` lặp lại, khiến cấu trúc dữ liệu và điều kiện rẽ nhánh khó quan sát.

Một cách cải thiện trong Java 17 là lưu record trung gian trước:

```java
Point origin = rect.origin();
Size size = rect.size();

int x = origin.x();
int y = origin.y();
int width = size.width();
int height = size.height();
```

Cách này giảm gọi accessor lặp lại và rõ ràng. Từ Java 21, record pattern còn cho phép **khớp toàn bộ hình dạng và ràng buộc các biến trong một pattern**, rất hữu ích khi mã đang phân nhánh theo dữ liệu.

## 2. Deconstruction: lấy nhiều component trong một pattern

Với `Rectangle`, có thể viết:

```java
// Đặt trong một phương thức có biến value kiểu Object:
if (value instanceof Rectangle(
        String id,
        Point(int x, int y),
        Size(int width, int height))) {
    System.out.println(id + " @ (" + x + ", " + y + ") - "
        + width + "x" + height);
}
```

Pattern này thực hiện đồng thời:
1. Kiểm tra `value` là một `Rectangle` khác `null`.
2. Ràng buộc component `id` với biến `id`.
3. Lấy component `origin` và yêu cầu nó khớp `Point(int x, int y)`; từ đó ràng buộc `x`, `y`.
4. Lấy component `size` và yêu cầu nó khớp `Size(int width, int height)`; từ đó ràng buộc `width`, `height`.
5. Chỉ chạy phần thân `if` khi toàn bộ cấu trúc khớp.

Đó là **nested record pattern**: record pattern bên ngoài chứa hai record pattern bên trong. Mã sử dụng ngay các giá trị đã được ràng buộc, không cần gọi `rect.origin().x()` hay `rect.size().height()` trong phần thân.

Bên trong record pattern, `String id`, `int x`, `int width` là các **type pattern** ở vị trí component; `Point(...)` và `Size(...)` là **record pattern** lồng nhau. Vì vậy deconstruction kết hợp kiểm tra kiểu với bóc tách cấu trúc.

### Dùng var khi kiểu đã rõ

Nếu trình biên dịch đã biết kiểu của component, có thể viết:

```java
if (value instanceof Rectangle(
        var id,
        Point(var x, var y),
        Size(var width, var height))) {
    // id: String; x/y/width/height: int
}
```

`var` ở đây là pattern có **kiểu suy luận từ thành phần record**, không phải kiểu động. Dùng tên kiểu tường minh khi muốn người đọc nhìn rõ ranh giới kiểu; dùng `var` khi cấu trúc lồng nhau đã đủ biểu đạt.

**Điều Java 21 chưa hỗ trợ:** Record deconstruction phải nằm trong ngữ cảnh pattern matching như `instanceof` hoặc `switch`. Cú pháp gán destructuring tùy ý sau là **không hợp lệ**:

```java
// Cố ý sai trong Java 21:
var (x, y) = point;
```

Khi chỉ muốn gán từ một record đã biết chắc kiểu, gọi accessor hay tạo biến trung gian vẫn hoàn toàn hợp lý.

## 3. Chương trình Java 21: trước và sau khi dùng record pattern

Tạo file **`DeconstructionComponentsDemo.java`**:

```java
public class DeconstructionComponentsDemo {
    record Point(int x, int y) {}

    record Size(int width, int height) {}

    record Rectangle(String id, Point origin, Size size) {}

    // Cách 1: đọc component bằng accessor.
    // Tiền điều kiện: rect, origin và size khác null.
    static String usingAccessors(Rectangle rect) {
        int x = rect.origin().x();
        int y = rect.origin().y();
        int width = rect.size().width();
        int height = rect.size().height();

        return rect.id() + " origin=(" + x + "," + y
            + ") size=" + width + "x" + height;
    }

    // Cách 2: phân loại và bóc tách bằng nested record pattern.
    static String usingPatterns(Object value) {
        return switch (value) {
            case Rectangle(
                    String id,
                    Point(int x, int y),
                    Size(int width, int height))
                    when width > 0 && height > 0 ->
                id + " origin=(" + x + "," + y
                    + ") size=" + width + "x" + height;

            case Rectangle(var id, var origin, var size) ->
                "invalid rectangle";

            case null -> "null input";

            default -> "unsupported type";
        };
    }

    public static void main(String[] args) {
        Rectangle valid = new Rectangle(
            "R-1", new Point(2, 3), new Size(4, 5));

        System.out.println(usingAccessors(valid));
        System.out.println(usingPatterns(valid));

        System.out.println(usingPatterns(
            new Rectangle("R-2", null, new Size(4, 5))));
        System.out.println(usingPatterns(
            new Rectangle("R-3", new Point(2, 3), new Size(0, 5))));
        System.out.println(usingPatterns(null));
        System.out.println(usingPatterns("other"));
    }
}
```

Lưu file đúng tên và biên dịch/chạy với JDK 21 trở lên:

```bash
javac --release 21 DeconstructionComponentsDemo.java
java DeconstructionComponentsDemo
```

Đầu ra:

```text
R-1 origin=(2,3) size=4x5
R-1 origin=(2,3) size=4x5
invalid rectangle
invalid rectangle
null input
unsupported type
```

**Đọc kết quả:**

| Trường hợp | Cách xử lý | Kết quả |
| --- | --- | --- |
| `R-1` có `Point(2,3)` và `Size(4,5)` | Cả accessor và pattern đều lấy đủ 4 số; guard đúng | Hai dòng thông tin giống nhau |
| `R-2` có `origin == null` | Nested `Point(...)` không khớp; `case Rectangle(var ...)` tiếp nhận | `invalid rectangle` |
| `R-3` có `width == 0` | Pattern lồng nhau khớp nhưng `when width > 0` sai | `invalid rectangle` |
| Giá trị đầu vào `null` | `case null` | `null input` |
| Chuỗi `"other"` | `default` vì không phải `Rectangle` | `unsupported type` |

Hàm `usingAccessors` minh họa cách truy cập dữ liệu trực tiếp khi **đã đảm bảo tiền điều kiện**. Hàm `usingPatterns` đồng thời kiểm tra cấu trúc và phân loại đầu vào; hai hàm không nhất thiết thay thế nhau trong mọi hoàn cảnh. Trong trường hợp hợp lệ, chúng xây dựng cùng chuỗi kết quả.

## 4. Bổ sung điều kiện sau deconstruction

Một record pattern mô tả **kiểu và hình dạng**; các điều kiện nghiệp vụ như chiều rộng/chiều cao dương nên viết ngoài pattern.

**Với instanceof**, nối `&&` sau pattern:

```java
if (value instanceof Rectangle(
        var id, Point(var x, var y), Size(var width, var height))
        && width > 0 && height > 0) {
    // value là Rectangle có origin/size hợp lệ,
    // đồng thời width, height đều dương.
}
```

Nếu cấu trúc không khớp, Java sẽ không đánh giá các phần sau của chuỗi `&&` và không cố sử dụng các biến chưa được ràng buộc.

**Với switch**, đặt guard `when` ngay sau pattern của `case`:

```java
// Trích từ một switch expression:
case Rectangle(
        var id, Point(var x, var y), Size(var width, var height))
        when width > 0 && height > 0 ->
    id + ": " + width + "x" + height;
```

`when` chỉ được xét sau khi pattern khớp. Khi guard trả về `false`, Java tiếp tục tìm nhánh `case` phù hợp khác. Trong chương trình ở mục 3, nhánh `Rectangle(var id, var origin, var size)` đóng vai trò fallback.

**Không nhầm lẫn:** Từ Java 21, pattern matching cho `switch` có cú pháp `when`; không viết `case ... && điềuKiện` theo cú pháp cũ của một số phiên bản preview.

## 5. Null, phạm vi biến và thứ tự case

### 5.1. Deconstruction không tự thay thế toàn bộ kiểm tra null

- `null instanceof Rectangle(...)` là `false`.
- Nếu `Rectangle` không phải `null` nhưng `origin == null`, nested pattern `Point(...)` không khớp và nhánh có nó bị bỏ qua.
- Nếu `size == null`, nested pattern `Size(...)` cũng không khớp.
- `case Rectangle(var id, var origin, var size)` vẫn có thể khớp một `Rectangle` mà **component tham chiếu** như `origin` hoặc `size` bằng `null`. Pattern `var` tại component không bắt buộc giá trị tham chiếu khác `null`.
- Selector của `switch` bằng `null` phải được xử lý tường minh bằng `case null` nếu cần hành vi riêng; chỉ `default` thường không thay thế được xử lý null.

Vì thế, deconstruction có lợi khi cấu trúc dữ liệu yêu cầu đủ các record con: một nhánh cụ thể chỉ chạy nếu chúng hiện diện. Tuy nhiên, những component được ràng buộc có thể mang `null` nếu pattern con cho phép; cần kiểm tra riêng khi nghiệp vụ cấm null.

### 5.2. Các biến chỉ tồn tại trong nhánh đã khớp

`x`, `y`, `width` và `height` trong `if` là **pattern variables**. Trình biên dịch cho phép dùng chúng trong phần thân `if` và các phần điều kiện `&&` mà chắc chắn việc khớp đã thành công. Trong `switch`, chúng dùng được ở guard `when` và phần thân `case` tương ứng.

Không sử dụng những biến đó ở các nhánh khác hoặc bên ngoài phạm vi được phân tích là đã khớp. Đặt tên khác nhau cho các component; khai báo hai biến pattern trùng tên trong cùng pattern là lỗi biên dịch.

### 5.3. Đặt nhánh cụ thể trước nhánh bao quát

Đoạn sau **cố ý sai** khi đặt trong cùng một `switch`:

```java
case Rectangle(var id, var origin, var size) -> "any rectangle";
case Rectangle(var id, Point(var x, var y),
               Size(var width, var height)) -> "detailed";
```

Nhánh đầu đã bao phủ tất cả giá trị `Rectangle` khác `null`, nên nhánh sau không bao giờ được chọn; Java báo lỗi *dominated case*. Hãy đặt nhánh kiểm tra sâu và có guard trước, đặt nhánh tổng quát sau.

Nếu dùng `switch` expression trên selector kiểu `Object`, phải bảo đảm **exhaustive**, ví dụ có `default` để xử lý kiểu khác. `case null` là lựa chọn riêng để xử lý đầu vào null.

## 6. Record pattern và accessor: chọn công cụ phù hợp

| Tình huống | Cách nên cân nhắc | Vì sao |
| --- | --- | --- |
| Chỉ cần một component, ví dụ `user.name()` | Gọi accessor | Đơn giản, ngắn, rõ nghĩa |
| Đã có object chắc chắn hợp lệ và chỉ cần vài trường | Accessor hoặc biến record trung gian | Không phải tạo ngữ cảnh phân nhánh |
| Đang kiểm tra kiểu và lấy nhiều component cùng lúc | `instanceof Record(...)` | Kiểm tra + ràng buộc dữ liệu trong một bước |
| Có nhiều cấu trúc/biến thể cần xử lý | `switch` với record patterns | Nhánh lựa chọn mô tả rõ hình dạng dữ liệu |
| Record lồng nhiều cấp | Nested record pattern có giới hạn độ sâu | Ít chuỗi accessor, dễ thấy cấu trúc mong đợi |
| Pattern quá dài hoặc nghiệp vụ phức tạp | Tách phương thức; giữ accessor nếu rõ hơn | Tránh một biểu thức phân nhánh khó bảo trì |

**Không suy diễn rằng record pattern luôn nhanh hơn.** Deconstruction vẫn dựa trên các accessor của record; Java không cam kết việc thay mã nguồn bằng pattern là một tối ưu hiệu năng. Một record còn có thể tự định nghĩa accessor, vì vậy đừng dùng các phép gọi có tác dụng phụ để biện minh cho việc khớp nhiều lần. Nếu cần đánh giá hiệu năng, đo trong ngữ cảnh thực tế.

**Deconstruction không tạo record mới** và không tự động sao chép sâu. Record có component final nhưng component tham chiếu có thể trỏ đến object mutable. Bóc tách nhiều biến cũng không đồng nghĩa với việc chụp được một snapshot nguyên tử trong chương trình đa luồng.

**Record pattern áp dụng cho record, không cho class bất kỳ.** Với POJO thông thường, hãy dùng type pattern và các method của class. Khi cần ràng buộc nhiều thành phần từ một object thường, Java 21 không có cú pháp deconstruction tùy ý giống một số ngôn ngữ khác.

## 7. Quy trình refactor từ accessor sang deconstruction

1. Xác định record ngoài cùng và cây component thực sự cần đọc.
2. Đọc các biểu thức accessor hiện có, ví dụ `rect.origin().x()`, `rect.origin().y()`, `rect.size().width()`.
3. Đặt record pattern tương ứng tại nơi **đã có** phân nhánh `if`/`instanceof` hoặc `switch`; tránh tạo pattern chỉ để ép mọi code theo một phong cách.
4. Đặt tên biến theo ý nghĩa `x`, `y`, `width`, `height`. Có thể dùng `var` khi kiểu được thể hiện rõ qua record và chữ ký component.
5. Chuyển kiểm tra giá trị sang `&&` hoặc `when`; bổ sung nhánh fallback cho thiếu record con, dữ liệu không hợp lệ và null.
6. Chạy lại trường hợp hợp lệ, trường hợp thiếu component, giá trị biên và đầu vào sai kiểu. Kiểm tra rằng xử lý lỗi vẫn rõ ràng và không bị đổi ngữ nghĩa ngoài ý muốn.

### Bài tập thực hành

Bổ sung `record Color(int red, int green, int blue) {}` và thay định nghĩa `Rectangle` bằng record có thêm component `Color color`. Hãy viết một `switch` lấy đồng thời `id`, `x`, `y`, `width`, `height`, `red`, `green` và `blue` bằng nested record pattern. Guard yêu cầu `width > 0`, `height > 0` và mỗi kênh màu trong khoảng 0..255; một case fallback xử lý component màu thiếu hoặc giá trị không hợp lệ.

Bài tập giúp thấy lợi ích của deconstruction khi cần **nhiều giá trị liên quan nhau** và cũng làm rõ lý do phải kiểm soát độ sâu pattern để dễ đọc.

## Tham khảo

- Oracle Java SE 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Oracle Java SE 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- OpenJDK JEP 440: https://openjdk.org/jeps/440
- OpenJDK JEP 441: https://openjdk.org/jeps/441
