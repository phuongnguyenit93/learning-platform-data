# Type argument tường minh trong record pattern

Record pattern cho phép kiểm tra một giá trị có thuộc kiểu record hay không, đồng thời tách các thành phần của record thành những biến có kiểu cụ thể. Khi record khai báo generic, record pattern có thể ghi rõ type argument (tham số kiểu) hoặc để trình biên dịch suy luận từ ngữ cảnh.

Trong Java 21, record patterns là tính năng chính thức của ngôn ngữ. Việc ghi type argument tường minh giúp thể hiện rõ kiểu tham số mà pattern sử dụng và kiểu tĩnh của các thành phần được tách ra. Tuy nhiên, pattern vẫn phải tuân thủ quy tắc tương thích kiểu của Java: phép chuyển đổi từ kiểu của giá trị được kiểm tra sang kiểu record trong pattern không được yêu cầu unchecked conversion.

## 1. Record pattern với record generic

Xét một generic record:

```java
record Box<T>(T value) {}
```

Record `Box` có một type parameter là `T`. Khi khai báo biến:

```java
Box<String> box = new Box<>("Java 21");
```

thì `T` được thay bằng `String` trong kiểu tham chiếu của biến `box`. Vì vậy, thành phần `value` có kiểu tĩnh là `String` trong ngữ cảnh này.

Record pattern cơ bản có dạng:

```java
RecordType<TypeArguments>(componentPattern1, componentPattern2, ...)
```

Với record generic, phần `<TypeArguments>` có thể được ghi tường minh. Ví dụ:

```java
record Box<T>(T value) {}

static void printBoxContents(Box<String> box) {
    if (box instanceof Box<String>(String text)) {
        System.out.println("Box chứa: " + text);
    }
}
```

Trong pattern `Box<String>(String text)`:

- `Box<String>` chỉ rõ record pattern sử dụng kiểu tham số `String` cho `T`.
- `(String text)` là component pattern áp dụng lên thành phần `value`.
- Nếu pattern khớp, biến `text` có kiểu tĩnh là `String` và có thể dùng trực tiếp các method của `String`.

Record pattern gọi accessor tương ứng để lấy giá trị thành phần và áp dụng component pattern lên giá trị đó. Với record `Box<T>`, accessor của thành phần `value` là `value()`.

## 2. Ý nghĩa của type argument tường minh

Type argument được ghi trong record pattern xác định cách tham số hóa kiểu record tại thời điểm biên dịch. Nó ảnh hưởng đến kiểu tĩnh của các thành phần và những phép kiểm tra kiểu mà component pattern có thể thực hiện.

Ví dụ với record có hai tham số kiểu:

```java
record Pair<L, R>(L left, R right) {}

static void printPair(Pair<String, Integer> pair) {
    if (pair instanceof Pair<String, Integer>(
            String left, Integer right)) {
        System.out.println(left + " / " + right);
    }
}
```

Trong ví dụ này, type argument `String, Integer` tương ứng lần lượt với `L` và `R`. Các component pattern `String left` và `Integer right` kiểm tra từng giá trị thành phần và khai báo biến có kiểu cụ thể.

Thứ tự type argument phải khớp với thứ tự khai báo type parameter của record. Nếu khai báo là `Pair<L, R>`, thì `Pair<String, Integer>` có nghĩa là `L = String` và `R = Integer`.

Có thể dùng kiểu tham số hóa với các kiểu lồng nhau:

```java
record Box<T>(T value) {}

static void printNestedBox(Box<Box<String>> nested) {
    if (nested instanceof Box<Box<String>>(
            Box<String>(String text))) {
        System.out.println(text.toUpperCase());
    }
}
```

Pattern bên ngoài chỉ rõ thành phần của nó là một `Box<String>`; pattern bên trong tiếp tục tách giá trị String. Việc ghi type argument ở từng tầng giúp thể hiện cấu trúc dữ liệu lồng nhau một cách tường minh.

## 3. Type argument tường minh và type argument được suy luận

Java có thể suy luận type argument của record pattern từ kiểu của giá trị được kiểm tra. Vì vậy, không phải lúc nào cũng cần viết đầy đủ phần `<...>`.

Với ví dụ:

```java
record Box<T>(T value) {}

static void printBoxContents(Box<String> box) {
    if (box instanceof Box(var text)) {
        System.out.println(text.toUpperCase());
    }
}
```

Trình biên dịch suy luận pattern `Box(var text)` tương đương với:

```java
Box<String>(String text)
```

Kiểu khai báo của biến `box` cung cấp thông tin rằng record có tham số hóa `Box<String>`. Từ đó, trình biên dịch suy luận kiểu thành phần và kiểu biến pattern `text`.

Với record có nhiều type parameter:

```java
record Pair<L, R>(L left, R right) {}

static void printPair(Pair<String, Integer> pair) {
    if (pair instanceof Pair(var left, var right)) {
        System.out.println(left + " / " + right);
    }
}
```

Compiler suy luận pattern tương đương với `Pair<String, Integer>(String left, Integer right)`. Vì vậy, `left` có kiểu `String` và `right` có kiểu `Integer`.

Cơ chế suy luận type argument áp dụng trong các ngữ cảnh chấp nhận pattern, bao gồm:

- Biểu thức `instanceof`.
- Câu lệnh `switch`.
- Biểu thức `switch`.

Ví dụ trong `switch`:

```java
record Pair<L, R>(L left, R right) {}

static void describe(Pair<String, Integer> pair) {
    switch (pair) {
        case Pair(var left, var right) ->
            System.out.println(left + ", #" + right);
    }
}
```

Ở đây compiler suy luận type argument từ kiểu `Pair<String, Integer>` của selector. Pattern component `var` nhận kiểu tương ứng với thành phần record sau khi suy luận.

### Khi nào nên ghi tường minh?

Nên cân nhắc ghi type argument tường minh khi:

- Muốn người đọc thấy ngay kiểu tham số hóa mà record pattern đang sử dụng.
- Record có nhiều type parameter và việc đọc pattern sẽ dễ nhầm thứ tự.
- Pattern lồng nhau có nhiều tầng generic.
- Muốn thể hiện rõ quan hệ giữa kiểu record và kiểu của các component pattern.

Có thể để compiler suy luận khi kiểu của biểu thức đã thể hiện rõ tham số hóa và pattern ngắn, dễ đọc. Cả hai cách đều là cú pháp Java hợp lệ khi thỏa mãn quy tắc tương thích kiểu.

## 4. Quy tắc tương thích và unchecked conversion

Không phải mọi kiểu record generic đều có thể được dùng tùy ý trong record pattern. Java chỉ cho phép kiểm tra một giá trị với record type đã tham số hóa khi giá trị đó có thể được chuyển đổi sang kiểu record trong pattern mà không cần unchecked conversion.

Ví dụ sau không hợp lệ:

```java
record Box<T>(T value) {}

static void inspectRawBox(Box box) {
    // Lỗi biên dịch:
    // Box không thể được chuyển đổi an toàn thành Box<String>.
    if (box instanceof Box<String>(var value)) {
        System.out.println(value);
    }
}
```

Biến `box` sử dụng raw type `Box`, nên compiler không có thông tin kiểu tham số hóa để chứng minh rằng giá trị phù hợp với `Box<String>`. Phép chuyển đổi này cần unchecked conversion và bị từ chối trong record pattern.

Cách xử lý đúng là giữ thông tin generic ở kiểu khai báo và API:

```java
record Box<T>(T value) {}

static void inspectBox(Box<String> box) {
    if (box instanceof Box<String>(var value)) {
        System.out.println(value.toUpperCase());
    }
}
```

Nếu chương trình thực sự phải nhận một `Box` không biết trước kiểu thành phần, hãy giữ kiểu đó dưới dạng wildcard:

```java
record Box<T>(T value) {}

static void inspectUnknownBox(Box<?> box) {
    if (box instanceof Box<?>(var value)) {
        System.out.println(value);
    }
}
```

Trong trường hợp này, `?` biểu thị một kiểu thành phần chưa biết. Biến `value` không được xem là String hay một kiểu cụ thể nào khác; có thể sử dụng nó thông qua kiểu an toàn chung mà compiler suy luận được.

Nếu cần xử lý theo kiểu thực tế của thành phần, hãy kiểm tra chính thành phần bằng một component pattern thích hợp. Ví dụ, với một giá trị thành phần có thể là String:

```java
static void printStringFromUnknownBox(Box<?> box) {
    if (box instanceof Box<?>(String text)) {
        System.out.println(text.strip());
    }
}
```

Pattern `Box<?>` giữ nguyên sự không xác định của type argument, còn component pattern `String text` kiểm tra giá trị thành phần có phải String hay không. Cách này khác với việc giả định toàn bộ record có kiểu `Box<String>`.

## 5. Type argument và type erasure

Generic trong Java được triển khai với type erasure. Thông tin tham số kiểu như `String` hoặc `Integer` không tạo ra một lớp runtime riêng cho mỗi cách tham số hóa.

Ví dụ, `Box<String>` và `Box<Integer>` đều có cùng lớp runtime là `Box`. Không thể dùng reflection hoặc kiểm tra lớp runtime thông thường để phân biệt chính xác hai cách tham số hóa này.

Điều đó không có nghĩa là type argument trong record pattern vô dụng. Type argument vẫn có vai trò quan trọng tại compile time:

- Xác định kiểu tĩnh của component pattern.
- Giúp compiler kiểm tra các thao tác trên biến pattern.
- Cho phép kiểm tra tính tương thích giữa kiểu selector và kiểu record pattern.
- Giúp compiler suy luận kiểu của các biến được khai báo trong component pattern.

Tuy nhiên, không nên hiểu `Box<String>` trong pattern như một yêu cầu runtime phải tìm được metadata generic để xác nhận đối tượng được tạo ra ban đầu bằng `new Box<String>(...)`. Java không lưu type argument theo cách đó. Việc kiểm tra runtime còn phụ thuộc vào kiểu record có thể kiểm tra và các component pattern cụ thể.

Đặc biệt, không được dùng raw type để né quy tắc an toàn kiểu. Khi mất thông tin generic, compiler có thể không chứng minh được phép chuyển đổi cần thiết và từ chối pattern.

## 6. Type argument với record có giới hạn kiểu

Generic record có thể khai báo giới hạn cho type parameter. Type argument trong record pattern phải tuân thủ các giới hạn đó.

Ví dụ:

```java
record Measurement<T extends Number>(T value) {}

static double toDouble(Measurement<Integer> measurement) {
    if (measurement instanceof Measurement<Integer>(var value)) {
        return value.doubleValue();
    }
    return 0.0;
}
```

Vì `T` bị giới hạn bởi `Number`, các kiểu tham số hóa hợp lệ phải thỏa mãn giới hạn này. Trong pattern, `Measurement<Integer>` thay `T` bằng `Integer`, nên biến `value` được suy luận là `Integer` và có thể gọi `doubleValue()`.

Một type argument không thỏa mãn giới hạn sẽ bị compiler từ chối:

```java
// Không hợp lệ vì String không kế thừa Number.
// Measurement<String>(var value)
```

Giới hạn kiểu tiếp tục được kiểm tra tại compile time như trong các khai báo generic thông thường.

## 7. Các lỗi thường gặp

| Cách viết hoặc tình huống | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Dùng raw type rồi pattern với type argument cụ thể | Cần unchecked conversion để chuyển raw type sang kiểu tham số hóa | Duy trì kiểu generic hoặc dùng wildcard nếu không biết kiểu thành phần |
| Ghi sai thứ tự type argument | Không khớp thứ tự type parameter trong khai báo record | Đối chiếu khai báo record trước khi viết pattern |
| Gọi method không có trên kiểu component đã suy luận | Biến pattern có kiểu tĩnh theo type argument, không theo suy đoán của người viết | Kiểm tra kiểu component và chọn API phù hợp |
| Ghi type argument không thỏa mãn bound | Vi phạm giới hạn của type parameter | Dùng kiểu thỏa mãn giới hạn khai báo |
| Nhầm type argument với kiểm tra generic runtime | Generic type argument bị xóa khi chạy | Dùng component pattern để kiểm tra giá trị thành phần khi cần |
| Lạm dụng raw type để làm pattern dễ biên dịch | Mất an toàn kiểu và có thể gây lỗi unchecked | Giữ kiểu tham số hóa hoặc dùng wildcard có chủ đích |

Khi compiler báo lỗi ở một record pattern generic, hãy kiểm tra lần lượt: khai báo record, kiểu tĩnh của giá trị selector, type argument đã ghi, các giới hạn kiểu và kiểu của từng component pattern.

## 8. Hướng dẫn lựa chọn cách viết

Có thể dùng các quy tắc sau khi thiết kế record pattern:

1. Nếu kiểu selector đã có thông tin generic rõ ràng và pattern đơn giản, để compiler suy luận thường giúp mã ngắn gọn.
2. Nếu record có nhiều tham số kiểu hoặc pattern lồng sâu, ghi type argument tường minh có thể làm rõ ý định.
3. Nếu kiểu selector không biết tham số hóa, dùng wildcard như `Box<?>` và kiểm tra thành phần bằng component pattern.
4. Tránh raw type vì nó làm mất thông tin cần thiết để kiểm tra an toàn.
5. Dùng `var` cho component khi kiểu được suy luận đã rõ; dùng type pattern cụ thể khi cần kiểm tra thêm kiểu của giá trị thành phần.

## 9. Phạm vi hỗ trợ trong Java 21

Record patterns được hoàn thiện trong Java 21 qua JEP 440. Generic record patterns hỗ trợ cả hai cách: ghi type argument tường minh và để compiler suy luận type argument từ ngữ cảnh. Tính năng này dùng được trực tiếp trong mã nguồn Java 21, không cần bật `--enable-preview`.

Khi áp dụng, cần nhớ:

- Type argument tường minh làm rõ kiểu tham số hóa của record pattern và kiểu tĩnh của các thành phần.
- Nếu bỏ type argument, compiler có thể suy luận từ kiểu selector và ngữ cảnh pattern.
- Một pattern tham số hóa chỉ hợp lệ khi phép chuyển đổi cần thiết không đòi hỏi unchecked conversion.
- Type erasure có nghĩa là generic type argument không phải một nhãn runtime để phân biệt các đối tượng cùng lớp generic.

Hiểu đúng các quy tắc này giúp khai thác record pattern với generic mà vẫn giữ được kiểm tra kiểu tĩnh và tính an toàn của Java 21.

## Tài liệu tham khảo

- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
