# Lộ trình học Pattern Matching trong Java

## 1. Học để giải quyết vấn đề gì?

Trong Java, nhiều đoạn mã phải kiểm tra kiểu của một đối tượng rồi mới lấy dữ liệu ra để xử lý. Trước đây, lập trình viên thường dùng `instanceof`, ép kiểu thủ công, chuỗi `if/else` hoặc `switch` chỉ xét các hằng số. **Pattern matching** cho phép diễn tả trực tiếp việc “giá trị có khớp với một mẫu không; nếu khớp thì lấy ra những biến nào?”. Nhờ đó, luồng xử lý theo kiểu dữ liệu rõ ràng hơn và giảm những phép ép kiểu lặp lại.

Ví dụ, `if (value instanceof String text)` vừa kiểm tra `value` có là `String`, vừa khai báo biến `text` đã có kiểu `String` cho nhánh hợp lệ. Với Java 21, bạn còn có thể dùng mẫu kiểu trong `switch` và tách thành phần của `record` bằng **record pattern**.

Bài này là **bản đồ học tập**: học theo thứ tự nào, phải biết gì ở mỗi chặng, luyện bài gì và dùng tiêu chí nào để biết đã sẵn sàng đi tiếp. Các bài chuyên sâu sau đó sẽ giải thích đầy đủ từng cơ chế.

**Đích đến:** Bạn có thể đọc, viết và kiểm thử mã sử dụng `instanceof` pattern, pattern matching cho `switch`, record pattern, và biết khi nào nên kết hợp chúng với `record`/`sealed`. Bạn cũng phải nhận ra phạm vi biến, nhánh bị che khuất, trường hợp `null` và giới hạn tương thích phiên bản.

## 2. Chọn JDK và kiến thức nền

| Mốc học | Phiên bản Java | Trạng thái |
| --- | --- | --- |
| Type pattern trong `instanceof` | Java 16 trở lên | Tính năng chính thức từ Java 16; dùng được trên Java 17 |
| `record` (kiểu dữ liệu) | Java 16 trở lên | Tính năng chính thức; là nền tảng để học record pattern |
| `sealed` class/interface | Java 17 trở lên | Tính năng chính thức; hữu ích cho `switch` bao quát mọi kiểu con |
| Type pattern, guard và `case null` trong `switch` | Java 21 trở lên | Pattern matching cho `switch` chính thức từ Java 21 |
| Record pattern và record pattern lồng nhau | Java 21 trở lên | Chính thức từ Java 21 |

Nên sử dụng **JDK 21 trở lên** khi học trọn lộ trình. Nếu dự án đang ở Java 17, hãy học và áp dụng phần `instanceof` trước; **không sao chép cú pháp pattern `switch`/record pattern của Java 21 vào mã biên dịch `--release 17`**. Java 21 dùng được tất cả ví dụ ổn định bên dưới mà không cần `--enable-preview`. Một số cải tiến pattern matching ở những bản Java khác còn có thể ở trạng thái preview; hãy kiểm tra tài liệu đúng phiên bản JDK và xem chúng là phần mở rộng, không phải điều kiện để hoàn thành lộ trình này.

Trước khi bắt đầu, nên nắm: kiểu tham chiếu và tính đa hình; `Object`, kế thừa và interface; `instanceof` cùng ép kiểu; `if/else` và `&&`/`||`; `switch` expression; ý nghĩa của `null`. Sau đó tìm hiểu cấu trúc `record` và `sealed` ở mức cơ bản. Không cần học reflection hay biểu thức chính quy trước: pattern matching ở đây **không phải** regex và không tự phân tích mọi cấu trúc đối tượng bất kỳ.

Kiểm tra môi trường:

```bash
java -version
javac -version
```

Cả hai lệnh phải trỏ đến JDK phù hợp với phần bạn chuẩn bị học. Khi biên dịch bằng JDK mới cho phiên bản mục tiêu, hãy dùng `javac --release 17` hoặc `javac --release 21` để chủ động kiểm tra tính tương thích.

## 3. Thứ tự học từ cơ bản đến ứng dụng

| Chặng | Trọng tâm | Bài luyện và dấu hiệu hoàn thành |
| --- | --- | --- |
| 0. Nhận diện bài toán | So sánh kiểm tra kiểu + ép kiểu thủ công với pattern matching; ôn `switch` expression và `null` | Chỉ ra đoạn mã ép kiểu thừa và giải thích vì sao cần kiểm tra kiểu |
| 1. Type pattern trong `instanceof` | `instanceof String text`; điều kiện khớp; biến được gán khi mẫu khớp | Viết hàm nhận `Object`, xử lý `String` và `Integer` mà không ép kiểu thủ công |
| 2. Phạm vi biến theo luồng điều khiển | Flow scoping; `&&`; phủ định + thoát sớm; nhánh không chắc chắn | Giải thích vì sao một biến mẫu có hoặc không có hiệu lực tại từng dòng |
| 3. Pattern matching trong `switch` | `case String s`, `case null`, `when`, `default`, thứ tự case, dominance | Chuyển chuỗi `if/else` phân loại kiểu thành `switch` hợp lệ trên Java 21 |
| 4. Record pattern | Tách các thành phần `record`, mẫu lồng nhau và sự khác biệt với lấy thuộc tính bằng accessor | Lấy tọa độ hoặc dữ liệu lồng nhau mà không khai báo biến tạm thủ công |
| 5. Sealed + kiểm tra tính đầy đủ | Tập kiểu con được phép, exhaustiveness, nhánh có guard và nhánh còn lại | Viết `switch` expression cho mô hình kiểu đóng mà không cần `default` tùy tiện |
| 6. Thiết kế và kiểm thử | Chọn cấu trúc phù hợp, xử lý `null`, trường hợp biên, đọc lỗi biên dịch | Hoàn thành bài tổng hợp, kiểm thử nhánh hợp lệ/lỗi và giải thích lựa chọn thiết kế |

Các chặng có thứ tự phụ thuộc: **kiểm tra kiểu → phạm vi biến → phân nhánh nhiều mẫu → tách dữ liệu → bao quát kiểu con → thiết kế ứng dụng**. Không nên bắt đầu từ record pattern lồng nhau nếu còn nhầm khi nào biến mẫu `instanceof` có hiệu lực.

### Chặng 0 — Nhìn thấy vấn đề trước khi học cú pháp

Hãy đọc đoạn mã cũ:

```java
Object value = "Java";
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
```

Ở đây `instanceof` đã xác nhận kiểu, nhưng lập trình viên vẫn phải ép kiểu lại. Câu hỏi dẫn đường: điều gì sẽ thay đổi nếu trình biên dịch cung cấp ngay biến đã đúng kiểu sau khi mẫu khớp? Đáp án dẫn sang chặng 1; bài tập là chỉ ra các bước **kiểm tra → ép kiểu → sử dụng**.

### Chặng 1 — Học `instanceof` type pattern trước

Cùng ý tưởng trên có thể viết:

```java
Object value = "Java";
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Biến `text` chỉ biểu thị đối tượng đã khớp mẫu `String`; đây không phải phép chuyển đổi dữ liệu từ kiểu này sang kiểu khác. Khi `value` là `null`, mẫu kiểu trong `instanceof` không khớp và thân `if` không chạy.

Bài thực hành độc lập, chạy được với Java 17:

```java
public class PatternMatchingBasics {
    static String describe(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "Văn bản: " + text;
        }
        if (value instanceof Integer number) {
            return "Số nguyên: " + number;
        }
        return "Giá trị khác";
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(21));
        System.out.println(describe(null));
    }
}
```

Lưu thành `PatternMatchingBasics.java`, rồi chạy:

```bash
javac -encoding UTF-8 --release 17 PatternMatchingBasics.java
java PatternMatchingBasics
```

Kết quả mong đợi:

```text
Văn bản: Java
Số nguyên: 21
Giá trị khác
```

**Tự kiểm tra:** Nếu đổi `"Java"` thành `""`, tại sao hàm trả về `"Giá trị khác"`? Vì biến `text` chỉ được dùng trong nhánh khi đồng thời thỏa `instanceof` **và** điều kiện `!text.isBlank()`.

### Chặng 2 — Nắm flow scoping để tránh lỗi biên dịch

Phạm vi biến pattern phụ thuộc vào **luồng điều khiển chứng minh mẫu đã khớp**; không đơn giản chỉ phụ thuộc vào cặp dấu ngoặc nhọn.

```java
if (value instanceof String text && text.length() > 3) {
    System.out.println(text);
}
```

Ở vế phải của `&&`, `text` đã được xác nhận vì vế trái phải đúng thì vế phải mới được đánh giá. Ngược lại, đoạn dưới **sai và không biên dịch**:

```java
// SAI: text có thể chưa được tạo khi vế trái là false.
if (value instanceof String text || text.isEmpty()) {
    System.out.println(value);
}
```

Một dạng khác cần biết là kiểm tra phủ định rồi thoát sớm:

```java
if (!(value instanceof String text)) {
    return;
}
System.out.println(text.length()); // Sau if, text chắc chắn đã khớp.
```

Đoạn này minh họa **thân một phương thức trả về `void`**, với `value` là biến đã được khai báo. Hãy tự vẽ hai nhánh điều khiển và chỉ ra vì sao dòng sau `if` chỉ có thể chạy khi `value` khớp `String`. Không cố dùng biến mẫu khi trình biên dịch chưa chứng minh mẫu đã khớp.

### Chặng 3 — Mở rộng từ một mẫu sang `switch` nhiều mẫu (Java 21)

Khi cần xử lý nhiều kiểu khác nhau của cùng một giá trị, `switch` cho phép mỗi `case` gắn với một pattern:

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "Không có dữ liệu";
        case String s when s.isBlank() -> "Chuỗi trống";
        case String s -> "Chuỗi: " + s;
        case Integer n -> "Số: " + n;
        default -> "Kiểu khác";
    };
}
```

Đây là **đoạn phương thức minh họa** đặt bên trong một lớp, yêu cầu Java 21 trở lên. `when` là điều kiện bổ sung (**guard**): chỉ xét sau khi mẫu kiểu khớp. Nhánh `String` có guard đặt trước nhánh `String` tổng quát để dữ liệu đặc biệt được xử lý đúng.

Ba quy tắc phải hiểu:

1. **Thứ tự và dominance:** Một case tổng quát bao phủ mọi giá trị của case cụ thể phía sau sẽ khiến case sau không thể được chọn, và trình biên dịch báo lỗi. Ví dụ đặt `case Object o` trước `case String s` là sai.
2. **`null` phải được xét riêng nếu có thể xuất hiện:** `switch` pattern trên tham chiếu `null` mà không có nhánh xử lý `null` sẽ ném `NullPointerException` trong các trường hợp thông thường; `default` không tự thay thế `case null`.
3. **`switch` expression cần bao quát mọi trường hợp có thể có:** Với kiểu `Object` có thể nhận nhiều loại giá trị, ví dụ trên dùng `default`. Với tập kiểu con đóng bằng `sealed`, trình biên dịch có thể kiểm tra tính đầy đủ mà không cần `default`.

Bài tập: viết hàm phân loại đầu vào `null`, chuỗi rỗng, chuỗi thường, số nguyên và một đối tượng bất kỳ; thêm ca kiểm thử cho từng nhánh. Chủ động đổi thứ tự hai `case String` rồi quan sát thông báo dominance.

### Chặng 4 — Học record pattern để tách dữ liệu có cấu trúc (Java 21)

`record` mô tả những thành phần dữ liệu cố định; **record pattern** cho phép kiểm tra và rút các thành phần đó ra ngay tại vị trí đối sánh.

```java
record Point(int x, int y) {}

static String location(Object value) {
    if (value instanceof Point(int x, int y)) {
        return "(" + x + ", " + y + ")";
    }
    return "Không phải điểm";
}
```

Đoạn trên minh họa khai báo `record` và phương thức cùng phạm vi lớp, yêu cầu Java 21 trở lên. Với `new Point(2, 5)`, hàm trả về `(2, 5)`. Không cần `Point p = (Point) value` rồi gọi `p.x()` và `p.y()`.

Sau khi thành thạo mẫu một tầng, chuyển sang mẫu lồng nhau:

```java
record Point(int x, int y) {}
record Segment(Point start, Point end) {}

// Bên trong một phương thức, với biến Object value:
if (value instanceof Segment(Point(int x1, int y1), Point(int x2, int y2))) {
    System.out.println("Từ " + x1 + "," + y1 + " đến " + x2 + "," + y2);
}
```

Đây là **mã minh họa cần đặt vào lớp/phương thức phù hợp**, không phải chương trình hoàn chỉnh; nếu ghép với ví dụ `Point` trước, chỉ khai báo `Point` một lần. Bài tập: đổi cấu trúc thành `Order(Customer customer, Money amount)` (các kiểu này do bạn định nghĩa), sau đó tách dần từng thành phần; thử `null` để thấy mẫu kiểu/record không mặc nhiên khớp giá trị `null`.

Đừng nhầm record pattern với việc tự do truy cập mọi trường `private` của lớp bất kỳ. Cơ chế này dựa trên **cấu trúc thành phần của `record`** và các quy tắc kiểu của Java.

### Chặng 5 — Kết hợp `sealed` để xử lý mô hình kiểu đóng

`sealed` giới hạn những kiểu con trực tiếp được phép triển khai một interface hoặc kế thừa một lớp. Khi `switch` duyệt hết những kiểu con phù hợp, trình biên dịch có thể chứng minh tính đầy đủ (**exhaustiveness**). Đây là lý do `sealed` rất hữu ích cho bài toán biểu diễn nhiều trường hợp của một miền dữ liệu.

Ví dụ tổng hợp đầy đủ sau sử dụng Java 21, đồng thời có `record`, guard, `switch` expression và `case null`:

```java
public class PatternMatchingAdvanced {
    sealed interface Shape permits Circle, Rect {}

    record Circle(double radius) implements Shape {}
    record Rect(double width, double height) implements Shape {}

    static String describe(Shape shape) {
        return switch (shape) {
            case null -> "Không có hình";
            case Circle(double r) when r <= 0 -> "Hình tròn không hợp lệ";
            case Circle(double r) -> "Hình tròn, bán kính=" + r;
            case Rect(double w, double h) when w <= 0 || h <= 0 ->
                    "Hình chữ nhật không hợp lệ";
            case Rect(double w, double h) ->
                    "Hình chữ nhật, kích thước=" + w + "x" + h;
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Circle(2)));
        System.out.println(describe(new Rect(3, 4)));
        System.out.println(describe(null));
    }
}
```

Lưu vào `PatternMatchingAdvanced.java`:

```bash
javac -encoding UTF-8 --release 21 PatternMatchingAdvanced.java
java PatternMatchingAdvanced
```

Kết quả mong đợi:

```text
Hình tròn, bán kính=2.0
Hình chữ nhật, kích thước=3.0x4.0
Không có hình
```

Tại sao không cần `default`? Vì `Shape` chỉ cho phép `Circle` và `Rect`, các trường hợp hợp lệ của mỗi record đều có một nhánh **không kèm guard** để bao quát phần còn lại, và `null` cũng đã được xử lý. Hai guard cho giá trị không hợp lệ chỉ là nhánh ưu tiên; chúng không tự đủ để bao quát cả kiểu. Hãy thử thêm một kiểu con `Triangle` vào `permits` mà chưa thêm `case`; lỗi tính đầy đủ của `switch` giúp phát hiện chỗ xử lý còn thiếu.

Trong mô hình mở, nơi các kiểu con có thể tăng lên ngoài tầm kiểm soát, `default` hoặc cách tổ chức khác có thể phù hợp hơn. Không nên biến mọi hệ phân cấp lớp thành `sealed` chỉ để có thể viết `switch`.

### Chặng 6 — Dùng pattern matching có chủ đích

Đến đây, hãy so sánh các lựa chọn trong cùng bài toán:

| Tình huống | Cân nhắc sử dụng |
| --- | --- |
| Chỉ cần phân nhánh theo một hoặc hai kiểu đối tượng | `instanceof` pattern có thể ngắn và dễ đọc hơn |
| Cần xử lý nhiều loại dữ liệu của một giá trị | `switch` pattern, chú ý case tổng quát và `null` |
| Dữ liệu vốn là `record` và cần lấy các thành phần | Record pattern, kể cả lồng nhau khi còn dễ đọc |
| Có miền dữ liệu đóng với những biến thể xác định | `sealed` kết hợp `switch` để kiểm tra tính đầy đủ |
| Hành vi thuộc về chính các đối tượng và có thể gọi qua interface | Cân nhắc **đa hình**; không nhất thiết viết một `switch` dài ở mọi nơi |

Pattern matching là cách biểu đạt kiểm tra/tách dữ liệu, không thay thế nguyên tắc thiết kế hướng đối tượng. Nếu cùng một `switch` theo kiểu dữ liệu lặp lại ở nhiều lớp, hãy tự hỏi một phương thức đa hình có làm cho trách nhiệm rõ ràng hơn không. Nếu cấu trúc `record` lồng quá sâu, việc đặt tên biến trung gian hoặc tách hàm có thể dễ bảo trì hơn.

## 4. Bài tập tổng hợp theo từng mức

**Mức cơ bản (Java 17):** Viết `format(Object input)` cho `String`, `Integer`, `Double` và các giá trị khác, dùng `instanceof` pattern; không có ép kiểu thủ công. Thử `null`, chuỗi trắng và số âm. Giải thích vì sao mẫu `instanceof` không khớp `null`.

**Mức trung bình (Java 21):** Chuyển `format` thành `switch` expression. Phân biệt chuỗi trắng bằng `when`, có `case null` và `default`. Chủ động đặt case quá tổng quát lên trên để quan sát lỗi dominance, rồi sửa thứ tự. Ghi rõ trường hợp nào yêu cầu `default`.

**Mức nâng cao (Java 21):** Tự thiết kế một `sealed interface Payment permits Cash, Card, Transfer`, trong đó các biến thể là `record`. Dùng record pattern để lấy dữ liệu, guard để kiểm tra số tiền hợp lệ, và viết `switch` expression mô tả giao dịch. Thử thêm kiểu thanh toán thứ tư để thấy tác dụng của exhaustiveness; không lấy dữ liệu thanh toán thật và không dùng ví dụ này để quyết định nghiệp vụ tài chính thực tế.

**Bài hoàn thiện:** Với mỗi bài trên, viết bảng ca kiểm thử gồm đầu vào, nhánh được chọn, đầu ra mong đợi; thử biên âm/không/ dương (nếu áp dụng), `null`, kiểu không khớp và thay đổi tập kiểu con. Chạy với `--release` đúng phiên bản mục tiêu. Đánh giá xem phương thức còn rõ nghĩa không sau khi thêm nhiều case.

## 5. Những lỗi thường gặp cần nhận ra ngay

- **Dùng cú pháp Java 21 trong dự án Java 17:** `switch` expression có từ trước Java 21 nhưng `case String s`, `when` và record pattern như ở đây cần Java 21 trở lên để dùng ở trạng thái chính thức.
- **Nghĩ biến mẫu luôn có phạm vi trong cả phương thức:** Phạm vi phụ thuộc vào đường đi chắc chắn làm mẫu khớp; `||`, phủ định và thoát sớm phải được phân tích riêng.
- **Đặt case tổng quát trước case cụ thể:** Case phía sau có thể bị dominance và không biên dịch.
- **Cho rằng `default` bao gồm `null`:** Cần hiểu quy tắc `null` của pattern `switch` và chủ động viết `case null` khi đầu vào có thể rỗng.
- **Chỉ viết các case có guard trong một `switch` đóng:** Guard có thể sai; cần nhánh không guard hoặc phương án bao quát hợp lệ để compiler chứng minh exhaustive.
- **Nhầm record pattern với một cơ chế “mở khóa” mọi lớp:** Record pattern dựa trên record component; không phải phản chiếu trường riêng của mọi đối tượng.
- **Lạm dụng phân nhánh theo kiểu:** Với hành vi gắn chặt vào loại đối tượng, thiết kế đa hình đôi khi dễ bảo trì hơn hàng loạt `switch` trùng nhau.
- **Chạy ví dụ với cấu hình không nhất quán:** Kiểm tra phiên bản `java`, `javac` và cờ `--release`; các ví dụ dùng tính năng chính thức của Java 21 không cần bật preview.

## 6. Tự đánh giá và lịch học gợi ý

Một lịch học tham khảo, có thể giãn theo tốc độ cá nhân:

| Buổi | Nội dung | Sản phẩm cần có |
| --- | --- | --- |
| 1 | Nền tảng + `instanceof` pattern | Chương trình `PatternMatchingBasics` chạy đúng |
| 2 | Flow scoping và các lỗi biên dịch cố ý | Giải thích được ít nhất ba đường đi của biến pattern |
| 3 | `switch` pattern, guard, `null` và dominance | Bộ phân loại kiểu có kiểm thử rõ các case |
| 4 | `record`, record pattern, mẫu lồng nhau | Một ví dụ tách record không ép kiểu thủ công |
| 5 | `sealed`, exhaustiveness, bài tổng hợp | `PatternMatchingAdvanced` và phiên bản có thêm kiểu con |
| 6 | Refactor và kiểm thử | Quyết định được trường hợp dùng pattern matching hay đa hình |

**Bạn đã sẵn sàng học chuyên sâu hơn khi có thể tự trả lời:**

1. Pattern matching khác gì với `instanceof` + ép kiểu truyền thống?
2. Vì sao `text` hợp lệ bên phải `&&` trong một điều kiện, nhưng không chắc hợp lệ bên phải `||`?
3. Khi nào một `case` bị case trước che khuất? Guard ảnh hưởng tới việc chọn nhánh thế nào?
4. `switch` pattern xử lý `null` ra sao? Vì sao `default` không tự đồng nghĩa với `case null`?
5. Record pattern tách thông tin nào từ một `record`, và điều gì xảy ra khi mẫu không khớp?
6. `sealed` giúp trình biên dịch kiểm tra `switch` đầy đủ như thế nào khi hệ phân cấp thay đổi?
7. Bạn sẽ chọn `instanceof`, `switch`, record pattern hay đa hình cho một bài toán cụ thể vì lý do gì?

Nếu chưa giải thích được câu nào, quay lại đúng chặng liên quan rồi tự sửa một ví dụ. Không cần thuộc lòng mọi quy tắc ngôn ngữ trước khi viết thử: điều quan trọng là hiểu **điều kiện khớp, biến được ràng buộc, phạm vi an toàn và các trường hợp còn thiếu**.

## 7. Tài liệu chuẩn để học tiếp

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): động cơ, type pattern và phạm vi biến; chính thức từ Java 16.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): switch theo mẫu, guard, null, dominance và exhaustiveness; chính thức từ Java 21.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): tách thành phần record và lồng mẫu; chính thức từ Java 21.
- [Oracle Java SE 21 Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html): danh sách tính năng và phiên bản chính thức.

Hãy dùng tài liệu theo **phiên bản Java mà dự án thực sự biên dịch và chạy**. Phần mở rộng ở những bản JDK mới có thể được học sau khi nắm chắc các tính năng chính thức của Java 17/21.
