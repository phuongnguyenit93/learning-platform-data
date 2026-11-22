# Phạm vi học tập của module Java Core Pattern Matching

**Nhóm kiến thức:** Nhập môn pattern matching  
**Đối tượng:** Người học đã có nền tảng Java Core và muốn đọc, viết, bảo trì mã kiểm tra kiểu dữ liệu rõ ràng hơn.

## 1. Module này giải quyết vấn đề gì?

Trong Java, chương trình thường nhận một giá trị có kiểu khai báo rộng (ví dụ `Object`, interface hoặc lớp cha), rồi phải xác định kiểu thực tế để xử lý. Cách truyền thống thường dùng `instanceof`, ép kiểu thủ công và nhiều nhánh `if/else`. Khi cấu trúc dữ liệu phức tạp hơn, các thao tác đó dễ tạo mã lặp, bỏ sót trường hợp hoặc đặt biến sai phạm vi.

**Pattern matching** cho phép đối chiếu giá trị với một *pattern* (mẫu). Khi giá trị khớp, Java có thể đồng thời cung cấp các biến đã được kiểm tra kiểu để sử dụng trong phạm vi hợp lệ. Với *record pattern*, việc khớp còn có thể tách các thành phần của một `record`. Pattern matching giúp diễn đạt ý định rõ hơn, nhưng không thay thế mọi dạng đa hình hoặc mọi cấu trúc điều kiện.

**Mục tiêu của module:** hiểu các pattern đã ổn định trong Java, lựa chọn cấu trúc phù hợp, xử lý an toàn những nhánh không khớp và áp dụng vào bài toán Java Core thực tế.

## 2. Kiến thức cần có và phiên bản Java

Người học nên biết khai báo biến, lớp/interface, kế thừa, `instanceof`, ép kiểu, `if/else`, `switch`, phương thức và cách biên dịch một tệp `.java`. Kiến thức cơ bản về `record` và `sealed` giúp đọc phần nâng cao; module sẽ giải thích vai trò của chúng trong việc khớp mẫu.

| Nền tảng | Tính năng nằm trong phạm vi | Lưu ý |
| --- | --- | --- |
| Java 17 trở lên | Pattern matching cho `instanceof` | Tính năng này đã chính thức từ Java 16; dùng Java 17 là đủ để học phần đó. |
| Java 21 trở lên | Pattern matching cho `switch`, record patterns, nhánh có điều kiện `when` | Các tính năng cốt lõi nêu ở đây đã chính thức trong Java 21, không cần `--enable-preview`. |

**Môi trường khuyến nghị:** JDK 21 hoặc mới hơn để chạy toàn bộ ví dụ. Nếu chỉ có JDK 17, học và chạy phần `instanceof` trước; ví dụ `switch` với type pattern hoặc record pattern bên dưới yêu cầu Java 21. Khi biên dịch, cần dùng `javac` đúng phiên bản, không chỉ có JRE để chạy chương trình.

## 3. Những nội dung module bao phủ

### 3.1. Type pattern và `instanceof`

- Phân biệt phép kiểm tra kiểu với việc gắn *pattern variable*: `if (value instanceof String text)` vừa kiểm tra vừa tạo biến `text` có kiểu `String` tại nơi hợp lệ.
- Hiểu *flow scoping*: biến pattern chỉ dùng được tại những vị trí mà trình biên dịch biết chắc việc khớp đã thành công. Không mặc nhiên dùng được sau mọi khối `if`, trong nhánh không khớp hoặc sau điều kiện kết hợp bất cẩn.
- So sánh cách viết có pattern với `instanceof` rồi ép kiểu tường minh; chọn cách biểu đạt ngắn và dễ kiểm chứng.

### 3.2. Pattern matching cho `switch`

- Dùng type pattern trong nhánh `case` để phân loại một giá trị theo kiểu thực tế; hiểu khác biệt giữa `switch` statement và `switch` expression.
- Biết khi nào cần `case null`, khi nào cần `default`; không giả định `default` luôn xử lý `null`.
- Dùng `when` để bổ sung điều kiện cho một pattern đã khớp, chẳng hạn phân biệt chuỗi rỗng với chuỗi có nội dung.
- Hiểu **dominance**: nhánh tổng quát đặt trước có thể khiến nhánh cụ thể phía sau không bao giờ tới được và gây lỗi biên dịch.
- Hiểu **exhaustiveness**: biểu thức `switch` phải xử lý đầy đủ các trường hợp theo kiểm tra của trình biên dịch; với tập kiểu đóng như `sealed` hierarchy, có thể diễn đạt các trường hợp cụ thể thay cho một nhánh `default` quá rộng.

### 3.3. Record patterns

- Phân biệt khai báo một `record` với việc dùng *record pattern* để kiểm tra và tách các thành phần của nó.
- Đọc và viết ví dụ `case Point(int x, int y)` để lấy các component của `Point` sau khi khớp.
- Nhận biết pattern lồng nhau ở mức cơ bản khi record chứa record; cân nhắc độ dễ đọc trước khi lồng quá nhiều tầng.
- Nhớ rằng record pattern nhắm vào cấu trúc `record`, không tự động bóc tách mọi lớp Java thông thường.

### 3.4. Thiết kế, giới hạn và chất lượng mã

- Lựa chọn giữa `if/else`, `instanceof`, `switch` và gọi phương thức đa hình dựa trên số nhánh, cấu trúc dữ liệu và khả năng mở rộng.
- Kiểm tra các tình huống `null`, kiểu không mong đợi, pattern bị che khuất, nhánh thiếu và thứ tự guard.
- Hiểu giới hạn kiểm tra kiểu do *type erasure*: không dùng `instanceof List<String>` để kiểm tra chính xác phần tử generic ở runtime; `List<?>` là ví dụ pattern có thể kiểm tra theo kiểu khả kiểm.
- Cải tiến mã cũ mà vẫn giữ hành vi nghiệp vụ, tránh dùng pattern matching chỉ để làm mã trông hiện đại.

## 4. Ví dụ định hướng: một chương trình Java 21 chạy được

Ví dụ này giới thiệu bốn ý chính của module: `instanceof` có biến pattern, `switch` theo kiểu, guard `when` và record pattern. Nó là bản đồ khái niệm; từng cơ chế sẽ được học kỹ hơn ở các bài chuyên đề.

Tạo tệp **`PatternMatchingScope.java`**:

```java
public class PatternMatchingScope {
    record Point(int x, int y) {}

    static String describe(Object input) {
        return switch (input) {
            case null -> "NULL";
            case String s when s.isBlank() -> "Blank String";
            case String s -> "String: " + s;
            case Point(int x, int y) -> "Point=(" + x + "," + y + ")";
            default -> "Other";
        };
    }

    public static void main(String[] args) {
        Object item = "Java";

        if (item instanceof String text) {
            System.out.println("Length=" + text.length());
        }

        System.out.println(describe(new Point(3, 5)));
        System.out.println(describe("   "));
        System.out.println(describe(null));
    }
}
```

Biên dịch và chạy bằng **JDK 21+**:

```bash
javac --release 21 PatternMatchingScope.java
java PatternMatchingScope
```

Kết quả:

```text
Length=4
Point=(3,5)
Blank String
NULL
```

Giải thích:

1. `item instanceof String text` chỉ cho phép sử dụng `text` trong nhánh đã khớp; chương trình in độ dài chuỗi `Java` là `4`.
2. `case Point(int x, int y)` khớp với record `Point(3, 5)` và tách hai component để tạo `Point=(3,5)`.
3. Guard `case String s when s.isBlank()` được kiểm tra trước `case String s` tổng quát, nên chuỗi ba dấu cách được mô tả là `Blank String`.
4. `case null` xử lý riêng giá trị `null`; `default` dành cho những giá trị khác chưa được các pattern bao phủ.

Thử đổi đối số thành `42`, `"Hello"` hoặc `new Point(0, 0)` để quan sát nhánh được chọn. Nếu chuyển `case String s` lên trước nhánh `String` có `when`, trình biên dịch sẽ phát hiện nhánh phía sau bị che khuất.

## 5. Ranh giới nội dung của module

Trong phạm vi học tập này, từ **pattern** chỉ cơ chế *pattern matching của ngôn ngữ Java*. Nó **không** đồng nghĩa với:

- **Regular expression:** `java.util.regex.Pattern` và `Matcher` dùng để tìm/kiểm tra mẫu ký tự trong chuỗi, là chủ đề khác.
- **Java Platform Module System (JPMS):** `module-info.java`, `requires` và `exports` giải quyết đóng gói/phụ thuộc module, không phải pattern matching.
- **Reflection, annotation processing hoặc parser:** những cơ chế kiểm tra/biến đổi cấu trúc chương trình ở runtime hay lúc biên dịch, nằm ngoài mục tiêu nhập môn ở đây.
- **Các đề xuất preview chưa ổn định hoặc cú pháp của ngôn ngữ khác:** không cần bật preview feature để hoàn thành bài thực hành chuẩn Java 21.

Module cũng không đặt mục tiêu thay thế toàn bộ thiết kế hướng đối tượng bằng các chuỗi kiểm tra kiểu. Nếu hành vi thuộc trách nhiệm của từng lớp và có thể giải quyết tốt bằng đa hình, đó vẫn là lựa chọn cần cân nhắc.

## 6. Lộ trình học và mức độ thực hành mong đợi

1. **Nhận diện vấn đề:** tìm phần mã kiểm tra kiểu rồi ép kiểu thủ công; giải thích điểm lặp và rủi ro.
2. **Làm chủ `instanceof` pattern:** viết lại một nhánh đơn giản, hiểu phạm vi của pattern variable và trường hợp không khớp.
3. **Chuyển sang `switch` pattern:** phân loại nhiều kiểu, thêm `null`/`default`, nhận diện nhánh bị che khuất và trường hợp còn thiếu.
4. **Làm việc với `record`:** khai báo record, khớp và tách component, đọc pattern lồng nhau đơn giản.
5. **Vận dụng có kiểm chứng:** thêm guard `when`, viết trường hợp kiểm thử đúng/sai kiểu và `null`, so sánh với giải pháp đa hình hoặc điều kiện truyền thống.

Một bài thực hành được xem là đạt khi người học có thể giải thích **vì sao nhánh được chọn**, **biến nào hợp lệ tại vị trí nào**, **điều gì xảy ra khi giá trị không khớp**, đồng thời biên dịch và kiểm tra được kết quả.

## 7. Các hiểu lầm cần tránh

- Cho rằng pattern matching làm mất nhu cầu kiểm tra `null`. `instanceof` type pattern không khớp `null`; khi dùng `switch`, xử lý `null` một cách chủ động.
- Nghĩ rằng biến khai báo trong pattern tồn tại ở mọi nhánh. Phạm vi của biến chịu sự phân tích luồng điều khiển của Java.
- Đặt pattern rộng trước pattern hẹp rồi ngạc nhiên khi trình biên dịch báo nhánh không thể tới được.
- Nhầm record pattern với phép giải cấu trúc tùy ý trên class thông thường hoặc cho rằng generic type argument luôn được xác định tại runtime.
- Sao chép ví dụ Java 21 vào dự án dùng compiler Java 17 rồi kết luận cú pháp Java bị lỗi; luôn kiểm tra phiên bản JDK và cấu hình build.
- Chuyển `if/else` sang `switch` mà không giữ nguyên logic nhánh, hành vi `null` và kết quả trả về.

## 8. Tự đánh giá và tài liệu tiếp nối

Sau bài định hướng này, người học nên tự trả lời được: `instanceof` pattern khác ép kiểu thủ công ở đâu; vì sao `when` cần đặt trước pattern rộng; record pattern lấy dữ liệu gì; một `switch` expression phải đầy đủ đến mức nào; và khi nào không nên dùng pattern matching.

Tài liệu đặc tả để tra cứu cú pháp và ranh giới phiên bản:

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394).
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440).

**Kết quả mong đợi của module:** đọc hiểu và viết được các pattern phổ biến trong Java Core, biết xử lý các trường hợp biên và đưa ra lựa chọn thiết kế dựa trên tính đúng đắn, tính rõ ràng và khả năng bảo trì.
