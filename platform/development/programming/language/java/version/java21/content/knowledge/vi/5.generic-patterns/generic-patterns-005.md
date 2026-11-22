# Giới hạn type erasure và matching đòi hỏi unchecked conversion

Trong Java 21, pattern matching có thể kiểm tra kiểu và ràng buộc biến ngay trong `instanceof` hoặc nhãn `case` của `switch`. Tuy nhiên, generics được triển khai bằng **type erasure**: thông tin tham số kiểu như `String` hoặc `Integer` không được giữ lại đầy đủ để JVM kiểm tra ở runtime. Vì vậy, không phải mọi kiểu generic đều có thể dùng trực tiếp làm kiểu đích của pattern.

Quy tắc thực hành là: pattern phải có thể được kiểm tra an toàn dựa trên kiểu tĩnh của biểu thức và thông tin runtime còn tồn tại. Nếu muốn khớp một kiểu tham số hóa mà việc kiểm tra sẽ cần unchecked narrowing conversion, trình biên dịch từ chối pattern đó. Ta thường dùng wildcard pattern để xác định kiểu tổng quát, rồi kiểm tra từng phần tử trước khi xử lý như kiểu cụ thể.

Các quy tắc này áp dụng cho Java 21 hiện hành; ví dụ trong bài không cần bật preview.

## 1. Vì sao type erasure giới hạn generic pattern?

Xét hai biến:

```java
List<String> names = new ArrayList<>();
List<Integer> scores = new ArrayList<>();
```

Ở mức kiểu nguồn, `List<String>` và `List<Integer>` khác nhau. Nhưng sau khi biên dịch, cả hai đều dùng cùng kiểu runtime `List`. JVM không thể hỏi một đối tượng bất kỳ rằng nó được tạo từ `List<String>` hay `List<Integer>` chỉ bằng cách kiểm tra lớp của đối tượng.

Ví dụ sau không hợp lệ:

```java
static void inspect(Object value) {
    // LỖI BIÊN DỊCH: không thể kiểm tra tham số kiểu String ở runtime.
    if (value instanceof List<String> strings) {
        System.out.println(strings.size());
    }
}
```

`instanceof` có thể kiểm tra đối tượng có phải một `List` hay không, nhưng không thể xác nhận tất cả phần tử của danh sách đều là `String`. Việc chấp nhận pattern này sẽ tạo cảm giác an toàn giả: một danh sách chứa `Integer` vẫn vượt qua kiểm tra lớp `List`, rồi có thể gây `ClassCastException` khi chương trình đọc phần tử và dùng nó như `String`.

Type erasure không có nghĩa là trình biên dịch quên mọi tham số kiểu. Trình biên dịch vẫn dùng chúng để kiểm tra tương thích, suy luận kiểu và ngăn nhiều lỗi ngay lúc biên dịch. Giới hạn nằm ở khả năng kiểm tra trực tiếp tham số kiểu của một đối tượng đã tồn tại tại runtime.

## 2. Reifiable type và kiểu không thể kiểm tra đầy đủ ở runtime

Một kiểu *reifiable* là kiểu mà thông tin cần thiết để kiểm tra kiểu vẫn có thể biểu diễn đầy đủ ở runtime. Một số dạng thường gặp:

| Kiểu | Reifiable? | Có thể kiểm tra từ `Object` bằng pattern? |
|---|---|---|
| `String` | Có | Có |
| `List<?>` | Có | Có |
| `Map<?, ?>` | Có | Có |
| `List<String>` | Không | Không, cần kiểm tra tham số kiểu đã bị xóa |
| `List<? extends Number>` | Không | Không, wildcard có giới hạn không làm kiểu trở thành reifiable |
| `List` (raw type) | Có | Có về mặt cú pháp, nhưng mất an toàn kiểu và không nên dùng trong mã mới |

Wildcard không giới hạn `?` nói rằng chương trình chấp nhận một danh sách có kiểu phần tử chưa biết. JVM chỉ cần kiểm tra đối tượng có phải `List`; không cần xác định kiểu phần tử. Vì vậy, `List<?>` là lựa chọn phù hợp để nhận diện một danh sách bất kỳ một cách an toàn.

```java
static void inspect(Object value) {
    if (value instanceof List<?> elements) {
        System.out.println("Số phần tử: " + elements.size());

        for (Object element : elements) {
            System.out.println(element);
        }
    }
}
```

Trong thân `if`, `elements` có kiểu `List<?>`. Khi đọc một phần tử, kiểu an toàn chung nhất là `Object`, vì kiểu thực tế của phần tử chưa được biết. Ta không thể thêm một `String` tùy ý vào `List<?>`, bởi danh sách thực tế có thể là `List<Integer>` hoặc một kiểu khác.

## 3. Pattern được phép khi kiểu tĩnh chứng minh phép thu hẹp an toàn

Không phải mọi pattern có tham số kiểu đều bị cấm. Java cho phép pattern với kiểu tham số hóa không reifiable nếu kiểu tĩnh của biểu thức đủ thông tin để phép thu hẹp không cần unchecked conversion.

Ví dụ:

```java
static void inspect(Collection<String> source) {
    if (source instanceof ArrayList<String> names) {
        // names có kiểu ArrayList<String>.
        // Có thể dùng các phần tử như String theo kiểu tĩnh đã biết.
        for (String name : names) {
            System.out.println(name.toUpperCase());
        }
    }
}
```

Biểu thức `source` đã có kiểu tĩnh `Collection<String>`. Nếu nó là một `ArrayList`, tham số kiểu `String` của kiểu đích tương thích với thông tin generic đã có ở kiểu nguồn. Runtime vẫn kiểm tra lớp thực tế là `ArrayList`; tính đúng đắn của tham số kiểu dựa trên hệ thống kiểu của Java và giả định mã không tạo heap pollution.

Ngược lại, với `Collection<?>`, trình biên dịch không biết phần tử là `String`:

```java
static void inspect(Collection<?> source) {
    // LỖI BIÊN DỊCH: cần unchecked narrowing conversion.
    if (source instanceof ArrayList<String> names) {
        System.out.println(names.get(0).toUpperCase());
    }
}
```

Kiểu nguồn chỉ cam kết rằng đây là một `Collection` có phần tử chưa biết. Chuyển sang `ArrayList<String>` sẽ giả định thêm rằng phần tử là `String`, điều mà runtime không thể xác minh và kiểu tĩnh không chứng minh được.

Có thể ghi nhớ hai trường hợp:

- `Collection<String>` sang `ArrayList<String>`: có thể kiểm tra an toàn nếu phép thu hẹp lớp phù hợp.
- `Collection<?>` sang `ArrayList<String>`: cần giả định về tham số kiểu, nên pattern bị từ chối.

Một pattern còn phải thỏa các quy tắc tương thích kiểu khác của Java. Việc không cần unchecked conversion là điều kiện cần, không có nghĩa mọi kiểu nguồn và kiểu pattern đều tương thích.

## 4. Dùng wildcard pattern để kiểm tra an toàn

Khi đầu vào có kiểu `Object` hoặc một kiểu generic chưa biết, hãy kiểm tra phần cấu trúc có thể kiểm tra được trước:

```java
static void inspect(Object value) {
    if (value instanceof List<?> elements) {
        for (Object element : elements) {
            if (element instanceof String text) {
                System.out.println("Tên: " + text.toUpperCase());
            } else {
                System.out.println("Phần tử không phải String: " + element);
            }
        }
    } else {
        System.out.println("Giá trị không phải List");
    }
}
```

Ở đây, Java thực hiện hai kiểm tra độc lập:

1. `value instanceof List<?> elements` kiểm tra đối tượng là một danh sách.
2. `element instanceof String text` kiểm tra từng phần tử có phải `String` hay không.

Kiểm tra phần tử có thể thực hiện vì mỗi phần tử được lấy ra dưới dạng `Object`, và `String` là kiểu có thể kiểm tra trực tiếp ở runtime. Không cần ép toàn bộ danh sách thành `List<String>`.

### Tạo một `List<String>` mới sau khi xác thực

Nếu phương thức cần trả về danh sách có kiểu phần tử chắc chắn là `String`, hãy kiểm tra từng phần tử và tạo danh sách kết quả:

```java
static List<String> copyStrings(Object value) {
    if (!(value instanceof List<?> elements)) {
        throw new IllegalArgumentException("Expected a List");
    }

    List<String> result = new ArrayList<>(elements.size());

    for (Object element : elements) {
        if (!(element instanceof String text)) {
            throw new IllegalArgumentException("Every element must be a String");
        }

        result.add(text);
    }

    return List.copyOf(result);
}
```

Phương thức này chấp nhận một `List` bất kỳ, nhưng chỉ trả về khi mọi phần tử đều là `String`. Phần tử `null` cũng bị từ chối vì `null instanceof String` trả về `false`; `List.copyOf` cũng không chấp nhận phần tử null. Nếu nghiệp vụ cho phép null, cần định nghĩa rõ cách giữ hoặc xử lý null và chọn cách tạo danh sách phù hợp.

Danh sách kết quả là một bản sao. Điều này tạo ranh giới rõ ràng giữa dữ liệu đầu vào chưa được xác thực và dữ liệu đầu ra đã có kiểu `List<String>`.

## 5. Generic record pattern cũng chịu giới hạn tương tự

Record pattern phân rã component của record, nhưng không loại bỏ giới hạn type erasure của kiểu record tổng thể.

```java
interface Payload<T> {}
record Box<T>(T value) implements Payload<T> {}

static void inspect(Payload<String> payload) {
    if (payload instanceof Box<String>(var text)) {
        System.out.println(text.toUpperCase());
    }
}
```

Trong ví dụ này, kiểu tĩnh `Payload<String>` cung cấp thông tin tham số kiểu. Pattern thu hẹp sang `Box<String>` và phân rã component `value`. Phép thu hẹp lớp có thể được kiểm tra mà không cần giả định một tham số kiểu chưa được biết.

Nếu đầu vào chỉ có kiểu `Object`, không thể dùng pattern `Box<String>` để xác minh tham số `String`:

```java
static void inspect(Object value) {
    // LỖI BIÊN DỊCH: runtime không thể xác minh tham số kiểu String.
    if (value instanceof Box<String>(var text)) {
        System.out.println(text.toUpperCase());
    }
}
```

Với đầu vào không rõ tham số kiểu, dùng wildcard:

```java
static void inspect(Object value) {
    if (value instanceof Box<?>(var item)) {
        // item có kiểu chưa xác định phù hợp với Box<?>.
        System.out.println(item);
    }
}
```

Nếu cần xác nhận component là `String`, kiểm tra component sau khi phân rã:

```java
static void inspectTextBox(Object value) {
    if (value instanceof Box<?>(var item)
            && item instanceof String text) {
        System.out.println(text.toUpperCase());
    }
}
```

Đây là cách phân biệt giữa hai câu hỏi: đối tượng có phải một `Box` không, và giá trị bên trong có phải `String` không. Câu hỏi thứ hai được trả lời bằng kiểm tra component có thể xác minh ở runtime.

## 6. Quy tắc tương tự áp dụng cho pattern trong `switch`

Pattern matching trong `switch` của Java 21 cũng phải tuân theo giới hạn generic. Ví dụ sau dùng wildcard nên có thể kiểm tra an toàn:

```java
static String describe(Object value) {
    return switch (value) {
        case List<?> elements -> "List có " + elements.size() + " phần tử";
        case String text -> "String: " + text;
        case null -> "null";
        default -> "Kiểu khác";
    };
}
```

Không thể đổi `List<?>` thành `List<String>` trong ví dụ trên để yêu cầu `switch` phân biệt danh sách chứa chuỗi. Selector có kiểu `Object` và runtime chỉ giữ được lớp `List`, không giữ tham số kiểu `String`.

Nếu selector đã có kiểu generic cụ thể, một pattern thu hẹp an toàn có thể sử dụng thông tin đó, tương tự ví dụ `Collection<String>` ở phần trước. Các quy tắc về khả năng tương thích kiểu, dominance và exhaustiveness của `switch` vẫn được áp dụng riêng.

## 7. Unchecked conversion, unchecked cast và raw type

Các khái niệm liên quan nhưng không nên đánh đồng:

| Khái niệm | Ý nghĩa |
|---|---|
| Type erasure | Cách triển khai generics loại bỏ phần lớn thông tin tham số kiểu khỏi kiểu runtime |
| Reifiable type | Kiểu có thể được biểu diễn và kiểm tra đầy đủ ở runtime |
| Unchecked conversion | Chuyển đổi mà trình biên dịch không thể xác minh đầy đủ tính an toàn kiểu, thường gặp khi chuyển từ raw type sang kiểu tham số hóa |
| Unchecked cast / unchecked narrowing conversion | Phép ép kiểu thu hẹp sang kiểu tham số hóa mà runtime không thể kiểm tra đầy đủ các tham số kiểu |
| Raw type | Dùng tên generic mà bỏ các tham số kiểu, ví dụ `List` thay cho `List<String>` |

Pattern matching không phải cách để hợp thức hóa một phép ép kiểu unchecked. Nếu một pattern cần giả định rằng `Object` thực ra là `List<String>`, trình biên dịch không thể xác nhận giả định đó và sẽ từ chối.

Tránh dùng raw type để né lỗi:

```java
List raw = new ArrayList();
raw.add(42);

// Kiểu raw bỏ qua kiểm tra tham số kiểu ở compile time.
```

Raw type vẫn tồn tại chủ yếu vì tương thích với mã Java cũ. Khi viết mã mới, hãy dùng `List<?>` nếu chưa biết kiểu phần tử, hoặc `List<String>` khi kiểu phần tử đã được xác định. Dùng raw type có thể tạo heap pollution và làm lỗi chỉ xuất hiện khi đọc phần tử.

## 8. Vì sao không nên ép kiểu unchecked sau khi pattern khớp?

Một cách viết nguy hiểm là kiểm tra `List<?>` rồi ép kiểu trực tiếp:

```java
if (value instanceof List<?> elements) {
    @SuppressWarnings("unchecked")
    List<String> names = (List<String>) elements;

    System.out.println(names.get(0).toUpperCase());
}
```

Pattern chỉ chứng minh `value` là một `List`. Nó không chứng minh phần tử là `String`. Annotation `@SuppressWarnings("unchecked")` chỉ ẩn cảnh báo của compiler, không thêm kiểm tra runtime và không làm phép ép kiểu trở nên an toàn. Nếu danh sách chứa số nguyên, lỗi có thể xuất hiện khi đọc phần tử như `String`.

Chỉ cân nhắc một phép ép kiểu unchecked khi có một bảo đảm bên ngoài đáng tin cậy mà compiler không thể biểu diễn, chẳng hạn một API nội bộ có hợp đồng kiểu rõ ràng. Khi đó cần giới hạn phạm vi ép kiểu, ghi rõ cơ sở của bảo đảm và giữ kiểm thử phù hợp. Với dữ liệu đầu vào không tin cậy, hãy xác thực từng phần tử như ví dụ ở phần 4.

## 9. Cách đọc lỗi biên dịch

| Thông báo hoặc tình huống | Nguyên nhân | Hướng xử lý |
|---|---|---|
| `Object cannot be safely cast to List<String>` | Kiểu đích không reifiable và kiểu nguồn không chứng minh được tham số `String` | Dùng `List<?>`, sau đó kiểm tra từng phần tử |
| Pattern `ArrayList<String>` không hợp lệ với `Collection<?>` | Phép thu hẹp cần unchecked narrowing conversion | Giữ wildcard hoặc xác thực phần tử trước khi tạo danh sách có kiểu cụ thể |
| Không thể gọi phương thức riêng của `String` trên phần tử | Phần tử của `List<?>` chỉ được biết là `Object` hoặc kiểu capture chưa xác định | Dùng `instanceof String text` trước khi gọi phương thức của `String` |
| Có cảnh báo unchecked khi ép kiểu sau pattern | Pattern chỉ xác nhận kiểu container, không xác nhận tham số kiểu | Tránh ép kiểu trực tiếp; sao chép và xác thực từng phần tử |
| Mã biên dịch được nhưng phát sinh `ClassCastException` khi đọc phần tử | Dữ liệu đã bị heap pollution hoặc có phép ép kiểu unchecked không an toàn | Truy tìm raw type, unchecked cast và ranh giới dữ liệu đã bỏ qua kiểm tra |

Khi gặp lỗi, hãy tự hỏi hai điều: JVM có thể kiểm tra lớp đích ở runtime không, và kiểu tĩnh của biểu thức có đủ thông tin để chứng minh tham số generic không? Nếu câu trả lời thứ hai là không và pattern cần một tham số cụ thể, hãy đổi sang wildcard pattern và kiểm tra dữ liệu thành phần.

## 10. Checklist khi viết generic pattern

- Xác định kiểu tĩnh của biểu thức trước khi chọn kiểu pattern.
- Dùng kiểu reifiable như `List<?>` khi cần kiểm tra một generic object từ `Object`.
- Chỉ dùng pattern tham số hóa cụ thể khi phép thu hẹp được chứng minh an toàn từ kiểu tĩnh và không cần unchecked conversion.
- Không kỳ vọng `instanceof` hoặc `switch` phân biệt `List<String>` với `List<Integer>` ở runtime.
- Với dữ liệu generic chưa rõ kiểu, đọc phần tử dưới dạng `Object` và xác thực bằng pattern cụ thể như `instanceof String text`.
- Tạo bản sao có kiểu cụ thể sau khi xác thực nếu API cần trả về `List<String>`.
- Tránh raw type và unchecked cast; không xem `@SuppressWarnings` là biện pháp kiểm tra dữ liệu.
- Với generic record, phân biệt việc kiểm tra lớp record và kiểm tra kiểu của component.

Type erasure giới hạn những gì pattern có thể xác nhận ở runtime. Java 21 vẫn cho phép pattern với kiểu generic cụ thể khi kiểu tĩnh chứng minh phép thu hẹp an toàn; khi thông tin tham số kiểu không đủ, wildcard pattern kết hợp kiểm tra từng component là cách xử lý rõ ràng và an toàn.
