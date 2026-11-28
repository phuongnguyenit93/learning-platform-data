# Kết hợp instanceof pattern và mapMulti để lọc kiểu có biến kết quả

Từ Java 16, pattern matching cho toán tử `instanceof` cho phép kiểm tra kiểu và khai báo biến đại diện cho giá trị đã khớp trong cùng một biểu thức. Khi kết hợp với `Stream.mapMulti`, ta có thể kiểm tra kiểu của từng phần tử, sử dụng trực tiếp biến pattern và phát giá trị phù hợp xuống Stream kết quả.

Cách kết hợp này hữu ích khi Stream nguồn chứa nhiều kiểu đối tượng và mapper cần chọn một số kiểu để xử lý. Mỗi phần tử không khớp có thể không phát kết quả; phần tử khớp có thể phát một hoặc nhiều giá trị đã chuyển đổi.

## 1. Vì sao kết hợp instanceof pattern với mapMulti?

Giả sử một Stream có kiểu phần tử là `Object`, bên trong chứa chuỗi, số nguyên, số thực và các kiểu khác. Ta chỉ muốn lấy chuỗi và chuyển chúng thành chữ hoa.

Nếu dùng cách kiểm tra kiểu truyền thống, mã thường phải kiểm tra `instanceof`, ép kiểu rồi mới sử dụng giá trị:

```java
if (value instanceof String) {
    String text = (String) value;
    emit.accept(text.toUpperCase());
}
```

Pattern matching cho `instanceof` gộp kiểm tra kiểu và khai báo biến:

```java
if (value instanceof String text) {
    emit.accept(text.toUpperCase());
}
```

Ở đây:

- `value instanceof String` kiểm tra đối tượng có phải là một `String` hay không.
- `text` là pattern variable, có kiểu `String`.
- Khi điều kiện đúng, `text` tham chiếu đến chính đối tượng đã khớp.
- Khi điều kiện sai, nhánh thân `if` không chạy và `text` không được sử dụng.

Kết hợp với `mapMulti`, nhánh không khớp chỉ cần không gọi Consumer. Nhánh khớp dùng biến pattern để tạo và phát kết quả, không cần ép kiểu thủ công.

## 2. Cú pháp cơ bản với mapMulti

Ví dụ sau lọc các phần tử kiểu `String` từ một danh sách hỗn hợp:

```java
import java.util.List;

List<Object> values = List.of(
    "Java",
    16,
    2.5,
    "Stream",
    true
);

List<String> texts = values.stream()
    .<String>mapMulti((value, emit) -> {
        if (value instanceof String text) {
            emit.accept(text);
        }
    })
    .toList();
```

Kết quả:

```text
[Java, Stream]
```

Mapper nhận từng phần tử kiểu `Object`. Nếu phần tử là `String`, pattern variable `text` được tạo và gửi qua `emit.accept`. Các phần tử kiểu `Integer`, `Double` hoặc `Boolean` không gọi Consumer nên không xuất hiện trong Stream kết quả.

Type witness `.<String>mapMulti` chỉ rõ kiểu phần tử đầu ra là `String`. Nhờ đó, Consumer trong mapper có kiểu `Consumer<String>`.

## 3. Dùng pattern variable để xử lý ngay giá trị đã khớp

Pattern variable không chỉ giúp tránh ép kiểu. Nó còn cho phép gọi phương thức và đọc thuộc tính của giá trị đã khớp ngay trong nhánh điều kiện.

Ví dụ, ta muốn chuẩn hóa các chuỗi bằng cách bỏ khoảng trắng ở hai đầu và chuyển thành chữ hoa:

```java
import java.util.List;

List<Object> values = List.of(
    "  java  ",
    16,
    "  stream api ",
    false
);

List<String> normalized = values.stream()
    .<String>mapMulti((value, emit) -> {
        if (value instanceof String text) {
            String result = text.trim().toUpperCase();
            emit.accept(result);
        }
    })
    .toList();
```

Kết quả:

```text
[JAVA, STREAM API]
```

Biến `text` có kiểu `String`, vì vậy có thể gọi `trim()` và `toUpperCase()` trực tiếp. Biến `result` chứa giá trị sau chuyển đổi và được phát xuống pipeline.

Nếu phần tử không phải chuỗi, mapper không phát kết quả. Điều này cho phép vừa lọc theo kiểu vừa chuyển đổi dữ liệu trong cùng một bước `mapMulti`.

## 4. Kết hợp nhiều kiểu pattern trong một mapper

Một Stream hỗn hợp có thể chứa nhiều kiểu mà ứng dụng cần xử lý theo những quy tắc khác nhau. Ta có thể dùng chuỗi `if` và `else if` với các pattern variable tương ứng.

Ví dụ, chuỗi được chuẩn hóa, số nguyên được chuyển thành nhãn số lượng, còn số thực được định dạng thành nhãn tỷ lệ:

```java
import java.util.List;

List<Object> values = List.of(
    "Java",
    16,
    2.5,
    "Stream",
    true
);

List<String> descriptions = values.stream()
    .<String>mapMulti((value, emit) -> {
        if (value instanceof String text) {
            emit.accept("text: " + text.toUpperCase());
        } else if (value instanceof Integer number) {
            emit.accept("integer: " + number);
        } else if (value instanceof Double decimal) {
            emit.accept("decimal: " + decimal);
        }
    })
    .toList();
```

Kết quả:

```text
[
  text: JAVA,
  integer: 16,
  decimal: 2.5,
  text: STREAM
]
```

Phần tử `true` không khớp với các pattern đã khai báo nên không tạo đầu ra. Mỗi nhánh có một biến pattern với kiểu cụ thể, giúp trình biên dịch kiểm tra các lời gọi phương thức và phép chuyển đổi.

Thứ tự các nhánh cần phản ánh các kiểu muốn phân biệt. Nếu kiểm tra một kiểu cha trước kiểu con, nhánh kiểu cha có thể nhận luôn các đối tượng thuộc kiểu con và khiến nhánh sau không còn cơ hội chạy. Ví dụ, nếu muốn phân biệt `Integer` với các loại `Number` khác, hãy kiểm tra `Integer` trước `Number`.

## 5. Dùng điều kiện bổ sung cùng pattern variable

Pattern variable có thể được sử dụng trong phần còn lại của biểu thức điều kiện khi quy tắc flow scoping bảo đảm biến đã được khởi tạo.

Ví dụ, chỉ phát chuỗi không rỗng và không phải chuỗi trắng:

```java
import java.util.List;

List<Object> values = List.of(
    "Java",
    "",
    "   ",
    16,
    "Stream"
);

List<String> nonBlankTexts = values.stream()
    .<String>mapMulti((value, emit) -> {
        if (value instanceof String text && !text.isBlank()) {
            emit.accept(text.trim());
        }
    })
    .toList();
```

Kết quả:

```text
[Java, Stream]
```

Toán tử `&&` chỉ đánh giá vế phải khi vế trái đúng. Nếu `value` không phải `String`, biến `text` không được tạo và biểu thức `!text.isBlank()` không được đánh giá. Khi vế phải được đánh giá, `text` đã có sẵn và có thể được sử dụng an toàn.

Cách viết này kết hợp ba việc trong một nhánh:

1. Kiểm tra kiểu đối tượng.
2. Kiểm tra điều kiện trên giá trị đã khớp.
3. Phát kết quả nếu tất cả điều kiện đều đúng.

Không cần tạo biến trung gian kiểu `Object`, ép kiểu hoặc lồng thêm một `if` nếu điều kiện có thể diễn đạt rõ bằng `&&`.

## 6. Dùng phủ định và return để giảm lồng nhau

Java 16 hỗ trợ flow scoping cho pattern variable trong điều kiện phủ định. Khi nhánh không khớp kết thúc chắc chắn bằng `return`, biến pattern có thể được sử dụng ở phần còn lại của phương thức.

Ví dụ tách logic phát nhãn thành helper method:

```java
import java.util.List;
import java.util.function.Consumer;

class TextEmitter {
    static void emitText(Object value, Consumer<String> emit) {
        if (!(value instanceof String text)) {
            return;
        }

        if (!text.isBlank()) {
            emit.accept(text.trim());
        }
    }

    static List<String> collectTexts(List<Object> values) {
        return values.stream()
            .<String>mapMulti(TextEmitter::emitText)
            .toList();
    }
}
```

Nếu `value` không phải `String`, phương thức kết thúc tại `return`. Nếu chương trình đi tiếp qua câu lệnh `if`, điều đó có nghĩa `value` đã khớp với `String`, nên biến `text` hợp lệ trong phần còn lại.

Mẫu này được gọi là guard clause. Nó giúp đưa trường hợp không phù hợp ra khỏi phần xử lý chính và giảm mức độ lồng nhau.

## 7. Phạm vi của pattern variable

Pattern variable không có phạm vi giống một biến được khai báo ở đầu phương thức. Java dùng flow scoping: biến chỉ có thể được tham chiếu tại những vị trí mà trình biên dịch xác định chắc chắn pattern đã khớp.

Một số quy tắc thực tế:

- Trong thân `if (value instanceof String text)`, biến `text` có thể được sử dụng.
- Trong biểu thức `value instanceof String text && condition(text)`, biến có thể được sử dụng ở vế phải của `&&`.
- Với `if (!(value instanceof String text)) return;`, biến có thể được sử dụng sau câu lệnh `if`, vì đường đi tiếp tục chỉ xảy ra khi pattern đã khớp.
- Không thể dùng biến pattern ở vị trí mà điều kiện có thể chưa khớp.

Đặc biệt, không nên viết điều kiện dùng pattern variable ở vế phải của `||` theo cách giả định biến luôn tồn tại:

```java
// Không hợp lệ: khi vế trái false, text chưa được tạo.
if (value instanceof String text || text.isBlank()) {
    // ...
}
```

Với `||`, vế phải có thể được đánh giá khi vế trái sai. Khi đó pattern không khớp và biến `text` không sẵn sàng để sử dụng. Hãy dùng `&&` khi điều kiện tiếp theo chỉ có ý nghĩa sau khi pattern đã khớp.

## 8. Khi nào nên dùng filter kết hợp map?

Nếu mục tiêu chỉ là giữ các phần tử thuộc một kiểu và không có logic phát kết quả bổ sung, `filter` kết hợp `map` cũng là cách viết rõ ràng:

```java
import java.util.List;

List<Object> values = List.of("Java", 16, "Stream");

List<String> texts = values.stream()
    .filter(String.class::isInstance)
    .map(String.class::cast)
    .toList();
```

Ở đây:

- `filter(String.class::isInstance)` giữ các phần tử là chuỗi.
- `map(String.class::cast)` chuyển kiểu phần tử của Stream thành `String`.

Cách này phù hợp khi chỉ cần lọc một kiểu duy nhất. Tuy nhiên, pattern variable được khai báo bên trong lambda của `filter` không tự tồn tại trong lambda của thao tác `map` tiếp theo. Mỗi lambda là một phạm vi riêng.

Với `mapMulti`, kiểm tra kiểu, sử dụng biến pattern và phát kết quả được đặt trong cùng mapper. Điều này hữu ích khi có nhiều nhánh kiểu, cần chuyển đổi theo từng kiểu hoặc một phần tử có thể tạo ra nhiều kết quả.

| Nhu cầu | Cách viết thường phù hợp |
|---|---|
| Chỉ giữ phần tử thuộc một kiểu | `filter` + `map` |
| Lọc kiểu và xử lý nhiều nhánh trong cùng callback | `mapMulti` + pattern matching |
| Một phần tử khớp có thể phát nhiều giá trị | `mapMulti` |
| Phép biến đổi tự nhiên tạo một Stream con | `flatMap` |

Hãy chọn thao tác diễn đạt rõ nhất ý định. Không cần dùng `mapMulti` chỉ để thay thế một phép lọc đơn giản.

## 9. Một kiểu khớp có thể phát nhiều kết quả

Pattern matching chỉ xác định kiểu và cung cấp biến tham chiếu đến đối tượng. Sau đó mapper quyết định phát bao nhiêu kết quả.

Ví dụ, một chuỗi có thể phát cả giá trị gốc đã chuẩn hóa và phiên bản chữ hoa:

```java
import java.util.List;

List<Object> values = List.of(
    "Java",
    16,
    "Stream"
);

List<String> variants = values.stream()
    .<String>mapMulti((value, emit) -> {
        if (value instanceof String text) {
            String normalized = text.trim();

            if (!normalized.isEmpty()) {
                emit.accept(normalized);
                emit.accept(normalized.toUpperCase());
            }
        }
    })
    .toList();
```

Kết quả:

```text
[Java, JAVA, Stream, STREAM]
```

Mỗi chuỗi hợp lệ phát hai kết quả. Số nguyên không khớp với pattern nên không phát gì. Đây là điểm kết hợp quan trọng: `instanceof` quyết định cách xử lý dựa trên kiểu; `mapMulti` quyết định số lượng và nội dung đầu ra.

## 10. Xử lý null và kiểu dữ liệu không khớp

Biểu thức `null instanceof String text` luôn cho kết quả `false`. Vì vậy, pattern variable không được tạo và thân nhánh không chạy. Không cần kiểm tra null riêng chỉ để bảo vệ phép kiểm tra `instanceof`.

Ví dụ:

```java
import java.util.Arrays;
import java.util.List;

List<Object> values = Arrays.asList(
    "Java",
    null,
    16,
    "Stream"
);

List<String> texts = values.stream()
    .<String>mapMulti((value, emit) -> {
        if (value instanceof String text) {
            emit.accept(text);
        }
    })
    .toList();
```

Dùng `Arrays.asList` trong ví dụ này vì nó cho phép phần tử null; `List.of` không chấp nhận null.

Pattern matching kiểm tra kiểu, không tự kiểm tra nội dung nghiệp vụ. Một chuỗi rỗng vẫn khớp với `String`; nếu không muốn nhận chuỗi rỗng, hãy thêm điều kiện `!text.isBlank()` hoặc điều kiện phù hợp với yêu cầu.

## 11. Giới hạn cú pháp cần nhớ trong Java 16

Trong Java 16, pattern matching cho `instanceof` đã là tính năng chính thức. Cú pháp type pattern có dạng:

```java
if (value instanceof String text) {
    // dùng text như một String
}
```

Java 16 chưa có record patterns để phân rã thành phần của record ngay trong `instanceof`. Vì vậy, với record, hãy kiểm tra kiểu trước rồi gọi accessor trên biến pattern:

```java
record User(String name, int age) {}

class UserExample {
    static void inspect(Object value) {
        if (value instanceof User user) {
            String name = user.name();
            int age = user.age();
        }
    }
}
```

Cách này dùng record và pattern matching `instanceof` đã ổn định trong Java 16. Khi mã cần tương thích với Java 16, hãy lấy thành phần record qua accessor như `user.name()` và `user.age()`; cú pháp record pattern thuộc các phiên bản Java mới hơn.

## 12. Đặc tính Stream và lưu ý khi sử dụng

`mapMulti` là thao tác trung gian, nên mapper chỉ chạy khi terminal operation tiêu thụ pipeline, chẳng hạn `toList()`, `count()` hoặc `findFirst()`. Việc đặt pattern matching bên trong mapper không làm thay đổi đặc tính lazy này.

Khi Stream chạy song song, mapper của các phần tử nguồn khác nhau có thể được gọi đồng thời. Hãy giữ logic kiểm tra kiểu và tạo kết quả độc lập theo từng phần tử; tránh cập nhật collection mutable dùng chung hoặc dựa vào thứ tự thực thi của các mapper.

Pattern variable chỉ là biến tham chiếu cục bộ cho giá trị đã khớp. Không lưu nó vào trạng thái dùng chung để điều khiển các lần xử lý khác. Hãy phát dữ liệu qua Consumer và để các thao tác Stream phía sau chịu trách nhiệm xử lý hoặc thu thập kết quả.

## 13. Lỗi thường gặp

**Kiểm tra instanceof rồi vẫn ép kiểu thủ công.** Khi dùng `value instanceof String text`, biến `text` đã có kiểu `String`. Không cần viết thêm `(String) value`.

**Dùng pattern variable ngoài phạm vi hợp lệ.** Biến pattern chỉ dùng được ở nơi Java xác định chắc chắn pattern đã khớp. Hãy đặt logic trong thân `if`, vế phải của `&&`, hoặc sau guard clause kết thúc bằng `return`.

**Dùng `||` thay cho `&&` khi cần biến pattern ở vế phải.** Vế phải của `||` có thể chạy khi pattern chưa khớp. Hãy dùng `&&` cho điều kiện bổ sung phụ thuộc vào biến pattern.

**Quên chỉ định kiểu đầu ra.** Với Stream nguồn là `Stream<Object>` và kết quả mong muốn là chuỗi, `.<String>mapMulti` làm rõ kiểu `R` và kiểu Consumer.

**Dùng mapMulti cho phép lọc đơn giản.** Nếu chỉ cần giữ một kiểu và không có logic phát bổ sung, `filter` kết hợp `map` có thể ngắn gọn hơn.

**Cho rằng instanceof kiểm tra luôn nội dung hợp lệ.** Một chuỗi rỗng vẫn là `String`. Hãy thêm điều kiện nghiệp vụ sau khi pattern khớp.

**Dùng cú pháp của phiên bản Java mới hơn.** Với Java 16, dùng type pattern như `instanceof User user`; record patterns không thuộc cú pháp Java 16.

## 14. Ghi nhớ

- Pattern matching cho `instanceof` được hoàn thiện trong Java 16.
- Cú pháp `value instanceof String text` vừa kiểm tra kiểu vừa khai báo biến pattern.
- Trong `mapMulti`, phần tử không khớp có thể không phát kết quả; phần tử khớp có thể phát một hoặc nhiều giá trị.
- Pattern variable có phạm vi theo luồng điều khiển, không phải toàn bộ phương thức.
- Dùng `&&` để kiểm tra thêm điều kiện trên biến pattern; dùng guard clause với `return` để giảm lồng nhau.
- Dùng `filter` + `map` khi chỉ lọc một kiểu đơn giản; dùng `mapMulti` khi cần nhiều nhánh hoặc nhiều kết quả.
- Kiểm tra kiểu không đồng nghĩa với kiểm tra dữ liệu hợp lệ; hãy bổ sung điều kiện nghiệp vụ.
- Với mã Java 16, dùng type patterns cho `instanceof`; không dùng record patterns từ phiên bản mới hơn.

Kết hợp pattern matching với `mapMulti` giúp xử lý Stream chứa nhiều kiểu dữ liệu một cách an toàn về kiểu và dễ đọc. Biến pattern cung cấp đối tượng đã khớp, còn Consumer của `mapMulti` cho phép phát chính xác những kết quả mà pipeline cần.

