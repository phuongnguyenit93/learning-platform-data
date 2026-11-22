# Varargs và lựa chọn phương thức nạp chồng

## 1. Vấn đề: một lời gọi có thể khớp nhiều khai báo

Nạp chồng (overloading) cho phép nhiều phương thức cùng tên nhưng khác danh sách kiểu tham số. Varargs làm một phương thức nhận được nhiều số lượng đối số, nên dễ xuất hiện lời gọi khớp nhiều khai báo.

Ví dụ minh họa:

```java
static void print(Object value) { }
static void print(String... values) { }
```

Lời gọi `print("Java")` chọn phương thức nào? Một chuỗi có thể truyền cho `Object`, đồng thời cũng có thể trở thành một phần tử của `String...`. Để trả lời đúng, phải xét **thứ tự các giai đoạn chọn phương thức**, rồi mới xét phương thức cụ thể nhất trong giai đoạn thành công.

Bài dùng Java 17+ để kiểm chứng. Những quy tắc này vẫn có hiệu lực trong Java hiện đại; không dựa vào API cũ hay hành vi riêng của Java 5.

## 2. Ba giai đoạn tìm phương thức phù hợp

Đối với các kiểu đơn giản trong bài, có thể dùng quy trình sau:

| Giai đoạn | Cách xét lời gọi | Các chuyển đổi đáng chú ý |
| --- | --- | --- |
| 1 | Số đối số cố định, chuyển đổi chặt | Trùng kiểu; mở rộng kiểu nguyên thủy; mở rộng kiểu tham chiếu |
| 2 | Số đối số cố định, chuyển đổi lỏng | Cho phép thêm đóng hộp hoặc bỏ hộp cùng các chuyển đổi được quy định |
| 3 | Lời gọi có số đối số thay đổi | Cho phép gom các đối số cuối thành mảng varargs |

Chỉ chuyển sang giai đoạn sau nếu giai đoạn trước **không tìm được phương thức phù hợp**. Khi một giai đoạn có các ứng viên phù hợp, trình biên dịch chọn phương thức cụ thể nhất trong các ứng viên của giai đoạn đó. Nếu không xác định được duy nhất phương thức tốt nhất, lời gọi có thể bị báo mơ hồ; Java không thử giai đoạn sau để “cứu” lời gọi.

“Cụ thể nhất” không có nghĩa là tự đếm số phép chuyển đổi trên tất cả khai báo. Trước hết phải xác định đúng giai đoạn. Với các ví dụ không dùng generic, `String` cụ thể hơn `Object`, `String[]` cụ thể hơn `Object[]`, và các kiểu nguyên thủy có quan hệ chuyển đổi mở rộng riêng.

### Varargs cũng có thể tham gia hai giai đoạn đầu

Khai báo:

```java
static void send(String... values) { }
```

có tham số mang kiểu `String[]`. Khi đối số đã là một `String[]` tương thích, phương thức có thể phù hợp ngay ở giai đoạn 1 như phương thức nhận một đối số mảng; không cần cơ chế gom đối số của giai đoạn 3.

Vì vậy, câu “phương thức varargs luôn được xét cuối” chưa chính xác. **Việc gom đối số theo cơ chế varargs** được xét cuối; một khai báo có dấu `...` vẫn có thể được chọn sớm khi truyền mảng trực tiếp.

## 3. Chương trình kiểm chứng đầy đủ

Lưu thành `VarargsOverloadDemo.java`:

```java
public class VarargsOverloadDemo {
    static String select(long value) {
        return "long";
    }

    static String select(Integer value) {
        return "Integer";
    }

    static String select(int... values) {
        return "int[] length=" + values.length;
    }

    static String route(Object value) {
        return "Object";
    }

    static String route(String... values) {
        return values == null
                ? "String[] null"
                : "String[] length=" + values.length;
    }

    static String boxed(Integer value) {
        return "Integer";
    }

    static String boxed(int... values) {
        return "int[]";
    }

    static String text(Object... values) {
        return "Object[]";
    }

    static String text(String... values) {
        return "String[]";
    }

    public static void main(String[] args) {
        System.out.println("primitive: " + select(7));
        System.out.println("wrapper: " + select(Integer.valueOf(7)));
        System.out.println("array: " + select(new int[] {7}));
        System.out.println("two values: " + select(7, 8));
        System.out.println("no values: " + select());

        System.out.println("one String: " + route("Java"));
        System.out.println("String array: "
                + route(new String[] {"Java"}));
        System.out.println("empty route: " + route());
        System.out.println("null element expression: "
                + route((String) null));
        System.out.println("null array expression: "
                + route((String[]) null));

        System.out.println("boxing before packing: " + boxed(7));
        System.out.println("specific varargs: " + text("Java", "SE"));
        System.out.println("specific empty varargs: " + text());

        Object value = "Java";
        System.out.println("static argument type: " + route(value));
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 VarargsOverloadDemo.java
java VarargsOverloadDemo
```

Kết quả:

```text
primitive: long
wrapper: Integer
array: int[] length=1
two values: int[] length=2
no values: int[] length=0
one String: Object
String array: String[] length=1
empty route: String[] length=0
null element expression: Object
null array expression: String[] null
boxing before packing: Integer
specific varargs: String[]
specific empty varargs: String[]
static argument type: Object
```

Các phần tiếp theo giải thích vì sao các dòng này được chọn. Các dòng gây lỗi biên dịch được tách riêng, không đưa vào chương trình chạy.

## 4. Mở rộng kiểu thắng đóng hộp khi nằm ở giai đoạn sớm hơn

Với ba khai báo `select(long)`, `select(Integer)` và `select(int...)`:

### `select(7)` chọn `select(long)`

Biểu thức `7` có kiểu `int`.

- `int → long` là mở rộng kiểu nguyên thủy, nên `select(long)` phù hợp ở giai đoạn 1.
- `int → Integer` cần đóng hộp, thuộc giai đoạn 2.
- Một `int` không phải `int[]`; để dùng `select(int...)` phải gom đối số thành mảng ở giai đoạn 3.

Giai đoạn 1 đã thành công nên trình biên dịch không so sánh hai cách còn lại.

### `select(Integer.valueOf(7))` chọn `select(Integer)`

Đối số có kiểu `Integer`, khớp trực tiếp tham số `Integer` ở giai đoạn 1. Cách bỏ hộp thành `int` rồi mở rộng thành `long` cần giai đoạn 2, nên không được xét tiếp.

### `boxed(7)` chọn `boxed(Integer)`

Trong nhóm `boxed` không có ứng viên phù hợp ở giai đoạn 1. Đóng hộp `int → Integer` làm `boxed(Integer)` phù hợp ở giai đoạn 2. Vì vậy Java không chuyển tới giai đoạn 3 để tạo mảng cho `boxed(int...)`.

Đây là lý do không nên dùng trực giác “khớp kiểu phần tử int chắc chắn tốt hơn Integer”. Phương thức nhận mảng `int[]` chưa khớp với một đối số `int` khi xét lời gọi có số đối số cố định.

## 5. Một mảng có sẵn có thể chọn phương thức varargs ngay

Lời gọi:

```java
select(new int[] {7});
```

có một đối số kiểu `int[]`. Nó khớp trực tiếp tham số mảng của `select(int...)` ở giai đoạn 1. Hai khai báo `select(long)` và `select(Integer)` không nhận được `int[]`.

Tương tự, trong nhóm `route`:

```java
route(new String[] {"Java"});
```

cả hai ứng viên đều phù hợp ở giai đoạn 1:

- Mảng `String[]` có thể được dùng như một `Object`.
- Mảng `String[]` khớp trực tiếp tham số `String[]` của khai báo `route(String...)`.

Kiểu `String[]` cụ thể hơn `Object`, nên chọn `route(String...)`. Mảng có sẵn được truyền thẳng, không bị gói thêm chỉ vì khai báo có dấu `...`.

Ngược lại:

```java
route("Java");
```

chọn `route(Object)`: một `String` mở rộng thành `Object` ở giai đoạn 1. Phương án tạo mảng `String[]` một phần tử thuộc giai đoạn 3 nên chưa tới lượt.

Cùng một tên phương thức, thay đối số từ một chuỗi thành một mảng chuỗi có thể làm đổi khai báo được chọn.

## 6. Khi chỉ cơ chế varargs mới làm lời gọi phù hợp

`select(7, 8)` có hai đối số. Các khai báo `select(long)`, `select(Integer)` và cách xem `select(int...)` như nhận một `int[]` đều không phù hợp ở hai giai đoạn đầu.

Đến giai đoạn 3, hai giá trị được gom thành một mảng `int[]` rồi truyền cho `select(int...)`.

Với `select()`, phương thức varargs cũng được chọn ở giai đoạn 3 và nhận mảng rỗng.

Nếu nhiều phương thức varargs phù hợp trong giai đoạn 3, vẫn phải chọn phương thức cụ thể nhất. Trong nhóm:

```java
static String text(Object... values) { return "Object[]"; }
static String text(String... values) { return "String[]"; }
```

`text("Java", "SE")` chọn phiên bản `String...`, vì các kiểu phần tử tương ứng là `String` và `Object`; `String` cụ thể hơn. Lời gọi `text()` cũng chọn phiên bản `String...` theo quy tắc phương thức cụ thể nhất, dù chưa có giá trị phần tử thực tế nào.

Không thể chỉ đếm số đối số rồi kết luận các phương thức varargs đều ngang nhau.

## 7. Lời gọi mơ hồ: trình biên dịch không đoán ý định

Xét đoạn mã minh họa độc lập:

```java
static void parse(String... values) { }
static void parse(Integer... values) { }
```

Những lời gọi sau gây lỗi biên dịch:

```java
// parse();
// parse(null);
```

Với `parse()`, cả hai khai báo phù hợp khi dùng varargs. `String` và `Integer` không có quan hệ kiểu con với nhau để chọn một phương thức cụ thể hơn.

Với `parse(null)`, giá trị null có thể dùng cho cả `String[]` lẫn `Integer[]` ngay khi xét lời gọi có số đối số cố định. Hai kiểu mảng cũng không cụ thể hơn nhau. Đây là tình huống mơ hồ ở giai đoạn sớm, không phải Java đang cố đoán số phần tử cần tạo.

Nếu ý định của bên gọi rõ ràng, có thể viết:

```java
parse(new String[0]);    // Chọn String..., truyền mảng rỗng.
parse((String[]) null);  // Chọn String..., truyền mảng null.
parse((String) null);    // Chọn String..., tạo mảng một phần tử null.
```

Trong lời gọi thứ ba, không phương thức nào phù hợp theo cách nhận mảng trực tiếp; tới giai đoạn varargs, biểu thức kiểu `String` có thể trở thành một phần tử của `String...` và không thể trở thành một `Integer`.

Ép kiểu nên biểu đạt đúng dữ liệu mong muốn, không chỉ để làm mất thông báo lỗi. Mảng null, mảng rỗng và mảng có một phần tử null có hợp đồng xử lý khác nhau.

### Thêm một phương thức nạp chồng có thể làm mã nguồn cũ không biên dịch

Nếu API ban đầu chỉ có `parse(String...)`, lời gọi `parse()` là hợp lệ. Thêm `parse(Integer...)` khiến chính lời gọi đó mơ hồ khi biên dịch lại.

Vì vậy, thêm khai báo nạp chồng không tự đảm bảo tương thích mã nguồn cho mọi lời gọi trước đó. Khi phát triển API, cần xem xét cả lời gọi rỗng, null và mảng có sẵn.

## 8. Kiểu tĩnh và null thường làm người đọc đoán sai

Chọn phương thức nạp chồng là công việc của trình biên dịch. Nó dựa vào các kiểu và biểu thức tại vị trí gọi, không chọn lại theo lớp thực tế của từng đối số lúc chạy.

Trong chương trình:

```java
Object value = "Java";
route(value);
```

biểu thức `value` có kiểu tĩnh là `Object`, nên chọn `route(Object)`. Việc đối tượng thực tế là một `String` không biến lời gọi đó thành một lời gọi varargs chuỗi. Với phương thức đối tượng bị ghi đè, cơ chế chọn phần triển khai lúc chạy là một vấn đề riêng; nó không làm lại bước chọn nạp chồng.

Trong nhóm `route(Object)` và `route(String...)`:

| Lời gọi | Phương thức được chọn | Lý do chính |
| --- | --- | --- |
| `route((String) null)` | `route(Object)` | Biểu thức kiểu String mở rộng thành Object ở giai đoạn 1 |
| `route((String[]) null)` | `route(String...)` | Khớp mảng ở giai đoạn 1; cụ thể hơn Object |
| `route((Object) null)` | `route(Object)` | Biểu thức chỉ có kiểu Object |
| `route()` | `route(String...)` | Chỉ phù hợp khi dùng varargs |

Đáng chú ý: `route((String) null)` không tạo mảng một phần tử null trong nhóm nạp chồng này. Phương thức `route(Object)` đã thắng ở giai đoạn 1. Ý nghĩa của cùng một cách ép kiểu phải được xét trong đúng tập khai báo.

Viết `route(null)` với đúng hai khai báo trên chọn `route(String...)` như lời gọi nhận mảng, vì `String[]` cụ thể hơn `Object`; trình biên dịch có thể cảnh báo về ý định của đối số null. Nếu muốn truyền mảng null, hãy viết rõ `(String[]) null`.

## 9. Mảng và varargs không tạo hai chữ ký khác nhau

Không được khai báo đồng thời:

```java
// static void save(String[] values) { }
// static void save(String... values) { }
```

Đây là cùng danh sách kiểu tham số, không phải hai phương thức nạp chồng hợp lệ. Thay riêng kiểu trả về cũng không làm hai khai báo trở thành một cặp nạp chồng hợp lệ.

Dấu `...` bổ sung cách gọi với số đối số thay đổi; trong thân phương thức, tham số vẫn có kiểu mảng.

## 10. Cách thiết kế và đọc mã ít gây bất ngờ

- Khi gặp một lời gọi khó đoán, viết ra kiểu tĩnh từng đối số và kiểu mảng tương ứng với tham số varargs.
- Xét lần lượt ba giai đoạn. Chỉ trong giai đoạn đầu tiên có ứng viên mới so sánh phương thức cụ thể nhất.
- Kiểm tra riêng trường hợp truyền mảng trực tiếp: nó có thể làm phương thức varargs phù hợp từ giai đoạn 1.
- Tránh tạo quá nhiều phương thức varargs cùng tên với các kiểu phần tử không có quan hệ rõ ràng. Tên riêng cho các thao tác có ý nghĩa khác nhau thường dễ dùng hơn.
- Với API public, kiểm chứng lời gọi không đối số, một đối số, nhiều đối số, mảng có sẵn, biến có kiểu rộng hơn và null trước khi thêm một phiên bản nạp chồng.
- Dùng ép kiểu khi nó thể hiện ý định dữ liệu rõ ràng. Nếu thường xuyên cần ép kiểu khó hiểu, hãy xem lại thiết kế API.

Để tự kiểm tra, hãy che phần kết quả của chương trình rồi giải thích mỗi lời gọi bằng hai thông tin: **giai đoạn thành công đầu tiên** và **lý do chọn ứng viên trong giai đoạn đó**. Nếu chỉ nhớ “fixed trước boxing trước varargs” mà bỏ qua kiểu mảng của tham số varargs, sẽ dễ kết luận sai các lời gọi truyền mảng trực tiếp.

## Tài liệu đối chiếu

- [JLS §15.12.2 — Các giai đoạn chọn phương thức và phương thức cụ thể nhất](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12.2).
- [JLS §8.4.1 và §8.4.2 — Tham số varargs và chữ ký phương thức](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.1).
