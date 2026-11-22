# `Arrays.toString()`, `Arrays.deepToString()` và biểu diễn thành phần lồng

Khi ghi log hoặc hiển thị một đối tượng có trường mảng, nhiều người thử `System.out.println(array)` hoặc nối mảng với chuỗi và nhận kết quả dạng `[I@4e25154f` thay vì `[1, 2, 3]`. Đó là vì mảng trong Java là **đối tượng** và bản thân lớp mảng không ghi đè `Object.toString()` để trình bày từng phần tử. API `java.util.Arrays` giải quyết hai nhu cầu khác nhau: **`Arrays.toString(...)`** biểu diễn một cấp mảng, còn **`Arrays.deepToString(Object[])`** đi sâu qua các mảng con để biểu diễn dữ liệu lồng nhau.

Mục tiêu là chọn đúng API cho mảng một chiều, mảng nhiều chiều và mảng chứa các thành phần khác kiểu, đồng thời hiểu giới hạn của chuỗi hiển thị khi viết `toString()` cho lớp tự tạo.

## 1. Vì sao in trực tiếp mảng lại thấy `[I@...`?

Đối với một object không có `toString()` riêng, dạng biểu diễn mặc định của `Object.toString()` bao gồm tên lớp, ký tự `@` và giá trị `hashCode()` dưới dạng hex. Mảng Java cũng có `toString()` mặc định kiểu này, nên:

```java
// Đoạn minh họa bên trong một method, không phải chương trình độc lập:
int[] values = {1, 2, 3};
System.out.println(values);            // Có thể thấy dạng [I@<hex>
System.out.println("" + values);       // Cũng là biểu diễn object mặc định
System.out.println(Arrays.toString(values)); // [1, 2, 3]
```

Một số tên lớp nội bộ thường gặp:

| Kiểu mảng | Tên lớp mảng dạng JVM | Phần đầu thường thấy khi in trực tiếp |
| --- | --- | --- |
| `int[]` | `[I` | `[I@...` |
| `byte[]` | `[B` | `[B@...` |
| `String[]` | `[Ljava.lang.String;` | `[Ljava.lang.String;@...` |
| `int[][]` | `[[I` | `[[I@...` |

Phần hex sau dấu `@` **không phải địa chỉ bộ nhớ** và không có bảo đảm duy nhất giữa mọi object. Nó đến từ mã băm mặc định để hiển thị và có thể thay đổi giữa những lần chạy. Không nên lưu chuỗi dạng này làm ID hay dùng để kiểm tra mảng có cùng nội dung không.

Đối với mảng một chiều chứa các giá trị có ý nghĩa, gọi `Arrays.toString(array)` tạo biểu diễn dễ đọc hơn rất nhiều. Cần `import java.util.Arrays;`.

## 2. `Arrays.toString()`: biểu diễn một cấp mảng

Lớp `Arrays` có các overload `toString` dành cho từng kiểu mảng nguyên thủy (`int[]`, `long[]`, `boolean[]`, `char[]`, `float[]`, `double[]`, `byte[]`, `short[]`) và mảng tham chiếu `Object[]`.

Ví dụ:

```java
// Đoạn minh họa trong method:
Arrays.toString(new int[]{1, 2, 3});          // "[1, 2, 3]"
Arrays.toString(new boolean[]{true, false});  // "[true, false]"
Arrays.toString(new String[]{"A", "B"});      // "[A, B]"
Arrays.toString(new int[0]);                 // "[]"
Arrays.toString((int[]) null);               // "null"
```

Cú pháp hiển thị thường dùng dấu ngoặc vuông, ngăn phần tử bằng dấu phẩy và khoảng trắng. Nếu mảng tham chiếu có phần tử `null`, nó hiển thị thành chữ `null`. Với các phần tử là object thông thường, `Arrays.toString(Object[])` lấy chuỗi biểu diễn của **từng phần tử** (theo `String.valueOf`/`toString` phù hợp), nên một lớp tự định nghĩa `toString()` sẽ ảnh hưởng trực tiếp tới kết quả.

**Nhưng `Arrays.toString` không tự đi sâu qua các mảng con.** Ví dụ `int[][] matrix = {{1, 2}, {3, 4}}` thực chất là mảng ngoài chứa hai phần tử kiểu `int[]`. Khi truyền `matrix` vào `Arrays.toString`, overload `Object[]` được chọn, rồi mỗi hàng `int[]` được trình bày bằng `toString()` mặc định:

```java
// Đoạn minh họa, phần hash hex thay đổi theo lần chạy:
int[][] matrix = {{1, 2}, {3, 4}};
System.out.println(Arrays.toString(matrix));
// Ví dụ dạng hiển thị: [[I@<hash-1>, [I@<hash-2>]
```

Đây là lý do ta có thể nhìn thấy nhiều `[I@...` bên trong cặp ngoặc vuông. `Arrays.toString(matrix)` chỉ xử lý **mảng ngoài**, không diễn giải nội dung của các mảng hàng.

## 3. `Arrays.deepToString(Object[])`: đi sâu qua mảng lồng nhau

Với mảng mà **lớp ngoài cùng là mảng tham chiếu** (`Object[]`, `String[][]`, `int[][]`, v.v.), có thể dùng `Arrays.deepToString`. Phương thức này kiểm tra mỗi phần tử: nếu phần tử là mảng, nó hiển thị nội dung mảng con bằng quy tắc thích hợp; nếu là đối tượng thông thường, nó dùng biểu diễn `toString` của đối tượng đó.

```java
// Các biểu thức minh họa đặt trong method:
int[][] matrix = {{1, 2}, {3, 4}};
String[][] groups = {{"A", "B"}, {"C"}};

Arrays.deepToString(matrix); // "[[1, 2], [3, 4]]"
Arrays.deepToString(groups); // "[[A, B], [C]]"

Object[] mixed = {"row", new int[]{7, 8},
        new Object[]{new boolean[]{true, false}, "end"}};
Arrays.deepToString(mixed);
// "[row, [7, 8], [[true, false], end]]"
```

`int[][]` hợp lệ vì mảng ngoài có các phần tử kiểu `int[]` (tham chiếu), nên bản thân `int[][]` có thể truyền cho tham số `Object[]`. Ngược lại, `int[]` đơn lẻ **không phải `Object[]`**, nên `Arrays.deepToString(new int[]{1, 2})` không biên dịch. Với mảng nguyên thủy một chiều, dùng `Arrays.toString`.

Bảng chọn nhanh:

| Dữ liệu đang có | Cách hiển thị nội dung | Điều cần tránh |
| --- | --- | --- |
| `int[]`, `byte[]`, `double[]` | `Arrays.toString(array)` | `array.toString()` hoặc `Arrays.deepToString(array)` |
| `String[]` | `Arrays.toString(array)` | In trực tiếp mảng nếu muốn thấy các chuỗi |
| `int[][]`, `double[][]` | `Arrays.deepToString(array)` | `Arrays.toString(array)` nếu muốn đọc các phần tử mảng hàng |
| `String[][]`, `Object[][]` | `Arrays.deepToString(array)` | Cho rằng hiển thị một cấp đã đầy đủ |
| `Object[]` chứa lẫn chuỗi, object và mảng | `Arrays.deepToString(array)` khi cần đi sâu qua các phần tử là mảng | Cho rằng nó tự hiểu mọi kiểu container bất kỳ |

Với dữ liệu `null`, cả `Arrays.toString((Object[]) null)` và `Arrays.deepToString((Object[]) null)` đều trả chuỗi `"null"`. Nếu phần tử của mảng là `null`, phần tử đó cũng được hiển thị `null`. Đây là chuỗi biểu diễn, **không phải một tham chiếu Java `null` được trả về**.

## 4. Ví dụ Java 17+ đầy đủ và đầu ra xác định

Tạo tệp **`ArrayRenderingDemo.java`**:

```java
import java.util.Arrays;

public class ArrayRenderingDemo {
    record Part(String name, int quantity) {}

    public static void main(String[] args) {
        int[] scores = {8, 9, 10};
        String[] tags = {"java", null, "core"};
        int[][] matrix = {{1, 2}, {3, 4}};
        Object[] nested = {
                "header",
                new int[]{7, 8},
                new Object[]{"deep", new boolean[]{true, false}},
                null
        };

        System.out.println("scores: " + Arrays.toString(scores));
        System.out.println("tags: " + Arrays.toString(tags));
        System.out.println("empty: " + Arrays.toString(new int[0]));
        System.out.println("null array: "
                + Arrays.toString((int[]) null));

        System.out.println("matrix deep: "
                + Arrays.deepToString(matrix));
        System.out.println("nested deep: "
                + Arrays.deepToString(nested));
        System.out.println("matrix shallow contains row identity: "
                + Arrays.toString(matrix).contains("[I@"));
        System.out.println("nested shallow contains primitive identity: "
                + Arrays.toString(nested).contains("[I@"));

        Object[] parts = {
                new Part("bolt", 2),
                new int[]{5, 6}
        };
        System.out.println("record and array: "
                + Arrays.deepToString(parts));

        Object[] selfReference = new Object[1];
        selfReference[0] = selfReference;
        System.out.println("cycle has marker: "
                + Arrays.deepToString(selfReference).contains("..."));
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp bằng JDK 17 trở lên:

```bash
javac ArrayRenderingDemo.java
java ArrayRenderingDemo
```

Kết quả:

```text
scores: [8, 9, 10]
tags: [java, null, core]
empty: []
null array: null
matrix deep: [[1, 2], [3, 4]]
nested deep: [header, [7, 8], [deep, [true, false]], null]
matrix shallow contains row identity: true
nested shallow contains primitive identity: true
record and array: [Part[name=bolt, quantity=2], [5, 6]]
cycle has marker: true
```

Ý nghĩa:

1. `scores` và `tags` là mảng một chiều nên `Arrays.toString` đã đủ; phần tử `null` được hiển thị an toàn.
2. `matrix` là mảng hai chiều. `deepToString` hiển thị tất cả phần tử của từng hàng; `toString` một cấp vẫn để lộ dạng định danh mặc định của các hàng `int[]`. Chương trình chỉ in kết quả kiểm tra `contains("[I@")` để **không phụ thuộc những chữ số hash không ổn định**.
3. `nested` chứa nhiều loại phần tử, kể cả mảng nguyên thủy nằm trong một `Object[]` khác. `deepToString` diễn giải đúng cấu trúc các mảng lồng nhau.
4. `Part` là record, nên `toString` được Java sinh theo tên record và các component. Khi một phần tử không phải mảng, `deepToString` sử dụng cách phần tử đó tự biểu diễn; nó không tự phản chiếu từng trường của mọi lớp.
5. `selfReference` là mảng chứa tham chiếu về chính nó. `deepToString` nhận diện chu trình mảng và dùng dấu rút gọn (có `...`) thay vì đệ quy không ngừng. Đây là cơ chế dành cho cấu trúc mảng tham chiếu lồng nhau.

Đừng dùng chính chuỗi in ra làm bằng chứng về tính bằng nhau của hai đối tượng: hai đối tượng khác nhau có thể được `toString` biểu diễn giống nhau, và kết quả `toString` cũng có thể thay đổi khi trạng thái thay đổi.

## 5. Giới hạn khi thành phần lồng không phải mảng

`Arrays.deepToString` duyệt sâu **các cấp mảng**, chứ không phải mọi loại cấu trúc dữ liệu trong Java. Nếu một phần tử của `Object[]` là `List<int[]>`, `Map<String,int[]>` hoặc một POJO chứa mảng, `deepToString` sẽ gọi `toString` của `List`, `Map` hoặc POJO đó; nó **không tự duyệt xuyên các lớp này để đến mảng con**.

Ví dụ ý tưởng (không phải chương trình độc lập):

```java
Object[] data = {
        java.util.List.of(new int[]{1, 2})
};
String rendered = Arrays.deepToString(data);
// List.toString() được dùng ở cấp phần tử List;
// không thể mặc định kỳ vọng nội dung mảng bên trong List là "[1, 2]".
```

Vì vậy, khi xây dựng biểu diễn `toString` cho đối tượng nhiều cấp, hãy quyết định rõ **lớp nào sở hữu trách nhiệm trình bày**. Lớp chứa mảng có thể tự dùng `Arrays.toString`/`deepToString` trong `toString` của mình. Cấu trúc `Map` hay `List` có thể cần ánh xạ thành phần thành chuỗi rõ ràng trước khi hiển thị.

Với đối tượng nghiệp vụ:

```java
// Chỉ minh họa phần thân của phương thức toString trong một lớp có các field:
@Override
public String toString() {
    return "Report[scores=" + Arrays.toString(scores)
            + ", matrix=" + Arrays.deepToString(matrix) + "]";
}
```

Phần minh họa giả định trường `scores` có kiểu `int[]` và `matrix` có kiểu `int[][]`, không phải chương trình độc lập. Cách này tạo chuỗi dễ đọc hơn so với nối trực tiếp `scores` hoặc `matrix`.

Một lưu ý khác: một object thường có thể có `toString` tự triển khai, bao gồm hiệu ứng phụ, chi phí truy xuất lớn hoặc lỗi nếu trạng thái không hợp lệ. `deepToString` **không kiểm soát hành vi của các `toString` thành phần**. Log biểu diễn toàn bộ cấu trúc chỉ nên được dùng khi dữ liệu thực sự an toàn và chi phí có thể chấp nhận.

## 6. `deepToString` và mảng tự tham chiếu

Mảng tham chiếu `Object[]` có thể chứa chính nó hoặc tạo một chuỗi tham chiếu vòng:

```java
// Đoạn minh họa:
Object[] a = new Object[1];
a[0] = a;
String text = Arrays.deepToString(a);
```

Nếu một thuật toán đi sâu qua mảng mà không theo dõi mảng đã gặp trên nhánh duyệt, nó sẽ gọi lại chính mình mãi và gây `StackOverflowError`. `Arrays.deepToString` có cơ chế phát hiện chu trình trong các mảng đối tượng, dùng ký hiệu `[[...]]` cho mảng bị gặp lại trong chu trình, nhờ vậy tránh đệ quy vô hạn **đối với vòng được tạo qua các mảng**.

Tuy nhiên:

- Cơ chế này không có nghĩa `Arrays.deepToString` là một công cụ tuần tự hóa *object graph* tổng quát, bao gồm mọi loại chu trình qua POJO, collection và map.
- Chuỗi hiển thị có thể lặp lại nội dung của một mảng con được tham chiếu từ nhiều nơi nhưng **không tạo vòng đệ quy hiện tại**. Do đó, không thể đọc chuỗi như một sơ đồ bảo toàn danh tính tham chiếu.
- Với dữ liệu lồng sâu hoặc kích thước lớn, dựng cả chuỗi có thể tốn bộ nhớ và CPU; cần cân nhắc giới hạn độ sâu hoặc kích thước của log ở tầng ứng dụng.

Cơ chế xử lý vòng chủ yếu nhằm giúp biểu diễn mảng để chẩn đoán; nó không thay thế thiết kế dữ liệu và không phải định dạng trao đổi dữ liệu ổn định.

## 7. Chuỗi trình bày khác với so sánh nội dung và mã băm

`Arrays.toString`/`deepToString` chỉ tạo **chuỗi văn bản**. Chúng không quyết định đối tượng bằng nhau hay không và không cấp ID duy nhất:

| Mục đích | Mảng một chiều | Mảng lồng nhau |
| --- | --- | --- |
| **Biểu diễn để đọc** | `Arrays.toString(a)` | `Arrays.deepToString(a)` |
| **So sánh nội dung** | `Arrays.equals(a,b)` | `Arrays.deepEquals(a,b)` |
| **Băm theo nội dung** | `Arrays.hashCode(a)` | `Arrays.deepHashCode(a)` |

Ba dòng này thường đi cùng nhau trong một value object có trường mảng, nhưng có chức năng riêng biệt. Nếu lớp tự viết cài đặt `equals` theo nội dung mảng và `hashCode` tương ứng, `toString` có thể hiển thị bằng API cùng mức sâu để giúp debug. Dù vậy, chuỗi hiển thị giống nhau **không tạo ra bảo đảm hợp đồng `equals`**: `toString` của một lớp có thể cố ý bỏ thông tin hoặc rút gọn.

Ví dụ hai mảng sau có thể hiển thị giống nhau trong một ngữ cảnh nhưng không đại diện cùng cấu trúc có kiểu chính xác:

```java
// Ví dụ minh họa:
String[] withComma = {"a, b", "c"};
String[] separate = {"a", "b", "c"};
// Arrays.toString(withComma) -> "[a, b, c]"
// Arrays.toString(separate)  -> "[a, b, c]"
// Arrays.equals(withComma, separate) -> false
```

Đặc biệt, `Arrays.toString` không tự escape hoặc quote đầy đủ nội dung chuỗi, nên **không phải một serialization format để parse ngược đáng tin cậy**. Dấu phân cách xuất hiện bên trong giá trị có thể khiến bản hiển thị mơ hồ.

## 8. Khi nào cần JSON hoặc cấu trúc có schema?

Nếu cần gửi dữ liệu qua API, ghi tệp cấu hình, lưu cơ sở dữ liệu hay cần một định dạng mà máy khác parse ngược chính xác, hãy dùng một thư viện serialization được duy trì (ví dụ Jackson JSON trong ứng dụng phù hợp) cùng cấu trúc/schema rõ ràng. Không dùng `Arrays.deepToString` thay thế JSON hay giao thức truyền thông:

- Không có hệ thống escaping/quoting như JSON để bảo toàn mọi chuỗi.
- Không mang đủ thông tin kiểu Java, nullability và danh tính đối tượng cho mọi trường hợp.
- Không có hợp đồng định dạng ổn định cho các lớp tự viết `toString`.
- Không thiết kế để đại diện chu trình, chia sẻ tham chiếu hoặc các collection lồng nhau dưới dạng có thể giải mã ngược.
- Có thể lộ các trường nhạy cảm nếu cứ in cả object để ghi log.

Nếu mục tiêu chỉ là nhìn nhanh một mảng ở console hoặc trong log debug an toàn, `Arrays.toString` và `deepToString` là lựa chọn hợp lý vì gọn và sẵn có trong JDK. Nếu mục tiêu là **dữ liệu có cấu trúc, tái sử dụng được**, hãy thiết kế serialization riêng.

## 9. Những lỗi phổ biến và cách tự kiểm tra

1. **`System.out.println(intArray)` rồi tưởng thấy nội dung:** thực tế thường thấy `[I@...`; dùng `Arrays.toString(intArray)`.
2. **`Arrays.toString(intMatrix)` rồi tưởng in hết hàng:** mảng con `int[]` vẫn in mặc định; dùng `Arrays.deepToString(intMatrix)`.
3. **Dùng `Arrays.deepToString(intArray)` cho `int[]` một chiều:** sai kiểu, không biên dịch vì phương thức nhận `Object[]`; dùng `Arrays.toString`.
4. **Nghĩ `deepToString` đi sâu qua mọi `List`, `Map`, POJO:** nó chỉ đi sâu qua mảng. Cần xử lý biểu diễn các container khác bằng API/thiết kế tương ứng.
5. **Nghĩ biểu diễn `[I@<hex>` là địa chỉ RAM hoặc ID bất biến:** đó là biểu diễn `Object.toString` dựa trên hash, không bảo đảm như vậy.
6. **Dùng chuỗi `Arrays.toString` như dữ liệu máy có thể parse lại:** ký tự phân cách và kiểu phần tử có thể mơ hồ; dùng định dạng có schema như JSON nếu cần trao đổi hoặc lưu trữ.
7. **Ghi log mảng mật khẩu, token hoặc dữ liệu cá nhân:** nội dung của mảng có thể xuất hiện trọn vẹn; chọn lọc/che thông tin nhạy cảm trước khi ghi.
8. **Để `toString` đệ quy thủ công không kiểm soát trên object graph có vòng:** `Arrays.deepToString` có xử lý vòng qua mảng, nhưng không bảo vệ mọi chu trình do code `toString` tùy biến tạo ra.
9. **Gán ý nghĩa “bằng nhau” từ `toString`:** hai đối tượng in giống nhau vẫn có thể khác theo `equals`; dùng phép so sánh thích hợp.
10. **Dựng chuỗi cho một mảng rất lớn mỗi lần xử lý:** trong code hiệu năng cao, chỉ tạo biểu diễn khi cần chẩn đoán; cân nhắc giới hạn phần tử và tránh log ở mức quá chi tiết.

### Checklist

- Đối tượng cần in là **mảng nguyên thủy một chiều**, mảng tham chiếu một chiều hay mảng nhiều chiều?
- Đã chọn đúng overload `Arrays.toString` hoặc `Arrays.deepToString` chưa?
- Trong mảng có chứa các mảng con, `List`, `Map` hoặc POJO cần biểu diễn riêng không?
- Có khả năng vòng tham chiếu, dữ liệu quá sâu/quá lớn hoặc `toString` của phần tử có tác dụng phụ không?
- Chuỗi dùng để **debug cho người đọc** hay để **truyền/lưu dữ liệu có thể parse**?
- Nội dung có chứa bí mật hoặc dữ liệu nhạy cảm cần che trước khi ghi log không?

**Ghi nhớ:** dùng **`Arrays.toString` cho mảng một chiều**, dùng **`Arrays.deepToString` khi có các cấp mảng lồng nhau với mảng ngoài là mảng tham chiếu**. Hai API này giúp in dữ liệu dễ hiểu, nhưng không biến chuỗi hiển thị thành danh tính đối tượng, phép so sánh `equals` hay định dạng serialization đáng tin cậy.
