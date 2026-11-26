# Bỏ qua tham số lambda không sử dụng mà vẫn giữ rõ hợp đồng hàm

## Biến và mẫu không tên

Trong module `JAVA_VERSION_JAVA22` — học các tính năng được giới thiệu trong Java 22 còn hữu ích ở Java hiện đại — dấu gạch dưới `_` có thể được dùng làm biến không tên. Tính năng này được hoàn thiện trong Java 22 qua JEP 456, vì vậy có thể sử dụng như cú pháp Java tiêu chuẩn trên JDK 22 trở lên mà không cần bật chế độ preview.

Một trường hợp hữu ích là tham số lambda mà hợp đồng của functional interface yêu cầu, nhưng phần thân lambda không cần dùng đến. Thay vì đặt một tên như `ignored` hoặc `unused`, ta có thể viết `_` để thể hiện trực tiếp ý định bỏ qua tham số đó.

Ví dụ, `Map.forEach` nhận một `BiConsumer` nên lambda phải có hai tham số: khóa và giá trị. Nếu chỉ cần khóa, có thể viết:

```java
Map<String, Integer> scores = Map.of(
    "Lan", 9,
    "Minh", 8
);

scores.forEach((student, _) ->
    System.out.println("Đã có điểm cho " + student)
);
```

`student` là khóa kiểu `String`; `_` là tham số giá trị kiểu `Integer` được cố ý bỏ qua. Lambda vẫn nhận đủ hai tham số mà `BiConsumer` quy định.

## 1. Vì sao lambda vẫn cần tham số không sử dụng?

Chữ ký của functional interface quyết định số lượng và kiểu tham số mà lambda phải nhận. Phần thân lambda có thể chỉ cần một phần trong số đó, nhưng không thể tự ý bỏ tham số khỏi danh sách.

Ví dụ, `java.util.function.BiConsumer<T, U>` có phương thức trừu tượng `accept(T, U)` nhận hai đối số. Khi truyền lambda cho API yêu cầu `BiConsumer`, lambda phải tương thích với cả hai vị trí tham số, kể cả khi chỉ sử dụng một vị trí.

Trước khi có biến không tên, lập trình viên thường đặt tên như `ignored`, `unusedValue` hoặc `notUsed`:

```java
scores.forEach((student, ignoredScore) ->
    System.out.println("Đã có điểm cho " + student)
);
```

Tên đó vẫn là một biến có thể được tham chiếu trong phần thân. Với `_`, mã nguồn thể hiện rõ rằng tham số thuộc hợp đồng của hàm, nhưng logic hiện tại không cần đến giá trị của nó.

## 2. Cú pháp `_` trong danh sách tham số lambda

Trong lambda, `_` chiếm đúng một vị trí tham số. Có thể dùng nó ở vị trí đầu, giữa hoặc cuối danh sách, tùy theo tham số nào không cần thiết:

```java
// Bỏ qua tham số thứ hai
scores.forEach((student, _) -> printStudent(student));

// Bỏ qua tham số thứ nhất
Map<String, Integer> attempts = new HashMap<>();
attempts.put("login", 2);

attempts.computeIfPresent("login",
    (_, currentCount) -> currentCount + 1
);
```

`Map.computeIfPresent` nhận một hàm có hai tham số: khóa và giá trị hiện tại. Ví dụ chỉ cần giá trị hiện tại để tính số lần thử mới, nên khóa được biểu diễn bằng `_`.

Nếu không cần dùng bất kỳ tham số nào, có thể đặt `_` ở tất cả vị trí:

```java
BiFunction<Integer, Integer, Integer> alwaysZero = (_, _) -> 0;
```

Hai dấu `_` biểu diễn hai tham số độc lập. Chúng không xung đột tên như hai biến có cùng tên thông thường, vì mỗi dấu là một biến không tên và không thể được tham chiếu trong phần thân lambda.

Với functional interface chỉ có một tham số, cú pháp vẫn giữ một vị trí tham số:

```java
Function<String, String> fallbackLabel = _ -> "Chưa phân loại";
```

Với functional interface không có tham số, lambda tiếp tục dùng danh sách rỗng `() -> ...`; không thêm `_` vì hợp đồng hàm không có tham số nào cần bỏ qua.

## 3. Kiểu tham số và hợp đồng functional interface vẫn được giữ nguyên

Kiểu của tham số `_` vẫn được xác định từ kiểu đích của lambda, giống như các tham số lambda suy luận kiểu khác. Dấu `_` chỉ bỏ tên biến khỏi mã nguồn; nó không xóa vị trí tham số và không thay đổi chữ ký của phương thức trừu tượng.

Trong ví dụ:

```java
BiConsumer<String, Integer> report = (student, _) ->
    System.out.println("Đang ghi nhận " + student);
```

Trình biên dịch vẫn kiểm tra lambda tương thích với `BiConsumer<String, Integer>`:

- Tham số thứ nhất có kiểu `String` và được đặt tên `student`.
- Tham số thứ hai có kiểu `Integer` nhưng không có tên để sử dụng trong thân lambda.
- Thân lambda vẫn phải đáp ứng kiểu kết quả `void` của `BiConsumer.accept`.

Điều này giữ nguyên hợp đồng của API đang nhận lambda. Ví dụ, không thể đổi `(student, _)` thành `(student)` khi truyền cho `Map.forEach`, vì API đó yêu cầu callback nhận cả khóa lẫn giá trị.

Việc dùng `_` cũng không làm cho đối số biến mất khỏi lời gọi callback. Bên gọi vẫn gọi hàm theo hợp đồng với đầy đủ đối số; `_` chỉ diễn tả rằng phần thân lambda không đọc tham số ở vị trí đó. Nó không phải cơ chế trì hoãn hoặc bỏ qua việc tính toán biểu thức đối số.

## 4. Kết hợp tham số có tên và không tên

Trong cùng một lambda, nên giữ tên cho những tham số có ý nghĩa với logic và dùng `_` cho các tham số không được sử dụng. Cách viết này giúp người đọc nhận ra ngay dữ liệu nào tham gia vào phép xử lý.

Ví dụ cập nhật số lần thử trong một map:

```java
Map<String, Integer> attempts = new HashMap<>();
attempts.put("login", 2);

attempts.computeIfPresent("login", (_, currentCount) -> {
    int nextCount = currentCount + 1;
    System.out.println("Số lần thử mới: " + nextCount);
    return nextCount;
});
```

Khóa không ảnh hưởng đến phép tính nên được đặt là `_`. Giá trị hiện tại cần dùng để tạo giá trị mới nên vẫn có tên `currentCount`.

Nếu sau này logic cần sử dụng một tham số từng bị bỏ qua, hãy thay `_` bằng một tên có ý nghĩa. Khi đó trình biên dịch sẽ giúp kiểm tra các chỗ tham chiếu đến biến theo quy tắc thông thường.

## 5. Những giới hạn cần nhớ

- `_` không thể được tham chiếu trong thân lambda. Chẳng hạn, `(value, _) -> use(_)` không hợp lệ vì không có biến mang tên `_` để truyền vào `use`.
- Mỗi `_` chiếm một vị trí trong danh sách tham số. Số lượng tham số vẫn phải khớp với phương thức trừu tượng của functional interface.
- Chỉ dùng `_` khi tham số thực sự không cần thiết. Nếu giá trị có vai trò trong nghiệp vụ hoặc có thể cần dùng trong logic hiện tại, hãy đặt tên mô tả.
- Dấu `_` không thay thế cho việc chọn đúng functional interface. Nếu API yêu cầu `BiFunction`, lambda vẫn phải trả về kiểu kết quả phù hợp; việc bỏ qua một tham số không thay đổi yêu cầu đó.
- Cú pháp biến không tên là tính năng ngôn ngữ được chuẩn hóa từ Java 22. Dự án cần biên dịch với source level tương ứng hoặc mới hơn để sử dụng cú pháp này.

## 6. Khi nào nên dùng?

Nên dùng tham số lambda không tên khi API cung cấp nhiều dữ liệu hơn mức logic hiện tại cần, và vị trí tham số bị bỏ qua vẫn cần thiết để khớp chữ ký callback. Các trường hợp thường gặp gồm:

- Duyệt map khi chỉ cần khóa hoặc chỉ cần giá trị.
- Cập nhật map khi hàm tính toán chỉ cần giá trị hiện tại mà không cần khóa.
- Cài đặt callback có nhiều tham số nhưng xử lý chỉ phụ thuộc vào một số tham số.
- Tạo lambda hằng, trong đó kết quả không phụ thuộc vào bất kỳ tham số đầu vào nào.

Không cần dùng `_` chỉ để rút ngắn mã. Mục đích của nó là làm rõ ý định bỏ qua dữ liệu mà vẫn giữ đúng chữ ký hàm. Nếu tên tham số giúp giải thích nghiệp vụ hoặc giúp người đọc hiểu callback, hãy tiếp tục dùng tên đó.

## Kết luận

Tham số lambda không tên `_` giúp thể hiện rõ một tham số được giữ lại vì hợp đồng của functional interface, dù phần thân lambda không cần sử dụng giá trị đó. Số lượng tham số, kiểu tham số và kiểu kết quả của lambda vẫn được kiểm tra như trước. Hãy đặt tên cho dữ liệu thực sự tham gia vào xử lý và dùng `_` cho những vị trí được cố ý bỏ qua.

## Tài liệu tham khảo

- [JEP 456: Unnamed Variables & Patterns](https://openjdk.org/jeps/456)
- [Java Language Specification, Java SE 22 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se22/html/jls-15.html#jls-15.27)
