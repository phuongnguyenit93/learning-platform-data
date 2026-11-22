# Cấu trúc cú pháp Record Patterns đã hoàn thiện trong Java 21

Record Patterns cho phép kiểm tra một giá trị có thuộc một kiểu `record` hay không và lấy các thành phần của record ngay trong cùng một biểu thức mẫu. Thay vì kiểm tra kiểu, ép kiểu rồi gọi từng accessor, chương trình có thể mô tả trực tiếp cấu trúc dữ liệu cần khớp.

Tính năng này được chuẩn hóa trong Java 21 qua [JEP 440: Record Patterns](https://openjdk.org/jeps/440). Từ Java 21, có thể dùng Record Patterns trong mã nguồn chuẩn mà không cần bật preview. Record Patterns hoạt động cùng `instanceof` và các nhãn `case` của pattern matching for `switch` đã được chuẩn hóa trong [JEP 441](https://openjdk.org/jeps/441).

## 1. Cú pháp cơ bản

Một record pattern có dạng tổng quát:

```java
RecordType(pattern1, pattern2, ..., patternN)
```

- `RecordType` phải là tên một lớp `record`.
- Mỗi `pattern` tương ứng với một record component theo đúng thứ tự khai báo.
- Số lượng component pattern phải bằng số lượng record component của record.
- Component pattern có thể là type pattern, `var` pattern hoặc một record pattern lồng nhau.

Ví dụ khai báo một record hai thành phần và lấy giá trị bằng `instanceof`:

```java
record Point(int x, int y) {}

static void printPoint(Object value) {
    if (value instanceof Point(int x, int y)) {
        System.out.println("x = " + x + ", y = " + y);
    }
}
```

`Point(int x, int y)` vừa kiểm tra `value` là một `Point`, vừa lấy hai component thông qua accessor `x()` và `y()`. Các biến `x`, `y` chỉ được khởi tạo khi toàn bộ pattern khớp; chúng có thể được sử dụng trong khối `if` sau phép kiểm tra thành công.

Nếu dùng cách kiểm tra kiểu thông thường, chương trình phải lấy đối tượng `Point` rồi gọi từng accessor. Record pattern gom hai thao tác đó vào một cấu trúc cú pháp ngắn gọn hơn, đồng thời thể hiện rõ hình dạng dữ liệu mà nhánh xử lý yêu cầu.

## 2. Cách một record pattern khớp dữ liệu

Khi kiểm tra một giá trị với record pattern, Java thực hiện các bước khái quát sau:

1. Kiểm tra giá trị có thể được chuyển đổi bằng phép kiểm tra kiểu sang kiểu record trong pattern hay không.
2. Gọi accessor tương ứng để lấy giá trị của từng record component.
3. Kiểm tra từng giá trị component với pattern tương ứng. Nếu component pattern lại là record pattern, quá trình được thực hiện đệ quy.
4. Chỉ khi tất cả component pattern đều khớp, các pattern variable trong cấu trúc mới được khởi tạo và có thể được sử dụng.

Record pattern chỉ áp dụng cho lớp `record`; viết tên một lớp thông thường theo dạng `SomeClass(...)` sẽ không hợp lệ. Các component pattern phải tương thích với kiểu component tương ứng và phải khai báo đủ số lượng component.

Việc lấy component dựa trên accessor của record, không đọc trực tiếp field từ bên ngoài. Nếu record khai báo accessor tường minh, accessor đó được gọi. Nếu một accessor kết thúc bất thường do ném exception, quá trình khớp pattern kết thúc bằng `MatchException`, với nguyên nhân là exception phát sinh từ accessor.

Giá trị `null` không khớp với một record pattern ở cấp ngoài cùng. Vì vậy, đoạn sau không vào nhánh `if` khi `value` là `null`:

```java
if (value instanceof Point(int x, int y)) {
    // Chỉ chạy khi value là Point không null và các component khớp.
}
```

## 3. Dùng `var` để suy luận kiểu component

Khi kiểu component đã được khai báo trong record, có thể dùng `var` để trình biên dịch suy luận kiểu của pattern variable:

```java
record Point(int x, int y) {}

static int sum(Object value) {
    if (value instanceof Point(var x, var y)) {
        // x và y được suy luận là int.
        return x + y;
    }
    return 0;
}
```

`var` giúp tránh lặp lại kiểu component khi cấu trúc record đã cung cấp đủ thông tin. Nếu chỉ cần một component, vẫn phải viết pattern cho các component còn lại. Có thể đặt tên một biến không dùng đến, chẳng hạn `var ignored`:

```java
if (value instanceof Point(var x, var ignored)) {
    System.out.println(x);
}
```

Trong cú pháp Java 21 chuẩn, mỗi component vẫn có pattern được đặt tên như ví dụ trên.

## 4. Record Patterns lồng nhau

Một component có thể được kiểm tra bằng một record pattern khác. Nhờ đó, có thể đi sâu qua nhiều lớp dữ liệu mà không cần viết nhiều lần kiểm tra kiểu và gọi accessor.

```java
record Point(int x, int y) {}
record Rectangle(Point upperLeft, Point lowerRight) {}

static void printRectangle(Object value) {
    if (value instanceof Rectangle(
            Point(int left, int top),
            Point(int right, int bottom))) {
        System.out.println("left=" + left + ", top=" + top);
        System.out.println("right=" + right + ", bottom=" + bottom);
    }
}
```

Pattern ngoài cùng yêu cầu một `Rectangle`. Component thứ nhất phải khớp `Point` và cung cấp `left`, `top`; component thứ hai phải khớp `Point` và cung cấp `right`, `bottom`. Nếu một component lồng nhau là `null`, record pattern tương ứng không khớp và toàn bộ pattern bên ngoài cũng không khớp.

Ví dụ với dữ liệu nghiệp vụ có địa chỉ lồng trong khách hàng:

```java
record Address(String city, String country) {}
record Customer(String name, Address address) {}

static void printCustomer(Object value) {
    if (value instanceof Customer(
            String name,
            Address(String city, String country))) {
        System.out.println(name + " lives in " + city + ", " + country);
    }
}
```

Đoạn code chỉ xử lý trường hợp `value` là `Customer` và `address` là một `Address` không null. Nếu `address` có thể null và chương trình vẫn cần xử lý khách hàng đó, hãy bắt component dưới dạng `var address`, sau đó kiểm tra `address == null` trước khi truy cập các thành phần địa chỉ:

```java
if (value instanceof Customer(var name, var address)) {
    if (address == null) {
        System.out.println(name + " has no address");
    } else {
        System.out.println(name + " lives in " + address.city());
    }
}
```

## 5. Record Patterns với record generic

Record Patterns hỗ trợ record có tham số kiểu. Có thể ghi rõ type argument hoặc để trình biên dịch suy luận type argument và kiểu của pattern variable.

```java
record Box<T>(T value) {}

static void printBox(Box<String> box) {
    if (box instanceof Box<String>(String text)) {
        System.out.println(text);
    }

    if (box instanceof Box(var text)) {
        // text được suy luận là String từ kiểu Box<String>.
        System.out.println(text);
    }
}
```

Khi suy luận kiểu, trình biên dịch sử dụng kiểu của biểu thức và các ràng buộc kiểu của record. Cơ chế này cũng áp dụng cho pattern lồng nhau, ví dụ `Box(Box(var text))` khi biểu thức có kiểu `Box<Box<String>>`.

Việc kiểm tra một kiểu record generic phải an toàn về kiểu. Không thể dùng record pattern để yêu cầu một chuyển đổi không kiểm tra (unchecked conversion). Ví dụ, nếu biến có kiểu raw `Box`, pattern `Box<String>(var value)` không hợp lệ vì trình biên dịch không thể xác nhận an toàn rằng giá trị bên trong là `Box<String>`.

## 6. Dùng Record Patterns trong `switch`

Java 21 hoàn thiện pattern matching cho `switch` qua JEP 441. Có thể dùng record pattern làm nhãn `case`, kết hợp với `when` để thêm điều kiện cho một nhánh:

```java
record Point(int x, int y) {}

static String describe(Object value) {
    return switch (value) {
        case null -> "null";
        case Point(int x, int y) when x == y -> "point on diagonal";
        case Point(int x, int y) -> "Point(" + x + ", " + y + ")";
        default -> "not a point";
    };
}
```

Nhánh có `when` chỉ khớp `Point` thỏa điều kiện `x == y`. Nếu điều kiện không đúng, Java tiếp tục xét các nhãn `case` sau. Nhánh `Point(int x, int y)` tiếp theo xử lý những điểm còn lại.

Trong switch pattern, thứ tự nhánh có ý nghĩa. Pattern tổng quát có thể làm các pattern cụ thể phía sau trở thành không thể đạt tới. Ví dụ, nếu đặt `case Point p` trước `case Point(int x, int y)`, nhánh đầu đã bao phủ mọi giá trị `Point` không null nên nhánh record pattern sau bị lỗi do bị nhánh trước chi phối (dominated). Hãy đặt nhánh cụ thể trước nhánh tổng quát.

Nếu giá trị selector của `switch` là `null`, switch sẽ ném `NullPointerException` khi không có nhãn `case null`. Hãy thêm `case null` nếu logic cần xử lý giá trị null như ví dụ trên.

## 7. Phạm vi sử dụng của pattern variable

Pattern variable chỉ có hiệu lực tại nơi trình biên dịch xác định pattern đã khớp. Có thể sử dụng biến ngay trong điều kiện tiếp theo của toán tử `&&` và trong nhánh tương ứng:

```java
if (value instanceof Point(int x, int y) && x == y) {
    System.out.println("Point nằm trên đường chéo.");
}
```

Ở đây, `x` và `y` được bảo đảm đã khởi tạo khi biểu thức bên phải của `&&` được đánh giá. Nếu pattern không khớp, biểu thức bên phải không được đánh giá và khối `if` không chạy.

Không sử dụng pattern variable bên ngoài phạm vi flow-scoped mà trình biên dịch xác định. Nếu cần dùng dữ liệu sau nhánh kiểm tra, hãy gán nó vào một biến có phạm vi phù hợp bên trong nhánh đã khớp.

## 8. Lỗi thường gặp và cách tránh

| Lỗi | Vì sao xảy ra | Cách xử lý |
| --- | --- | --- |
| Dùng record pattern với một class thông thường | Record pattern yêu cầu kiểu được nêu là record class. | Chỉ dùng `RecordType(...)` với kiểu `record`; với class thông thường, dùng type pattern và gọi method phù hợp. |
| Viết thiếu hoặc thừa component pattern | Số pattern phải bằng số record component theo đúng thứ tự khai báo. | Đối chiếu khai báo `record` và cung cấp một pattern cho từng component. |
| Dùng nested record pattern khi component có thể null | `null` không khớp với nested record pattern. | Bắt component bằng `var`, kiểm tra null rồi xử lý tiếp nếu cần. |
| Dùng kiểu generic gây unchecked conversion | Kiểu biểu thức không đủ thông tin để xác nhận type argument của record pattern an toàn. | Dùng kiểu generic cụ thể đã được kiểm tra hoặc pattern có type argument phù hợp với kiểu biểu thức. |
| Đặt pattern tổng quát trước pattern cụ thể trong switch | Pattern tổng quát có thể chi phối (dominate) pattern phía sau. | Đặt nhánh cụ thể trước nhánh tổng quát và kiểm tra các điều kiện `when`. |
| Quên xử lý null trong switch | Switch pattern không tự coi record pattern là khớp với null. | Thêm `case null` nếu nghiệp vụ cần nhánh xử lý null. |
| Cố dùng pattern variable ngoài nhánh đã khớp | Pattern variable tuân theo quy tắc flow scoping. | Dùng biến trong phạm vi mà trình biên dịch bảo đảm pattern đã khớp. |

## 9. Biên dịch mã nguồn bằng Java 21

Record Patterns và pattern matching for `switch` đã là tính năng chuẩn của Java 21. Khi biên dịch mã nguồn nhắm tới Java 21, không cần bật preview:

```bash
javac --release 21 RecordPatternDemo.java
java RecordPatternDemo
```

Nếu dự án dùng Maven hoặc Gradle, cấu hình mức phát hành Java là 21 trong cấu hình compiler của dự án và bảo đảm tiến trình build chạy bằng JDK 21. Việc chỉ cài JDK 21 trên máy không tự động thay đổi `source`, `target` hoặc `release` của dự án.

## 10. Tài liệu tham khảo chính thức

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): mục tiêu thiết kế và trạng thái hoàn thiện trong Java 21.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): cách sử dụng pattern trong `switch` và các quy tắc liên quan.
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html): cú pháp, generic record patterns, suy luận kiểu và record pattern lồng nhau.
- [Java Language Specification, Java SE 21 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): quy tắc khớp pattern, khởi tạo pattern variable và hành vi khi accessor kết thúc bất thường.
- [Oracle Java 21 — Java Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html): xác nhận Record Patterns và pattern matching for `switch` là tính năng chuẩn trong Java 21.
