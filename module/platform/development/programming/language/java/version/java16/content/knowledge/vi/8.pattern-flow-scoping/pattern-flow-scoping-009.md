# Đặt tên, khai báo lại và tránh che khuất pattern variable

Pattern matching cho `instanceof` được hoàn thiện trong Java 16. Cú pháp như `value instanceof String text` kiểm tra kiểu runtime và khai báo biến pattern `text` ngay trong biểu thức. Biến này là biến cục bộ; tên của nó tuân theo các quy tắc phạm vi và khai báo biến cục bộ của Java.

Điểm dễ gây nhầm lẫn là phạm vi của pattern variable được xác định theo luồng điều khiển. Nó có thể chỉ tồn tại trong thân `if`, có thể dùng ở vế phải của `&&`, hoặc có thể tiếp tục nằm trong phạm vi sau `if` nếu nhánh không khớp kết thúc bằng `return` hay `throw`. Vì vậy, một tên tưởng như đã hết phạm vi ở cuối dấu ngoặc nhọn đôi khi vẫn còn được sử dụng ở phần tiếp theo của phương thức.

Trong module Java 16, pattern matching cho `instanceof` là cải tiến ngôn ngữ vẫn hữu ích bên cạnh `record` và các API Stream. Bài này tập trung vào cách đặt tên có ý nghĩa, trường hợp khai báo trùng tên bị compiler từ chối, tái sử dụng tên trong các phạm vi tách biệt và tránh che khuất field. Các ví dụ dùng cú pháp đã được chuẩn hóa, tiếp tục áp dụng trong Java hiện đại.

## 1. Pattern variable là biến cục bộ

Trong ví dụ sau, `text` là tên biến pattern và có kiểu tĩnh `String` sau khi phép kiểm tra khớp:

```java
static void printValue(Object value) {
    if (value instanceof String text) {
        System.out.println(text.strip());
    }
}
```

Vì là biến cục bộ, pattern variable phải tuân theo các quy tắc đặt tên và phạm vi của biến cục bộ:

- Không thể khai báo một biến cục bộ khác cùng tên trong một phạm vi đang nhìn thấy pattern variable.
- Không thể dùng lại tên tham số phương thức làm tên pattern variable trong cùng phương thức.
- Có thể dùng cùng một tên ở các phạm vi tách biệt, không chồng lấn.
- Pattern variable có thể che khuất một field cùng tên; khi cần truy cập field, dùng `this.fieldName`.

Compiler xét phạm vi thực tế của pattern variable theo flow scoping, nên cần đọc cả điều kiện và các nhánh điều khiển trước khi quyết định một tên đã được dùng hay chưa.

## 2. Chọn tên theo ý nghĩa dữ liệu

Tên biến pattern nên mô tả vai trò của giá trị sau khi kiểm tra kiểu. Điều này giúp người đọc hiểu dữ liệu đang được xử lý mà không phải suy luận từ kiểu Java.

```java
if (value instanceof String command) {
    System.out.println(command.strip());
}

if (value instanceof CharSequence sequence) {
    System.out.println(sequence.length());
}

if (value instanceof Integer retryCount) {
    System.out.println(retryCount + 1);
}
```

Một số gợi ý:

- Dùng `command`, `userName`, `message` hoặc `path` khi giá trị có ý nghĩa nghiệp vụ cụ thể.
- Dùng tên phản ánh abstraction khi kiểm tra interface, ví dụ `sequence` cho `CharSequence`.
- Tránh các tên quá chung như `x`, `obj`, `s` khi có nhiều điều kiện hoặc nhiều pattern trong cùng phương thức.
- Không lặp lại tên kiểu một cách dư thừa như `stringValue` nếu một tên miền nghiệp vụ rõ ràng hơn.

Ví dụ, `value instanceof String command` dễ hiểu hơn `value instanceof String s` khi giá trị đại diện cho lệnh cần xử lý.

## 3. Không khai báo lại tên trong phạm vi đang chồng lấn

Khi pattern variable đang nằm trong phạm vi, không thể khai báo một biến cục bộ khác cùng tên trong khối lồng bên trong:

```java
static void normalize(Object value) {
    if (value instanceof String text) {
        String text = text.strip(); // Lỗi biên dịch: tên text đã được khai báo.
        System.out.println(text);
    }
}
```

Lý do là `text` đã là biến cục bộ trong phạm vi của thân `if`. Khai báo `String text` thứ hai sẽ tạo ra hai biến cục bộ cùng tên trong các phạm vi chồng lấn. Java không cho phép cách khai báo này.

Hãy đặt tên khác cho kết quả đã xử lý:

```java
static void normalize(Object value) {
    if (value instanceof String text) {
        String normalized = text.strip();
        System.out.println(normalized);
    }
}
```

Tên `normalized` cũng làm rõ rằng đây là giá trị đã được chuẩn hóa từ `text`, không phải một biến đại diện cho đối tượng đầu vào ban đầu.

## 4. Không dùng lại tên tham số phương thức

Pattern variable không thể trùng tên với tham số đã được khai báo trong cùng phương thức:

```java
static void print(Object text) {
    if (text instanceof String text) { // Lỗi biên dịch: trùng tên tham số.
        System.out.println(text.strip());
    }
}
```

Tham số `text` đã nằm trong phạm vi phương thức. Hãy đặt tên pattern variable theo vai trò cụ thể hoặc đổi tên tham số:

```java
static void print(Object value) {
    if (value instanceof String text) {
        System.out.println(text.strip());
    }
}
```

Cách đặt tên `value` cho đầu vào chưa được xác nhận và `text` cho giá trị đã khớp kiểu giúp thể hiện rõ trạng thái của dữ liệu.

## 5. Phạm vi flow scoping có thể kéo dài sau `if`

Một trường hợp dễ bị bỏ sót là guard clause. Pattern variable có thể tiếp tục nằm trong phạm vi sau `if` nếu nhánh pattern chưa khớp kết thúc bằng `return` hoặc `throw`:

```java
static String normalize(Object value) {
    if (!(value instanceof String text)) {
        return "(empty)";
    }

    // text vẫn nằm trong phạm vi sau if.
    return text.strip();
}
```

Trong đoạn mã này, nếu pattern không khớp, phương thức kết thúc bằng `return`. Nếu luồng thực thi đi đến câu lệnh cuối, pattern chắc chắn đã khớp và `text` vẫn nằm trong phạm vi.

Do đó, khai báo lại tên `text` sau guard cũng không hợp lệ:

```java
static String normalize(Object value) {
    if (!(value instanceof String text)) {
        return "(empty)";
    }

    String text = "default"; // Lỗi biên dịch: text vẫn trong phạm vi.
    return text;
}
```

Hãy dùng tên khác như `normalized`, `fallback` hoặc `displayText`, tùy ý nghĩa thực tế:

```java
static String normalize(Object value) {
    if (!(value instanceof String text)) {
        return "(empty)";
    }

    String normalized = text.strip();
    return normalized;
}
```

Không nên xác định phạm vi chỉ bằng cách nhìn dấu ngoặc nhọn. Hãy xem nhánh nào có thể đi tiếp và điều kiện nào đã chứng minh pattern khớp.

## 6. Có thể tái sử dụng tên ở các phạm vi tách biệt

Khi hai pattern variable có các phạm vi không chồng lấn, Java cho phép dùng lại cùng tên. Ví dụ, hai câu lệnh `if` độc lập có thể khai báo cùng tên trong từng thân riêng:

```java
static void describe(Object value) {
    if (value instanceof String candidate) {
        System.out.println("Chuỗi: " + candidate.strip());
    }

    if (value instanceof Integer candidate) {
        System.out.println("Số nguyên: " + candidate);
    }
}
```

`candidate` trong thân `if` thứ nhất và `candidate` trong thân `if` thứ hai thuộc hai phạm vi tách biệt. Pattern variable thứ nhất không còn trong phạm vi khi đến thân `if` thứ hai, nên không có khai báo trùng trong vùng chồng lấn.

Tuy vậy, nếu hai kiểu đại diện cho vai trò khác nhau, tên riêng như `text` và `number` có thể giúp mã dễ đọc hơn. Tái sử dụng tên là hợp lệ khi phạm vi tách biệt, nhưng không phải lúc nào cũng là lựa chọn dễ hiểu nhất.

## 7. Phân biệt khai báo trùng tên với che khuất field

Java không cho phép khai báo lại một biến cục bộ trong phạm vi cục bộ đang chồng lấn. Tuy nhiên, biến cục bộ có thể che khuất (*shadow*) field cùng tên:

```java
class UserProfile {
    private final String name = "Tên lưu trong hồ sơ";

    void print(Object value) {
        if (value instanceof String name) {
            System.out.println(name);      // Pattern variable.
            System.out.println(this.name); // Field của đối tượng hiện tại.
        }
    }
}
```

Trong thân `if`, tên `name` tham chiếu đến pattern variable. Field `name` bị che khuất trong cách truy cập không định danh. Dùng `this.name` để truy cập field của đối tượng hiện tại.

Mặc dù hợp lệ, đặt tên pattern variable trùng với field thường khiến người đọc phải phân biệt hai nguồn dữ liệu. Có thể chọn tên cụ thể hơn:

```java
class UserProfile {
    private final String name = "Tên lưu trong hồ sơ";

    void print(Object value) {
        if (value instanceof String suppliedName) {
            System.out.println(suppliedName);
            System.out.println(this.name);
        }
    }
}
```

Tên `suppliedName` làm rõ chuỗi được truyền vào khác với tên được lưu trong hồ sơ.

## 8. Chú ý tên biến trong điều kiện kết hợp

Flow scoping cho phép sử dụng pattern variable ở vế phải của `&&` khi vế trái khớp:

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.strip());
}
```

Không khai báo một pattern variable khác cùng tên ở vế phải. Hãy dùng một tên khác nếu cần kiểm tra một đối tượng khác:

```java
if (value instanceof String text
        && anotherValue instanceof String description
        && !text.isBlank()
        && !description.isBlank()) {
    System.out.println(text + ": " + description);
}
```

Với `||`, pattern dương ở vế trái không được bảo đảm đã khớp khi vế phải được đánh giá. Trường hợp phủ định pattern có thể đảo quy tắc đó:

```java
if (!(value instanceof String text) || text.isBlank()) {
    return;
}

System.out.println(text.strip());
```

Ở đây, `text` có thể dùng trong vế phải vì vế phải chỉ chạy khi phép phủ định sai, tức pattern gốc đã khớp. Sau `if`, biến vẫn nằm trong phạm vi vì nhánh không hợp lệ kết thúc bằng `return`. Vì vậy, không thể khai báo lại `text` trong phần còn lại của phương thức.

## 9. Các lỗi đặt tên thường gặp và cách sửa

| Trường hợp | Vì sao có vấn đề | Cách sửa |
|---|---|---|
| Khai báo biến cục bộ cùng tên bên trong thân chứa pattern variable | Hai phạm vi chồng lấn | Đặt tên cho kết quả như `normalized`. |
| Pattern variable trùng tên tham số | Tham số đã nằm trong phạm vi phương thức | Dùng `value` cho đầu vào và tên theo kiểu/ý nghĩa cho pattern. |
| Khai báo lại tên sau guard clause | Flow scoping có thể kéo dài qua câu lệnh `if` | Dùng tên khác hoặc bỏ khai báo không cần thiết. |
| Pattern variable trùng tên field | Hợp lệ nhưng field bị che khuất | Dùng tên rõ nghĩa như `suppliedName` hoặc truy cập field bằng `this.name`. |
| Dùng tên quá chung cho nhiều pattern | Khó nhận biết giá trị nào đang được xử lý | Đặt tên theo vai trò như `command`, `sequence`, `retryCount`. |

## 10. Ví dụ hoàn chỉnh

```java
class PatternVariableNamingDemo {
    private final String name = "Tên hồ sơ";

    void describe(Object value, Object details) {
        if (value instanceof String suppliedName
                && !suppliedName.isBlank()) {
            String normalizedName = suppliedName.strip();
            System.out.println(normalizedName);
        }

        if (details instanceof String description) {
            System.out.println(description.strip());
        }

        if (value instanceof Integer retryCount) {
            System.out.println("Số lần thử: " + retryCount);
        }

        if (value instanceof String profileName) {
            System.out.println("Tên truyền vào: " + profileName);
            System.out.println("Tên hồ sơ: " + this.name);
        }
    }

    String requireText(Object value) {
        if (!(value instanceof String text)) {
            throw new IllegalArgumentException("value phải là String");
        }

        String normalized = text.strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("value không được để trống");
        }

        return normalized;
    }
}
```

Các tên như `suppliedName`, `description`, `retryCount`, `profileName` và `normalized` cho biết vai trò cụ thể của từng biến. Pattern variable có phạm vi riêng theo từng điều kiện; biến `text` trong phương thức `requireText` vẫn nằm trong phạm vi sau guard, nên kết quả xử lý được đặt tên là `normalized`.

## 11. Cách áp dụng trong mã Java hiện đại

- Đặt tên pattern variable theo vai trò của dữ liệu sau khi xác nhận kiểu.
- Xem pattern variable như biến cục bộ khi kiểm tra xung đột tên với tham số và biến cục bộ khác.
- Tính đến flow scoping khi dùng guard clause; tên có thể vẫn nằm trong phạm vi sau `if`.
- Chỉ tái sử dụng tên khi các phạm vi không chồng lấn và cách viết vẫn dễ đọc.
- Tránh che khuất field nếu nó làm người đọc khó phân biệt dữ liệu đầu vào và trạng thái đối tượng; dùng `this.fieldName` khi cần truy cập field.
- Đặt tên mới cho giá trị đã biến đổi thay vì khai báo lại tên pattern variable.

Đặt tên rõ ràng và hiểu đúng phạm vi giúp tránh lỗi khai báo trùng, giảm nhầm lẫn khi đọc điều kiện phức hợp và giữ mã Java dễ bảo trì. Những quy tắc này tiếp tục áp dụng cho pattern matching `instanceof` trong Java hiện đại.
