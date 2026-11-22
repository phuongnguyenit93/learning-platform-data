# Quan hệ giữa kiểu đầu vào và kiểu trả về

## 1. Giá trị của generic nằm ở quan hệ kiểu

Một tiện ích nhận dữ liệu rồi trả kết quả cần diễn đạt được người gọi có thể biết gì về kiểu kết quả. Nếu chỉ nhận và trả `Object`, mọi dữ liệu đều có thể đi qua nhưng thông tin kiểu cụ thể không còn được giữ trong chữ ký.

So sánh hai phương thức:

```java
static Object keepAsObject(Object value) {
    return value;
}

static <T> T keep(T value) {
    return value;
}
```

Đây là các phương thức minh họa đặt trong một lớp bao ngoài. Cả hai phần triển khai đều trả lại đối số đầu vào, nhưng hợp đồng kiểu khác nhau.

`keepAsObject` luôn có kiểu trả về khai báo là `Object`. Với `keep`, cùng tên tham số kiểu `T` xuất hiện ở đầu vào và đầu ra: người gọi chọn hoặc để trình biên dịch suy luận một `T` phù hợp cho lần gọi, rồi nhận kết quả theo cùng quan hệ đó.

```java
String code = keep("A12");
Integer count = keep(7);
```

Không cần ép kiểu kết quả. Với đối số số nguyên, giá trị được đóng hộp khi tham gia phương thức generic; đối số kiểu là kiểu tham chiếu như `Integer`, không phải `int`.

Generic không có nghĩa “trả về bất cứ kiểu nào người gọi muốn”. Kiểu được chọn phải đồng thời phù hợp với đầu vào, chữ ký phương thức và ngữ cảnh sử dụng kết quả. Đây là hợp đồng được kiểm tra khi biên dịch, vẫn dùng trong Java hiện hành.

## 2. Đọc chữ ký như một đường nối thông tin

| Chữ ký điển hình | Quan hệ được diễn đạt |
| --- | --- |
| `<T> T keep(T value)` | Kiểu kết quả liên hệ trực tiếp với kiểu đầu vào qua `T` |
| `<T> T head(List<T> values)` | Kiểu phần tử của danh sách trở thành kiểu kết quả |
| `<T> List<T> one(T value)` | Kiểu giá trị đầu vào trở thành kiểu phần tử của danh sách kết quả |
| `<T> T select(boolean first, T a, T b)` | Hai đối số và kết quả cùng tương thích với một `T` được chọn |
| `<S, R> R convert(S source, Function<S, R> converter)` | Kiểu nguồn `S` và kiểu kết quả `R` được nối bằng một hàm chuyển đổi |

Các dòng trong bảng là chữ ký, không phải chương trình độc lập. Khi đọc, hãy tìm từng lần xuất hiện của một tên kiểu và xem nó nối những vị trí nào. Việc một tên xuất hiện trong `List<T>` vẫn mang quan hệ với `T` trực tiếp ở nơi khác; nó không chỉ là ký hiệu trang trí.

Phương thức chỉ thực sự generic khi tự khai báo danh sách tham số kiểu như `<T>` hoặc `<S, R>` trước kiểu trả về. Nếu một phương thức dùng tham số đã được khai báo ở lớp, quan hệ với kiểu lớp vẫn có giá trị nhưng phạm vi lựa chọn kiểu không giống tham số riêng của phương thức.

Tham khảo khai báo phương thức generic tại [JLS §8.4.4](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.4).

## 3. Giữ kiểu qua cấu trúc dữ liệu

### 3.1. Từ danh sách tới một phần tử

```java
static <T> T head(List<T> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("empty list");
    }
    return values.get(0);
}
```

Với `List<String>`, có thể gán kết quả cho `String`. Với `List<Integer>`, có thể gán cho `Integer`. Cùng một phương thức giữ được quan hệ kiểu phần tử mà không cần viết riêng `headString` và `headInteger`.

Chữ ký không bảo đảm danh sách có phần tử. Trong phần triển khai này, danh sách rỗng khiến phương thức ném `IllegalArgumentException`; đối số `null` vẫn có thể gây `NullPointerException`. Chính sách rỗng và `null` là hợp đồng giá trị cần được giải thích thêm, không được suy ra chỉ từ `T`.

### 3.2. Từ một phần tử tới danh sách

```java
static <T> List<T> one(T value) {
    return List.of(value);
}
```

Nếu truyền một chuỗi, danh sách kết quả có thể được dùng theo kiểu `List<String>`. Nếu truyền một số nguyên, danh sách có thể được dùng theo kiểu `List<Integer>` trong ngữ cảnh phù hợp.

Cấu trúc kết quả thay đổi từ một giá trị thành danh sách, nhưng kiểu phần tử vẫn được nối với đầu vào bằng `T`. Phần triển khai dùng `List.of`, nên danh sách không cho sửa và không nhận phần tử `null`. Những tính chất đó đến từ API được sử dụng, không phải từ cú pháp generic.

Đừng đổi kiểu trả về thành `List<Object>` nếu muốn giữ quan hệ này. Một `List<Object>` có thể chứa nhiều kiểu, nhưng không thể gán nó trực tiếp cho `List<String>` chỉ vì lần gọi hiện tại đã truyền chuỗi.

## 4. Đổi kiểu cần một quan hệ chuyển đổi rõ ràng

Khi kiểu đầu ra khác kiểu đầu vào, dùng hai tham số kiểu và mô tả điều nối chúng. Ví dụ:

```java
static <S, R> R convert(S source, Function<S, R> converter) {
    return converter.apply(source);
}
```

`S` là kiểu nguồn, `R` là kiểu kết quả. `Function<S, R>` biểu đạt hành vi nhận một `S` và tạo một `R`. Nó là bằng chứng trong chữ ký rằng nguồn có thể được đưa vào hàm chuyển đổi và kết quả của hàm đó đáp ứng kiểu trả về.

```java
Integer parsed = convert("42", Integer::valueOf);
String description = convert(7, n -> "stock=" + n);
```

Lần gọi đầu chuyển nguồn chuỗi thành kết quả số nguyên. Lần gọi thứ hai nhận một số nguyên và xây dựng chuỗi mô tả. Không có quy tắc tự động rằng `S` phải là kiểu con của `R`, hay ngược lại.

Nếu chỉ viết `<S, R> R convert(S source)` rồi thử `return source;`, mã không biên dịch: `S` và `R` là hai tham số độc lập, chưa có quan hệ cho phép dùng một giá trị `S` như một `R`.

Thêm ép kiểu từ `S` sang `R` không tạo ra phép chuyển đổi dữ liệu. Chuyển chuỗi thành số cần thao tác như `Integer.valueOf`; ép tham chiếu không biến một đối tượng `String` thành `Integer`.

Chữ ký `Function<S, R>` trong bài được giữ đơn giản để thấy rõ đường nối kiểu. API cần nhận các hàm chuyển đổi linh hoạt hơn có thể dùng wildcard phù hợp, chẳng hạn `Function<? super S, ? extends R>`; đó là cách mở rộng tương thích, vẫn giữ vai trò nguồn và kết quả.

Tài liệu [Function](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/Function.html) định nghĩa rõ tham số kiểu đầu vào và kiểu kết quả của hàm.

## 5. Một tên `T` không bắt buộc cùng lớp lúc chạy

Xét phương thức chọn một trong hai giá trị:

```java
static <T> T select(boolean useFirst, T first, T second) {
    return useFirst ? first : second;
}
```

`T` phải là một kiểu phù hợp với cả hai đối số và cách sử dụng kết quả. Nó không yêu cầu hai đối tượng có cùng lớp cụ thể khi chạy.

```java
Number selected = select(true, 7, 2.5);
```

Một lựa chọn kiểu chung phù hợp có thể chứa cả `Integer` và `Double`, đồng thời đáp ứng kiểu đích `Number`. Phần triển khai trả về đối số đầu khi điều kiện là `true`; nó không đổi số nguyên thành số thực chỉ vì đối số còn lại là `Double`.

Không thể suy từ đó rằng lời gọi sau phải hợp lệ:

```java
// String invalid = select(true, "ready", 42);
// Bỏ dấu chú thích để thử lỗi biên dịch.
```

Dù điều kiện đang viết là `true`, toàn bộ lời gọi vẫn phải thỏa mãn chữ ký có hai đối số `T`. Một kết quả được yêu cầu là `String` không thể đồng thời làm cho giá trị `Integer` ở đối số thứ hai phù hợp với `T` đó.

Ngược lại, có thể dùng kiểu đích rộng hơn khi mô hình dữ liệu cho phép. Điều này không bảo đảm kết quả là một chuỗi; người dùng kết quả chỉ được dựa vào hợp đồng kiểu chung đã chọn.

## 6. Đầu vào và kiểu đích cùng ràng buộc suy luận

Trình biên dịch không chỉ nhìn kiểu biến nhận rồi bỏ qua đầu vào. Ví dụ:

```java
Object unknown = "A12";
// String code = keep(unknown); // Lỗi biên dịch nếu bỏ chú thích
```

Biểu thức `unknown` có kiểu tĩnh `Object`, dù giá trị trong lần chạy dự kiến là chuỗi. Không thể chọn một `T` vừa nhận một `Object` bất kỳ theo kiểu tĩnh đó vừa bảo đảm kết quả là `String` mà không có kiểm tra/chuyển đổi bổ sung.

Tương tự, nếu giữ kết quả trong một biến rộng hơn:

```java
Object broad = keep("A12");
```

Biến `broad` có kiểu khai báo `Object`, nên các thao tác tiếp theo qua biến này được kiểm tra theo `Object`. Phương thức generic không làm biến ấy tự có kiểu `String` hay tự có phương thức `length()`.

Có thể ghi rõ đối số kiểu của phương thức:

```java
String code = InputReturnRelationDemo.<String>keep("A12");
```

Cách viết này chọn `T = String`, nhưng vẫn phải truyền một đối số phù hợp. Ghi `<String>` không cho phép truyền một biến có kiểu tĩnh `Object` bất kỳ và nhận chuỗi an toàn.

Quá trình suy luận có thể kết hợp ràng buộc từ đối số và ngữ cảnh đích; xem [JLS §18.5.2](https://docs.oracle.com/javase/specs/jls/se25/html/jls-18.html#jls-18.5.2).

## 7. Chương trình chạy đầy đủ

Lưu thành `InputReturnRelationDemo.java`:

```java
import java.util.List;
import java.util.function.Function;

public class InputReturnRelationDemo {
    static <T> T keep(T value) {
        return value;
    }

    static <T> T select(boolean useFirst, T first, T second) {
        return useFirst ? first : second;
    }

    static <T> T head(List<T> values) {
        if (values.isEmpty()) {
            throw new IllegalArgumentException("empty list");
        }
        return values.get(0);
    }

    static <T> List<T> one(T value) {
        return List.of(value);
    }

    static <S, R> R convert(S source, Function<S, R> converter) {
        return converter.apply(source);
    }

    public static void main(String[] args) {
        String code = keep("A12");
        Integer count = keep(7);
        System.out.println("code=" + code);
        System.out.println("count=" + count);

        List<String> codes = List.of("A12", "B07");
        String firstCode = head(codes);
        List<String> wrapped = one(firstCode);
        System.out.println("head=" + firstCode);
        System.out.println("wrapped=" + wrapped);

        Integer parsed = convert("42", Integer::valueOf);
        String description = convert(7, n -> "stock=" + n);
        System.out.println("parsed=" + parsed);
        System.out.println("description=" + description);

        Number selected = select(true, 7, 2.5);
        System.out.println("selected=" + selected);

        Object broad = keep("A12");
        System.out.println("broad=" + broad);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 -Xlint:all -Werror InputReturnRelationDemo.java
java InputReturnRelationDemo
```

Stdout:

```text
code=A12
count=7
head=A12
wrapped=[A12]
parsed=42
description=stock=7
selected=7
broad=A12
```

Mỗi kiểu kết quả có thể được lần ngược về hợp đồng đầu vào hoặc hàm chuyển đổi. Không phương thức nào cần ép kiểu kết quả để thỏa mãn chữ ký của mình.

`parsed` có thể được kiểm tra là `Integer` khi biên dịch, nhưng một nguồn như `"abc"` vẫn có thể làm `Integer.valueOf` ném `NumberFormatException`. Quan hệ kiểu đúng không bảo đảm mọi nội dung giá trị đều chuyển đổi thành công.

## 8. Những giới hạn của lời hứa trong chữ ký

### 8.1. Cùng kiểu không đồng nghĩa cùng đối tượng

Chữ ký `<T> T method(T value)` bảo vệ quan hệ tương thích kiểu; tự nó không khẳng định phương thức trả lại cùng tham chiếu đầu vào. Muốn biết kết quả là chính đối tượng đó, một bản sao hay một giá trị được tìm từ nơi khác, phải đọc hợp đồng hành vi và phần triển khai.

Với `keep` trong bài, phần triển khai trả lại đúng đối số. Với `select`, nó trả lại một trong hai đối số. Đây là hành vi cụ thể của hai phương thức, không phải quy tắc bắt buộc cho mọi phương thức có kiểu trả về `T`.

### 8.2. Tham số chỉ xuất hiện ở đầu ra cần có nguồn bảo đảm

Một phương thức `<T> T load(String key)` không cho thấy dữ liệu theo khóa liên hệ với `T` như thế nào. Chỉ thêm chữ `T` vào kiểu trả về không đủ chứng minh rằng một dữ liệu bất kỳ từ kho là kiểu mà người gọi yêu cầu.

API thực tế có thể cần một đối số `Class<T>`, một bộ giải mã có kiểu, một đối tượng khóa generic hoặc một hợp đồng dữ liệu khác để gắn yêu cầu kiểu với kết quả. Một phép ép kiểu `unchecked` bị che cảnh báo không thay thế được nguồn bảo đảm ấy.

Việc `T` chỉ xuất hiện ở đầu ra không tự làm mọi phương thức như vậy sai: một hàm tạo cấu trúc rỗng có thể đáp ứng nhiều kiểu mà không lấy phần tử từ nguồn. Điểm cần xem xét là phần triển khai có thực sự cung cấp được hợp đồng cho mọi lựa chọn kiểu hợp lệ hay không.

### 8.3. Tránh làm mất quan hệ khi đi qua `Object`

Nếu một tầng API nhận `List<T>` rồi trả `Object`, các tầng sau không tự khôi phục được kiểu phần tử chỉ nhờ generic ở đầu đường đi. Cần giữ thông tin kiểu trong những chữ ký trung gian khi chúng thực sự có quan hệ ấy.

Cũng không nên dùng hai tên độc lập `<A, B>` khi dữ liệu đầu ra phải có cùng kiểu đầu vào. Ngược lại, không ép chỉ dùng một `T` cho cả nguồn và kết quả nếu thao tác thật sự chuyển từ `String` sang `Integer`. Chọn số lượng tham số theo quan hệ thực tế.

## 9. Tự kiểm tra

1. Vì sao `<T> T head(List<T> values)` cho biết nhiều hơn `Object head(List<?> values)` về kiểu kết quả?
2. `<S, R> R convert(S source)` có tự chứng minh rằng có thể trả `source` làm `R` không?
3. Một biến `Object` đang giữ chuỗi có thể được truyền vào `keep` rồi gán thẳng kết quả cho `String` không?
4. Hai đối số cho `select` có bắt buộc có cùng `getClass()` không?
5. `<T> T method(T value)` có bảo đảm kết quả là chính đối tượng đầu vào không?

Đáp án:

1. Nó nối kiểu phần tử của danh sách đầu vào với kiểu kết quả qua cùng `T`; chữ ký trả `Object` không giữ quan hệ cụ thể đó cho nơi gọi.
2. Không. `S` và `R` độc lập nếu chưa có quan hệ hoặc hành vi chuyển đổi phù hợp.
3. Không chỉ dựa vào thông tin đó. Kiểu tĩnh của đầu vào là `Object`, nên không đủ bảo đảm kết quả `String`.
4. Không. Có thể chọn một kiểu chung phù hợp với cả đối số và kiểu đích, nhưng chỉ được dùng kết quả theo hợp đồng được bảo đảm.
5. Không. Điều đó là hợp đồng hành vi cần được xác định riêng; quan hệ generic bảo vệ kiểu tương thích.

Khi thiết kế phương thức generic, hãy vẽ được đường nối từ nguồn kiểu tới kết quả: cùng một giá trị, phần tử của cấu trúc, cấu trúc bao quanh giá trị hoặc một phép chuyển đổi có kiểu. Nếu đường nối chưa rõ, thêm một chữ cái generic vào kiểu trả về sẽ không tự làm hợp đồng trở nên đúng.
