# Kết hợp record generic với sealed hierarchy

Khi một mô hình dữ liệu có nhiều biến thể nhưng các biến thể cùng mang một kiểu dữ liệu tổng quát, có thể kết hợp **generic record** với **sealed hierarchy** để mô tả cấu trúc đó. Generic giúp tái sử dụng mô hình với nhiều kiểu dữ liệu; sealed interface giới hạn tập biến thể; Record Patterns trong Java 21 giúp phân rã từng biến thể ngay trong `switch`.

Ví dụ, một thao tác API có thể trả về kết quả thành công hoặc thất bại. Kết quả thành công mang dữ liệu kiểu `T`, còn kết quả thất bại mang mã lỗi và thông báo. Cả hai đều thuộc cùng một kiểu `ApiResult<T>`, nên tầng gọi có thể làm việc với một hợp đồng chung mà vẫn giữ được kiểu dữ liệu cụ thể.

Các tính năng liên quan đã được hoàn thiện trong những phiên bản sau:

- Generic types là một phần của Java từ Java 5.
- Record trở thành tính năng chính thức trong Java 16.
- Sealed classes và sealed interfaces trở thành tính năng chính thức trong Java 17.
- Record Patterns và pattern matching for `switch` trở thành tính năng chính thức trong Java 21.

## 1. Ôn tập generic record

Record có thể khai báo tham số kiểu giống class và interface. Danh sách tham số kiểu được đặt sau tên record, trước danh sách record components:

```java
public record Pair<K, V>(K key, V value) {
}
```

`Pair<K, V>` là một record tổng quát. `K` đại diện cho kiểu của `key`, còn `V` đại diện cho kiểu của `value`. Có thể tạo các đối tượng với những kiểu khác nhau:

```java
Pair<String, Integer> quantity = new Pair<>("books", 12);
Pair<Long, String> owner = new Pair<>(1001L, "An");

String key = quantity.key();
Integer value = quantity.value();
```

Trình biên dịch suy luận tham số kiểu từ ngữ cảnh khi sử dụng toán tử kim cương `<>`. Accessor được sinh tự động giữ kiểu thành phần tương ứng, vì vậy `quantity.key()` có kiểu `String` và `quantity.value()` có kiểu `Integer`.

Generic record cũng có thể khai báo giới hạn kiểu:

```java
public record Measurement<T extends Number>(T value, String unit) {
}
```

Với `T extends Number`, thành phần `value` chỉ có thể dùng kiểu `Number` hoặc kiểu con của nó. Điều này cho phép mã trong record gọi các hành vi được bảo đảm bởi `Number`, đồng thời giữ kiểu cụ thể của giá trị.

Record vẫn tuân theo quy tắc của record thông thường: các thành phần được lưu trong trường `private final`, constructor chính và accessor được sinh tự động, và record là lớp `final`. Việc thêm tham số kiểu không làm record có thể được kế thừa.

## 2. Xây dựng sealed hierarchy có tham số kiểu

Có thể khai báo một sealed interface tổng quát để đại diện cho một nhóm kết quả. Các kiểu con được phép cũng khai báo tham số kiểu và truyền tham số đó vào kiểu cha:

```java
public sealed interface ApiResult<T>
        permits ApiResult.Success, ApiResult.Failure {

    record Success<T>(T data) implements ApiResult<T> {
    }

    record Failure<T>(String code, String message) implements ApiResult<T> {
    }
}
```

Trong mô hình này:

- `ApiResult<T>` là hợp đồng tổng quát cho một kết quả.
- `Success<T>` là biến thể thành công, chứa dữ liệu có kiểu `T`.
- `Failure<T>` là biến thể thất bại, chứa mã lỗi và thông báo nhưng vẫn giữ `T` để biểu diễn cùng một loại kết quả dự kiến.
- Mệnh đề `permits` giới hạn những kiểu được phép triển khai trực tiếp `ApiResult`.

Các record lồng bên trong interface có tính chất `public static` ngầm định. Mỗi record tự khai báo tham số kiểu `T` và triển khai `ApiResult<T>`. Việc lặp lại `T` trong khai báo record là cần thiết vì tham số kiểu của một kiểu thành viên static không tự lấy tham số kiểu từ một instance của kiểu bao ngoài.

Có thể tạo kết quả theo kiểu dữ liệu cụ thể:

```java
ApiResult<String> textResult =
        new ApiResult.Success<>("Completed");

ApiResult<Integer> countResult =
        new ApiResult.Success<>(42);

record User(String id, String name) {
}

ApiResult<User> userResult =
        new ApiResult.Failure<>("USER_NOT_FOUND", "User does not exist");
```

`Failure<User>` vẫn là một `ApiResult<User>` dù không lưu một đối tượng `User`. Điều đó cho biết kết quả này thuộc thao tác dự kiến trả về `User`, nhưng thao tác đã thất bại. Nếu mô hình cần lưu dữ liệu bổ sung khi thất bại, có thể thêm các record components phù hợp, chẳng hạn mã tương quan hoặc thông tin lỗi có cấu trúc.

## 3. Giữ đúng quan hệ kiểu giữa biến thể và kiểu cha

Khi một kiểu con triển khai sealed generic interface, cần truyền tham số kiểu một cách nhất quán:

```java
sealed interface BoxResult<T> permits BoxResult.Value {
    record Value<T>(T data) implements BoxResult<T> {
    }
}
```

Khai báo này bảo đảm `BoxResult.Value<String>` là một `BoxResult<String>`, `BoxResult.Value<User>` là một `BoxResult<User>`, và kiểu dữ liệu của `data` được giữ nguyên trong quá trình biên dịch. Trong mô hình ở phần trước, `Success<T>` áp dụng cùng quy tắc khi triển khai `ApiResult<T>`.

Không nên bỏ tham số kiểu của kiểu cha hoặc dùng raw type:

```java
// Không nên: raw type làm mất thông tin kiểu và có thể phát sinh cảnh báo.
Pair rawPair = new Pair("books", 12);
```

Trong mã Java hiện đại, hãy dùng kiểu tham số hóa đầy đủ. Nếu kiểu dữ liệu cụ thể chưa biết, wildcard `?` thể hiện rõ hơn rằng đây là một kiểu chưa xác định:

```java
ApiResult<?> result = new ApiResult.Success<>("Some value");
```

`ApiResult<?>` có thể tham chiếu đến `ApiResult<String>`, `ApiResult<User>` hoặc một tham số hóa hợp lệ khác. Khi đọc qua kiểu wildcard, mã gọi không được giả định kiểu dữ liệu cụ thể của giá trị.

## 4. Phân tích generic record bằng Record Patterns trong Java 21

Java 21 cho phép dùng Record Patterns trong nhãn `case` của switch. Khi kiểu cha và các biến thể cùng mang tham số `T`, có thể viết pattern với chính tham số kiểu đó:

```java
static <T> String describe(ApiResult<T> result) {
    return switch (result) {
        case ApiResult.Success<T>(var data) ->
                "Success: " + data;

        case ApiResult.Failure<T>(var code, var message) ->
                "Failure: " + code + " - " + message;
    };
}
```

Phương thức `describe` là generic method với tham số kiểu `T`. Selector có kiểu `ApiResult<T>`, vì vậy các pattern dùng `ApiResult.Success<T>` và `ApiResult.Failure<T>` để giữ cùng quan hệ kiểu.

Ở nhánh thành công, `var data` được suy luận là kiểu `T`, không phải `Object`. Ở nhánh thất bại, `code` và `message` được suy luận là `String`. Không cần ép kiểu thủ công để lấy các thành phần của record.

Có thể viết kiểu tường minh trong component pattern nếu muốn nhấn mạnh kiểu dữ liệu:

```java
static void printTextResult(ApiResult<String> result) {
    switch (result) {
        case ApiResult.Success<String>(String data) -> System.out.println(data);
        case ApiResult.Failure<String>(String code, String message) ->
                System.out.println(code + ": " + message);
    }
}
```

`var` hữu ích khi kiểu đã rõ từ khai báo record; kiểu tường minh hữu ích khi người đọc cần thấy ngay hợp đồng dữ liệu tại vị trí xử lý.

## 5. Vì sao switch có thể exhaustive?

`ApiResult<T>` là sealed interface và khai báo hai biến thể được phép: `Success<T>` và `Failure<T>`. Trong phương thức `describe`, hai Record Patterns bao phủ cả hai biến thể. Vì vậy, switch expression không cần `default` mà vẫn có thể được trình biên dịch xác nhận là exhaustive.

Nếu thêm biến thể mới, chẳng hạn `Loading<T>`, phải bổ sung kiểu đó vào `permits` và khai báo record tương ứng:

```java
public sealed interface ApiResult<T>
        permits ApiResult.Success, ApiResult.Failure, ApiResult.Loading {

    record Success<T>(T data) implements ApiResult<T> {
    }

    record Failure<T>(String code, String message) implements ApiResult<T> {
    }

    record Loading<T>(String operationId) implements ApiResult<T> {
    }
}
```

Sau thay đổi này, switch xử lý `ApiResult<T>` cần được xem xét để xử lý `Loading<T>`. Khi biên dịch lại cùng định nghĩa sealed hierarchy mới, compiler có thể báo switch không còn exhaustive. Đây là lợi ích quan trọng của việc kiểm soát tập biến thể: thay đổi mô hình được phản ánh vào những nơi phân tích mô hình.

Không nên thêm `default` một cách máy móc nếu mục tiêu là để compiler giúp phát hiện biến thể mới. Với các ranh giới mở hoặc khi cần chính sách dự phòng rõ ràng, nhánh tổng quát có thể phù hợp; lựa chọn này nên phản ánh yêu cầu của ứng dụng.

## 6. Dùng wildcard khi kiểu dữ liệu cụ thể chưa biết

Một phương thức có thể nhận `ApiResult<?>` khi chỉ cần xử lý hình dạng kết quả mà không cần biết chính xác kiểu payload:

```java
static String describeUnknown(ApiResult<?> result) {
    return switch (result) {
        case ApiResult.Success(var data) ->
                "Success with value: " + data;

        case ApiResult.Failure(var code, var message) ->
                "Failure: " + code + " - " + message;
    };
}
```

Wildcard cho biết tham số kiểu là một kiểu cụ thể nào đó nhưng chưa được gọi tên tại vị trí này. Trong record pattern, Java 21 suy luận tham số kiểu từ kiểu selector; ở đây tham số của `Success` là capture tương ứng với wildcard `?`. `var data` có kiểu capture đó; có thể truyền giá trị vào những API nhận `Object`, hoặc gọi các hành vi được bảo đảm bởi giới hạn kiểu nếu wildcard có bound.

Nếu chỉ đọc dữ liệu, `ApiResult<?>` thường là lựa chọn phù hợp. Nếu cần tạo kết quả cùng kiểu với đầu vào hoặc chuyển payload sang một biến cùng kiểu, generic method `<T>` thường biểu đạt quan hệ đó rõ ràng hơn:

```java
static <T> ApiResult<T> identity(ApiResult<T> result) {
    return result;
}
```

Không nên thay wildcard bằng raw type `ApiResult`. Raw type bỏ qua kiểm tra generic và có thể làm mất an toàn kiểu tại compile time.

## 7. Hiểu type erasure khi dùng generic patterns

Java triển khai generics bằng type erasure. Tham số kiểu như `T` được kiểm tra chủ yếu trong quá trình biên dịch; tại runtime, các kiểu tham số hóa cùng lớp dùng chung biểu diễn lớp đã xóa tham số kiểu.

Java 21 cho phép ghi rõ tham số kiểu của generic record pattern khi phép chuyển đổi từ kiểu selector sang kiểu pattern được kiểm tra an toàn. Nếu bỏ tham số kiểu, compiler có thể suy luận chúng từ kiểu selector:

```java
record Box<T>(T value) {
}

static void printBox(Box<String> box) {
    if (box instanceof Box<String>(String value)) {
        System.out.println(value);
    }

    // Tương đương về kết quả suy luận: Box<String>(String value).
    if (box instanceof Box(var value)) {
        System.out.println(value.toUpperCase());
    }
}
```

Ngược lại, nếu biến có raw type `Box`, compiler không thể xác nhận tham số `String` một cách an toàn:

```java
static void inspectRawBox(Box box) {
    // Lỗi biên dịch: cần unchecked conversion từ Box sang Box<String>.
    if (box instanceof Box<String>(var value)) {
        System.out.println(value);
    }
}
```

Vì vậy, hãy giữ kiểu tham số hóa đầy đủ ở selector và dùng generic record pattern với kiểu đối số có thể được kiểm tra hoặc suy luận an toàn.

Điều này có một hệ quả quan trọng: không thể dùng Record Patterns để phân biệt hai instance của cùng một generic record chỉ vì chúng được tạo với tham số kiểu khác nhau.

Ví dụ, không thiết kế logic theo ý tưởng có hai nhánh runtime riêng như sau:

```java
// Không dùng generic type argument như một nhãn phân biệt runtime.
case ApiResult.Success<String>(var text) -> ...
case ApiResult.Success<Integer>(var number) -> ...
```

Hai trường hợp trên cùng chỉ đến một lớp runtime `ApiResult.Success`; tham số kiểu `String` và `Integer` không tạo ra hai lớp khác nhau. Ngoài ra, pattern có kiểu tham số không reifiable có thể không được chấp nhận nếu không có chuyển đổi thu hẹp được kiểm tra an toàn từ kiểu selector sang kiểu pattern.

Nếu ứng dụng cần phân biệt biến thể tại runtime, hãy biểu diễn sự khác nhau bằng các kiểu con riêng trong sealed hierarchy, hoặc dùng một trường discriminator có kiểu rõ ràng khi đó thực sự là dữ liệu nghiệp vụ. Dùng generic để giữ quan hệ kiểu ở compile time, không dùng generic argument như một cơ chế phân nhánh runtime.

## 8. Generic invariance và wildcard

Các kiểu generic trong Java là invariant. Dù `String` là subtype của `Object`, `ApiResult<String>` không phải subtype của `ApiResult<Object>`.

```java
ApiResult<String> strings = new ApiResult.Success<>("Hello");

// Không hợp lệ: generic types là invariant.
// ApiResult<Object> objects = strings;
```

Khi cần nhận kết quả có payload là một subtype của một kiểu cơ sở, có thể dùng wildcard có giới hạn:

```java
static void printNumberResult(ApiResult<? extends Number> result) {
    switch (result) {
        case ApiResult.Success(var value) ->
                System.out.println(value.doubleValue());

        case ApiResult.Failure(var code, var message) ->
                System.out.println(code + ": " + message);
    }
}
```

`? extends Number` cho phép nhận các kết quả thành công mang `Integer`, `Long`, `Double` hoặc kiểu con khác của `Number`. Giá trị `value` có thể được sử dụng như một `Number`. Do wildcard không chỉ rõ một kiểu con duy nhất, không thể tùy ý đưa một giá trị `Number` bất kỳ vào vị trí payload đó.

Quy tắc này cũng áp dụng khi kết hợp generic records với collection, API và các kiểu dữ liệu lồng nhau. Chọn wildcard theo hướng dữ liệu được đọc hoặc ghi, và giữ generic method khi cần duy trì mối quan hệ giữa các kiểu đầu vào và đầu ra.

## 9. Generic record lồng nhau trong mô hình dữ liệu

Một biến thể của sealed hierarchy có thể chứa generic record khác. Ví dụ, một kết quả thành công có thể chứa một trang dữ liệu:

```java
import java.util.List;

record User(String id, String name) {
}

record Page<T>(List<T> items, int pageNumber, int pageSize) {
    public Page {
        items = List.copyOf(items);
        if (pageNumber < 0) {
            throw new IllegalArgumentException("pageNumber must not be negative");
        }
        if (pageSize <= 0) {
            throw new IllegalArgumentException("pageSize must be positive");
        }
    }
}

public sealed interface ApiResult<T>
        permits ApiResult.Success, ApiResult.Failure {

    record Success<T>(T data) implements ApiResult<T> {
    }

    record Failure<T>(String code, String message) implements ApiResult<T> {
    }
}
```

Có thể biểu diễn kết quả chứa một trang người dùng bằng `ApiResult<Page<User>>`. Kiểu dữ liệu cho biết payload là `Page<User>`, còn `Page<T>` tái sử dụng được cho nhiều loại phần tử khác nhau.

Nếu cần phân rã sâu nhiều tầng record, Record Patterns cho phép lồng pattern theo cấu trúc thành phần. Tuy nhiên, không nên lồng quá sâu nếu làm nhánh `switch` khó đọc. Có thể tách xử lý thành phương thức nhỏ sau khi đã khớp biến thể ở lớp ngoài.

`List.copyOf` trong ví dụ bảo vệ cấu trúc danh sách khỏi thay đổi qua tham chiếu ban đầu. Nó không tạo bản sao sâu cho từng phần tử; nếu `T` là kiểu mutable, trạng thái bên trong các phần tử vẫn có thể thay đổi.

## 10. Xử lý null và điều kiện hợp lệ

Generic và sealed hierarchy không tự loại bỏ `null`. Nếu `ApiResult<T>` có thể là `null`, switch cần thể hiện chính sách xử lý rõ ràng:

```java
static <T> String describeSafely(ApiResult<T> result) {
    return switch (result) {
        case null -> "No result";
        case ApiResult.Success<T>(var data) -> "Success: " + data;
        case ApiResult.Failure<T>(var code, var message) ->
                "Failure: " + code + " - " + message;
    };
}
```

Nếu không có `case null`, switch trên selector `null` sẽ ném `NullPointerException`. Ở phía tạo dữ liệu, constructor của record nên kiểm tra những thành phần bắt buộc bằng `Objects.requireNonNull` hoặc quy tắc xác thực phù hợp. Sealed hierarchy kiểm soát kiểu biến thể; constructor bảo vệ điều kiện hợp lệ của dữ liệu bên trong biến thể.

## 11. Khi nào nên kết hợp generic record và sealed hierarchy?

Mẫu thiết kế này phù hợp khi có một hợp đồng chung với một số biến thể hữu hạn, và ít nhất một biến thể mang dữ liệu có kiểu thay đổi theo ngữ cảnh.

- **Kết quả API:** `Success<T>` mang payload, `Failure<T>` mang thông tin lỗi.
- **Kết quả xác thực:** `Valid<T>` chứa dữ liệu đã chuẩn hóa, `Invalid<T>` chứa danh sách lỗi cho kiểu dữ liệu dự kiến.
- **Kết quả truy vấn:** `Found<T>` chứa bản ghi, `NotFound<T>` hoặc `Failed<T>` mô tả các kết quả còn lại.
- **Thông điệp xử lý:** một hierarchy có thể có biến thể mang payload generic, metadata hoặc lỗi có cấu trúc.

Không cần dùng generic nếu các biến thể không chia sẻ một kiểu dữ liệu tổng quát hoặc tham số kiểu không giúp tăng an toàn kiểu. Với tập lựa chọn đơn giản không mang dữ liệu riêng, `enum` thường dễ hiểu hơn. Với hệ thống cần bên ngoài tự định nghĩa thêm biến thể, interface mở có thể phù hợp hơn sealed hierarchy.

## 12. Các nguyên tắc thiết kế

1. **Đặt tham số kiểu ở đúng tầng:** dùng `T` trên sealed interface khi toàn bộ kết quả cần giữ cùng kiểu payload; khai báo tham số tương ứng trên từng record variant.
2. **Giữ kiểu cha và kiểu con nhất quán:** triển khai `ApiResult<T>` bằng `Success<T>` hoặc `Failure<T>`, tránh raw types.
3. **Dùng Record Patterns có kiểu phù hợp:** giữ `T` trong generic method, hoặc dùng wildcard khi kiểu payload chưa biết.
4. **Tận dụng exhaustive switch:** liệt kê các biến thể sealed để compiler hỗ trợ phát hiện trường hợp mới.
5. **Hiểu type erasure:** không dùng `Success<String>` và `Success<Integer>` như hai lớp runtime khác nhau.
6. **Chọn wildcard có chủ đích:** `? extends T` phù hợp khi đọc giá trị thuộc một subtype; generic method phù hợp khi cần duy trì quan hệ kiểu giữa nhiều vị trí.
7. **Bảo vệ dữ liệu trong constructor:** kiểm tra tham số bắt buộc và sao chép collection khi cần bảo vệ cấu trúc.
8. **Quy định chính sách null:** xử lý null trong switch hoặc bảo đảm API không trả null.

## 13. Tổng kết

Generic record cho phép mô tả dữ liệu có cấu trúc mà vẫn giữ kiểu thành phần cụ thể. Sealed generic interface định nghĩa một hợp đồng chung và giới hạn các biến thể được phép. Khi mỗi record variant triển khai đúng tham số kiểu của sealed interface, hệ thống vừa tái sử dụng được mô hình, vừa duy trì an toàn kiểu ở compile time.

Java 21 kết hợp các kiểu này với Record Patterns và pattern matching for `switch` để phân tích từng biến thể, lấy dữ liệu thành phần và kiểm tra tính đầy đủ của các nhánh. Cần hiểu thêm wildcard, generic invariance và type erasure để tránh nhầm lẫn giữa kiểm tra kiểu lúc biên dịch với nhận dạng lớp tại runtime.

## Tài liệu tham khảo

- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html) — generic record patterns, type inference và giới hạn chuyển đổi không an toàn.
- [JEP 395: Records](https://openjdk.org/jeps/395) — record classes, được hoàn thiện trong Java 16.
- [JEP 409: Sealed Classes](https://openjdk.org/jeps/409) — sealed classes và sealed interfaces, được hoàn thiện trong Java 17.
- [JEP 440: Record Patterns](https://openjdk.org/jeps/440) — Record Patterns, được hoàn thiện trong Java 21.
- [JEP 441: Pattern Matching for switch](https://openjdk.org/jeps/441) — pattern matching for switch, được hoàn thiện trong Java 21.
- [Java Language Specification, Java SE 21 — Type Parameters](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.4) — khai báo và giới hạn tham số kiểu.
- [Java Language Specification, Java SE 21 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.6) — cơ chế xóa kiểu của generics.
- [Java Language Specification, Java SE 21 — Record Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30) — cú pháp và ngữ nghĩa Record Patterns.
- [Java Language Specification, Java SE 21 — Record Pattern Type Inference](https://docs.oracle.com/javase/specs/jls/se21/html/jls-18.html#jls-18.5.5) — suy luận tham số kiểu trong generic record patterns.
- [Java Language Specification, Java SE 21 — Sealed Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.1.2) — kiểu con được phép trong sealed hierarchy.
