# Cơ chế đóng gói đối số thành mảng

Varargs cho phép người gọi truyền số lượng đối số thay đổi, nhưng thân phương thức vẫn xử lý một mảng có kiểu xác định. Hiểu điểm này giúp dự đoán chính xác độ dài mảng, trường hợp không truyền phần tử, việc dùng lại mảng có sẵn và tác động khi sửa phần tử.

## 1. Từ lời gọi thuận tiện đến một tham số mảng

Xét phương thức sau; đây là đoạn minh họa đặt bên trong một lớp:

```java
static int sum(int... values) {
    int total = 0;
    for (int value : values) {
        total += value;
    }
    return total;
}
```

Bên trong `sum`, `values` có kiểu `int[]`: có thể đọc `length`, truy cập chỉ số hoặc duyệt bằng vòng lặp. Nó không phải danh sách và cũng không phải một nhóm tham số vô danh.

Các lời gọi minh họa tương ứng:

```java
sum();          // Tương đương sum(new int[] {})
sum(7);         // Tương đương sum(new int[] {7})
sum(7, 8, 9);   // Tương đương sum(new int[] {7, 8, 9})
```

Cụm “tương đương” mô tả cách hiểu ngữ nghĩa của lời gọi. Không cần giả định trình biên dịch thật sự tạo một tệp mã nguồn trung gian.

Dấu `...` cung cấp cú pháp thuận tiện ở nơi gọi. Sau khi đối số được chuẩn bị, phương thức nhận một giá trị tham chiếu đến mảng, giống cách truyền tham số mảng thông thường. Varargs vẫn là tính năng đang được dùng trong Java hiện hành.

## 2. Phần nào được đóng gói?

Nếu phương thức có tham số cố định đứng trước, chỉ nhóm đối số dành cho tham số varargs được đưa vào mảng. Varargs phải là tham số cuối cùng và mỗi phương thức chỉ có tối đa một tham số như vậy.

```java
static void log(String label, int... values) {
    System.out.println(label + ": " + java.util.Arrays.toString(values));
}

// Các lời gọi minh họa:
log("empty");
log("scores", 10, 20);
```

Với lời gọi thứ hai:

| Thành phần ở nơi gọi | Tham số nhận | Giá trị nhận |
| --- | --- | --- |
| `"scores"` | `label` | Chuỗi `"scores"` |
| `10, 20` | `values` | Mảng `int[]` chứa `10, 20` |

Có thể hình dung lời gọi là `log("scores", new int[] {10, 20})`. Không truyền phần tử nào cho varargs tạo mảng rỗng, không tự tạo `null`. Ngược lại, `log()` không hợp lệ vì vẫn thiếu tham số bắt buộc `label`.

Cần phân biệt “đóng gói vào mảng” với tự động đóng hộp (autoboxing). Với `int...`, các phần tử nằm trong `int[]`; không cần đổi chúng thành `Integer`. Với `Integer...`, truyền các literal `int` có thể cần đóng hộp để tạo phần tử `Integer`. Hai cơ chế này có thể cùng xuất hiện nhưng không phải một.

## 3. Truyền mảng có sẵn: không tự sao chép

Một phương thức varargs cũng có thể được gọi như phương thức nhận mảng thông thường:

```java
int[] source = {7, 8, 9};
int total = sum(source);
```

Ở đây, `source` đã phù hợp với tham số `int[]`. Lời gọi truyền chính giá trị tham chiếu đó; không tạo thêm một lớp mảng và không tự sao chép các phần tử.

Có hai tình huống cần tách rõ:

- `sum(7, 8, 9)`: ngữ nghĩa lời gọi tạo mảng để chứa ba giá trị.
- `sum(source)`: truyền mảng đã có theo cách gọi với số lượng tham số cố định.

Do đó, nhận định “cứ gọi varargs là luôn tạo mảng mới” không đúng. Nếu phải phân tích hiệu năng, cần xem hình thức gọi và đo trong bối cảnh thực tế; cơ chế tối ưu của JVM cũng có thể ảnh hưởng chi phí quan sát được.

### Hệ quả với quyền thay đổi dữ liệu

Java truyền tham số theo giá trị. Với mảng, giá trị được sao chép là tham chiếu, không phải toàn bộ mảng.

Nếu phương thức sửa `values[0]`, người gọi giữ cùng mảng sẽ nhìn thấy thay đổi. Nếu phương thức chỉ gán `values = new int[] {...}`, nó thay đổi biến tham số cục bộ và không làm biến mảng của người gọi trỏ sang mảng khác.

Đây là hành vi mảng thông thường, không phải cơ chế riêng của varargs. Nếu API cần bảo vệ dữ liệu đầu vào, có thể sao chép rõ ràng bằng `values.clone()` trước khi sửa. Với mảng chứa đối tượng, sao chép mảng chỉ sao chép các tham chiếu phần tử, không tự sao chép sâu các đối tượng.

## 4. Chương trình kiểm chứng hoàn chỉnh

Lưu nguyên chương trình sau vào `VarargsPackingDemo.java`. Chương trình dùng cú pháp tương thích Java 17+.

```java
import java.util.Arrays;

public class VarargsPackingDemo {
    static void show(String label, int... values) {
        System.out.println(label + ": " + Arrays.toString(values));
    }

    static int mark(int value) {
        System.out.println("evaluate " + value);
        return value;
    }

    static void changeFirst(int... values) {
        values[0] = 99;
    }

    static void replaceParameter(int... values) {
        values = new int[] {5, 6};
        System.out.println("local: " + Arrays.toString(values));
    }

    static void inspect(String label, String... values) {
        if (values == null) {
            System.out.println(label + ": null array");
        } else {
            System.out.println(label + ": length=" + values.length
                    + ", values=" + Arrays.toString(values));
        }
    }

    static void countObjects(String label, Object... values) {
        System.out.println(label + ": " + values.length);
    }

    public static void main(String[] args) {
        show("empty");
        show("one", 7);
        show("many", 7, 8, 9);

        show("ordered", mark(1), mark(2));

        int[] source = {10, 20};
        show("before", source);
        changeFirst(source);
        show("after mutation", source);
        replaceParameter(source);
        show("after reassignment", source);

        inspect("no elements");
        inspect("null array", (String[]) null);
        inspect("one null", (String) null);

        int[] primitives = {1, 2};
        Integer[] wrappers = {1, 2};
        countObjects("int array", primitives);
        countObjects("Integer array", wrappers);
        countObjects("array as one object", (Object) wrappers);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac -encoding UTF-8 VarargsPackingDemo.java
java VarargsPackingDemo
```

Lệnh `javac` có thể phát cảnh báo `non-varargs call of varargs method with inexact argument type for last parameter` tại lời gọi truyền trực tiếp `Integer[]` vào `Object...`. Đây là cảnh báo biên dịch, không phải lỗi và không thuộc stdout của chương trình. Trong ví dụ, chủ đích là dùng mảng đó làm toàn bộ mảng tham số; viết `(Object[]) wrappers` sẽ làm rõ chủ đích và loại bỏ cảnh báo này. Ép thành `(Object) wrappers` lại tạo ý nghĩa khác như dòng kế tiếp minh họa.

Stdout:

```text
empty: []
one: [7]
many: [7, 8, 9]
evaluate 1
evaluate 2
ordered: [1, 2]
before: [10, 20]
after mutation: [99, 20]
local: [5, 6]
after reassignment: [99, 20]
no elements: length=0, values=[]
null array: null array
one null: length=1, values=[null]
int array: 1
Integer array: 2
array as one object: 1
```

### Đọc kết quả theo từng hiện tượng

`show("empty")` nhận mảng dài 0. Nó có thể duyệt mảng an toàn mà không cần một phần tử đặc biệt đại diện cho “không có dữ liệu”.

Với `show("ordered", mark(1), mark(2))`, các biểu thức đối số được đánh giá từ trái sang phải. Hai dòng `evaluate` xuất hiện trước khi thân `show` in mảng. Nếu một biểu thức đối số ném ngoại lệ, việc đánh giá lời gọi dừng ở đó: các đối số phía sau chưa được đánh giá và thân phương thức chưa chạy.

Sau `changeFirst(source)`, mảng mà người gọi đang giữ thành `[99, 20]`. Sau `replaceParameter(source)`, mảng ấy vẫn như vậy; dòng `local: [5, 6]` chỉ phản ánh mảng được biến tham số cục bộ trỏ tới.

Các ví dụ `null` và `Object...` cần xem riêng dưới đây vì kiểu của biểu thức ở nơi gọi ảnh hưởng trực tiếp đến cách chuẩn bị mảng.

## 5. Mảng rỗng, mảng null và một phần tử null

Với khai báo `inspect(String label, String... values)`:

| Lời gọi | Thứ phương thức nhận |
| --- | --- |
| `inspect("x")` | Một mảng `String[]` dài 0 |
| `inspect("x", (String[]) null)` | Tham chiếu mảng bằng `null` |
| `inspect("x", (String) null)` | Một mảng dài 1, phần tử duy nhất bằng `null` |

Ép kiểu trong bảng giúp thể hiện chủ đích của người gọi:

- `(String[]) null` phù hợp với toàn bộ tham số mảng.
- `(String) null` là một đối số phần tử, nên lời gọi cần đóng gói nó vào mảng.

Với đúng khai báo này và không có overload cạnh tranh, `inspect("x", null)` có thể truyền mảng `null`; trình biên dịch có thể cảnh báo về ý định gọi varargs. Nên viết ép kiểu rõ ràng để người đọc nhận ra trường hợp mong muốn.

Phương thức không tự được bảo vệ khỏi `NullPointerException`. Đọc `values.length` khi `values == null` vẫn gây lỗi. API cần quy định mảng `null` có được chấp nhận hay bị từ chối, và xử lý thống nhất. Chương trình trên kiểm tra `null` để quan sát sự khác biệt, không ngầm biến mọi dữ liệu lỗi thành mảng rỗng.

## 6. Vì sao int[] là một phần tử của Object...?

`Object...` có kiểu tham số `Object[]`. Tuy nhiên:

- `int[]` là một đối tượng nhưng không phải `Object[]`. Khi truyền nó vào `Object...`, lời gọi tạo mảng `Object[]` dài 1 chứa chính mảng `int[]`.
- `Integer[]` có thể được dùng như `Object[]`. Khi truyền trực tiếp, nó được dùng làm mảng tham số; hai phần tử được nhìn thấy là hai đối tượng `Integer`.
- Ép `Integer[]` thành `Object` buộc cách hiểu “một phần tử”: lời gọi tạo mảng ngoài chứa mảng ban đầu.

Varargs không tự trải (spread) một mảng nguyên thủy thành các đối tượng đóng hộp. Ví dụ `countObjects("x", new int[] {1, 2})` không tương đương `countObjects("x", 1, 2)`.

Tương tự, một collection không tự được biến thành các phần tử varargs. Nếu phương thức nhận `String...` mà dữ liệu nằm trong `List<String>`, hãy chuyển tường minh thành `String[]` khi thực sự cần gọi API đó; không giả định dấu `...` tự duyệt collection.

## 7. Lỗi thường gặp và cách áp dụng

| Nhầm lẫn | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Không truyền phần tử nghĩa là mảng null | Thêm nhánh xử lý sai hoặc dự đoán sai kết quả | Nhớ rằng cách gọi bỏ trống tạo mảng dài 0 |
| Truyền mảng có sẵn sẽ được sao chép | Phương thức vô tình sửa dữ liệu của người gọi | Tránh sửa hoặc tạo bản sao rõ ràng |
| Gán lại biến tham số làm đổi biến của người gọi | Tưởng rằng dữ liệu phía ngoài đã bị thay thế | Phân biệt sửa đối tượng và gán lại tham chiếu cục bộ |
| `Object...` tự trải mọi kiểu mảng | Đếm sai phần tử hoặc xử lý nhầm kiểu | Kiểm tra kiểu mảng, đặc biệt `int[]` |
| Đọc phần tử đầu tiên mà không kiểm tra độ dài | Lỗi khi lời gọi không có đối số varargs | Kiểm tra `length` hoặc quy định số phần tử tối thiểu |
| Dùng varargs để né hợp đồng dữ liệu rõ ràng | Người gọi không biết chấp nhận rỗng/null hay dữ liệu có bị sửa | Ghi rõ hợp đồng API |

Không thể khai báo đồng thời `m(int[] values)` và `m(int... values)` trong cùng lớp chỉ để phân biệt “mảng” với “nhiều đối số”: hai khai báo có cùng chữ ký phương thức. Một phương thức varargs đã hỗ trợ cả hai cách gọi.

Nếu xử lý dữ liệu thường xuyên đã nằm trong collection, thiết kế API nhận collection có thể diễn đạt nhu cầu tốt hơn. Varargs phù hợp khi muốn người gọi thuận tiện liệt kê một nhóm giá trị; nó không thay thế mọi dạng dữ liệu đầu vào.

## 8. Tự kiểm tra

1. Với `sum(int... values)`, `sum()` nhận mảng dài bao nhiêu?
2. Nếu gọi `changeFirst(new int[] {3, 4})`, có mảng nào được tạo chỉ để đóng gói thêm lần nữa không?
3. Tại sao `countObjects("x", new int[] {3, 4})` in 1?
4. Muốn truyền một phần tử `null` vào `String...`, nên viết thế nào?
5. Nếu một biểu thức đối số ném ngoại lệ, thân phương thức đã bắt đầu chạy chưa?

Đáp án:

1. Dài 0.
2. Không cần mảng đóng gói ngoài; biểu thức `new int[]` tự tạo mảng đầu vào, rồi tham chiếu của nó được truyền trực tiếp.
3. `int[]` không phù hợp với `Object[]`, nhưng phù hợp như một phần tử `Object`; mảng varargs ngoài dài 1.
4. Dùng `(String) null` tại vị trí đối số phần tử, hoặc truyền tường minh `new String[] {null}`.
5. Chưa; lời gọi dừng trong lúc đánh giá đối số.

## Tài liệu đối chiếu

Cú pháp tham số và cách tạo mảng đối số được quy định tại [JLS 21 §8.4.1 — Formal Parameters](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.1) và [JLS 21 §15.12.4.2 — Evaluate Arguments](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12.4.2).
