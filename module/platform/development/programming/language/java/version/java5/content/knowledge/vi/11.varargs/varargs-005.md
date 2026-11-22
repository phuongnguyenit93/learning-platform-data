# Truyền một mảng có sẵn vào phương thức varargs

## 1. Mảng và varargs có quan hệ gì?

Varargs cho phép một phương thức nhận số lượng đối số thay đổi ở tham số cuối. Với khai báo `sum(int... values)`, kiểu của `values` trong thân phương thức là `int[]`. Vì vậy, ngoài cách gọi `sum(10, 20, 30)`, ta có thể truyền một mảng tương thích đã tồn tại:

```java
int[] scores = {10, 20, 30};
int total = sum(scores);
```

Đây là cách dùng vẫn có giá trị trong Java hiện đại: dữ liệu thường đã được thu thập vào mảng, và không cần lấy từng phần tử ra để gọi một API varargs. Các ví dụ trong bài dùng cú pháp thông thường, chạy được trên Java 17+.

Có hai hình thức cần phân biệt:

| Cách gọi với `int... values` | Mảng mà phương thức nhận |
| --- | --- |
| `sum(10, 20, 30)` | Mảng do cơ chế varargs tạo để chứa các đối số |
| `sum(scores)` với `scores` là `int[]` | Chính đối tượng mảng mà `scores` đang tham chiếu |
| `sum()` | Mảng rỗng được tạo cho lời gọi không có đối số |
| `sum(new int[0])` | Mảng rỗng được tạo tường minh trong biểu thức gọi |

Khi truyền mảng tương thích, Java không tự sao chép mảng hoặc gói thêm một mảng bên ngoài cho tham số đó. Về việc áp dụng lời gọi, phương thức varargs có thể được gọi như một phương thức có số lượng đối số cố định, nhận tham số mảng. Đây không phải cơ chế “trải mảng” tổng quát như một số ngôn ngữ khác.

## 2. Ví dụ chạy đầy đủ

Lưu chương trình sau thành `ExistingArrayVarargs.java`:

```java
import java.util.Arrays;

public class ExistingArrayVarargs {
    static int sum(int... values) {
        int total = 0;
        for (int value : values) {
            total += value;
        }
        return total;
    }

    static boolean receivesSameArray(int[] expected, int... actual) {
        return expected == actual;
    }

    static void increaseFirst(int... values) {
        if (values.length > 0) {
            values[0]++;
        }
    }

    static void replaceLocalReference(int... values) {
        values = new int[] {999};
    }

    static void inspect(String label, Object... values) {
        System.out.println(label + ": length=" + values.length
                + ", firstType="
                + values[0].getClass().getSimpleName());
    }

    static String describe(String... values) {
        if (values == null) {
            return "null array";
        }
        return "length=" + values.length + ", values="
                + Arrays.toString(values);
    }

    public static void main(String[] args) {
        int[] numbers = {10, 20, 30};

        System.out.println("array sum=" + sum(numbers));
        System.out.println("separate sum=" + sum(10, 20, 30));
        System.out.println("same array="
                + receivesSameArray(numbers, numbers));

        increaseFirst(numbers);
        System.out.println("after mutation="
                + Arrays.toString(numbers));

        replaceLocalReference(numbers);
        System.out.println("after local rebind="
                + Arrays.toString(numbers));

        System.out.println("empty sum=" + sum(new int[0]));

        String[] words = {"Java", "array"};
        inspect("reference array", (Object[]) words);
        inspect("single array object", (Object) words);
        inspect("primitive array", numbers);

        System.out.println(describe((String[]) null));
        System.out.println(describe((String) null));
        System.out.println(describe());
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 ExistingArrayVarargs.java
java ExistingArrayVarargs
```

Kết quả:

```text
array sum=60
separate sum=60
same array=true
after mutation=[11, 20, 30]
after local rebind=[11, 20, 30]
empty sum=0
reference array: length=2, firstType=String
single array object: length=1, firstType=String[]
primitive array: length=1, firstType=int[]
null array
length=1, values=[null]
length=0, values=[]
```

Phương thức `receivesSameArray` dùng `==` để kiểm tra hai tham chiếu có trỏ tới cùng đối tượng mảng hay không. Kết quả `true` chứng minh lời gọi đang chuyển cùng mảng tới tham số varargs; việc tổng bằng nhau đơn thuần chưa chứng minh được điều đó.

## 3. Mảng có sẵn được truyền như thế nào?

Xét:

```java
static void send(String prefix, String... messages) {
    for (String message : messages) {
        System.out.println(prefix + message);
    }
}
```

Đoạn mã minh họa lời gọi bên trong một phương thức:

```java
String[] messages = {"created", "saved"};
send("INFO: ", messages);
```

`prefix` nhận chuỗi `"INFO: "`; `messages` trong `send` nhận tham chiếu tới mảng có sẵn. Mảng chỉ thay thế phần tham số varargs ở cuối, không thay thế các tham số đứng trước nó.

Nếu gọi:

```java
send("INFO: ", "created", "saved");
```

thì có thể hình dung phần đối số cuối được gom thành `new String[] {"created", "saved"}`. Cách hình dung này giải thích hành vi; không cần tự viết mảng khi API đã cung cấp varargs.

Một phương thức `send(String, String...)` không thể đồng thời được khai báo thêm phiên bản `send(String, String[])` trong cùng lớp với cùng tên và phần còn lại của chữ ký. Dấu `...` không tạo ra một kiểu tham số khác với kiểu mảng tương ứng.

## 4. Chia sẻ mảng: sửa phần tử khác với gán lại tham số

Java luôn truyền đối số theo giá trị. Với mảng, giá trị được sao chép sang tham số là giá trị tham chiếu, không phải toàn bộ các phần tử.

Sau lời gọi `increaseFirst(numbers)`, biến `numbers` bên ngoài và tham số `values` bên trong đều trỏ tới cùng một mảng. Vì vậy, `values[0]++` sửa phần tử của mảng dùng chung; bên gọi thấy `[11, 20, 30]`.

Trong `replaceLocalReference`, câu lệnh `values = new int[] {999}` chỉ đổi tham chiếu lưu trong biến tham số. Nó không gán lại biến `numbers` của bên gọi, nên mảng bên ngoài vẫn là `[11, 20, 30]`.

Nếu không muốn phương thức có khả năng sửa trực tiếp mảng ban đầu, có thể truyền bản sao:

```java
int[] original = {1, 2, 3};
increaseFirst(original.clone());
// original vẫn chứa 1, 2, 3.
```

Với mảng đối tượng, `clone()` là sao chép nông: mảng ngoài là mảng mới nhưng các phần tử tham chiếu vẫn có thể cùng trỏ tới các đối tượng cũ. Bản sao mảng không tự bảo vệ trạng thái của đối tượng có thể thay đổi bên trong.

Khi thiết kế API varargs, nên ghi rõ phương thức chỉ đọc, sửa phần tử hay giữ tham chiếu mảng để dùng sau. Tính thuận tiện của cú pháp không tạo ra cam kết bất biến hoặc độc lập dữ liệu.

## 5. Kiểu mảng quyết định cách truyền

### 5.1. Mảng nguyên thủy phải khớp loại phần tử

Với `sum(int... values)`:

```java
int[] values = {1, 2, 3};
int result = sum(values); // Hợp lệ.
```

Các dòng sau chỉ minh họa lỗi biên dịch, không đưa vào chương trình chạy:

```java
// sum(new long[] {1L, 2L});
// sum(new Integer[] {1, 2});
// sum(new short[] {1, 2});
```

Java có thể mở rộng một đối số `short` riêng lẻ thành `int` hoặc bỏ hộp một `Integer` riêng lẻ. Nhưng nó không tự biến toàn bộ `short[]` thành `int[]`, cũng không tự bỏ hộp từng phần tử của `Integer[]` để tạo `int[]`.

Nếu cần chuyển đổi, phải tạo mảng đích và chuyển từng phần tử một cách tường minh. Đừng suy từ quy tắc chuyển đổi một giá trị sang quy tắc chuyển đổi cả mảng.

### 5.2. Mảng tham chiếu và `Object...`

Mảng tham chiếu có tính tương thích theo kiểu phần tử: `String[]` có thể được dùng ở nơi cần `Object[]`. Trong chương trình đầy đủ:

```java
inspect("reference array", (Object[]) words);
```

tham số `Object...` nhận chính mảng `String[]`, với hai phần tử là hai chuỗi. Ép kiểu `(Object[])` thể hiện rõ ý định truyền mảng làm danh sách đối số; không tạo bản sao.

Ngược lại:

```java
inspect("single array object", (Object) words);
```

khiến biểu thức đối số có kiểu `Object`. Java tạo mảng `Object[]` một phần tử để truyền theo cơ chế varargs; phần tử duy nhất đó là đối tượng mảng `words`. Kết quả độ dài là `1`, không phải `2`.

Với `int[]`, tình huống tự nhiên đã khác:

```java
inspect("primitive array", numbers);
```

Một `int[]` là một `Object`, nhưng không phải `Object[]`. Do đó lời gọi trên tạo `Object[]` một phần tử chứa cả `int[]`; nó không tự trải các số nguyên và không tự đóng hộp từng số.

| Đối số vào `Object... values` | Số phần tử trong `values` | Ý nghĩa |
| --- | --- | --- |
| `(Object[]) words` | `words.length` | Dùng mảng tham chiếu có sẵn |
| `(Object) words` | `1` | Dùng cả mảng như một đối tượng |
| `numbers`, kiểu `int[]` | `1` | Dùng cả mảng nguyên thủy như một đối tượng |

Các ví dụ này giả định chỉ có phương thức `inspect(String, Object...)` như trên; một tập phương thức nạp chồng khác có thể làm thay đổi lựa chọn lời gọi.

### 5.3. Không thể trộn “một phần tử” và “một mảng để trải”

Với `String... messages`, lời gọi sau không hợp lệ:

```java
// send("INFO: ", "created", messages);
```

Khi phần varargs có nhiều đối số rời, mỗi đối số phải tương thích với kiểu phần tử `String`. Biến `messages` có kiểu `String[]`, không phải `String`. Muốn thêm một phần tử vào danh sách mảng, hãy tạo mảng kết hợp trước rồi truyền mảng kết quả.

## 6. Mảng rỗng, mảng null và một phần tử null

Ba trạng thái khác nhau:

```java
describe();                 // Mảng rỗng, length = 0.
describe(new String[0]);     // Mảng rỗng được tạo tường minh.
describe((String[]) null);  // Tham số mảng bằng null.
describe((String) null);    // Mảng length = 1, phần tử duy nhất bằng null.
```

Một biến `String[] data = null;` truyền vào `describe(data)` cũng chuyển mảng null tới phương thức. Cơ chế varargs không tự đổi nó thành mảng rỗng. Nếu thân phương thức truy cập `values.length` mà không kiểm tra, nó sẽ gây `NullPointerException`.

Trong trường hợp chỉ có `describe(String...)`, viết `describe(null)` được hiểu là truyền mảng null và có thể sinh cảnh báo của trình biên dịch về lời gọi varargs. Ép kiểu rõ như trên giúp phân biệt ý định. Nếu có nhiều phương thức nạp chồng nhận các kiểu tham chiếu khác nhau, đối số `null` còn có thể làm lời gọi mơ hồ.

Quyết định có chấp nhận mảng null hay không là hợp đồng API. Ví dụ `sum` trong bài yêu cầu mảng khác null; nó không có chính sách tự coi null là tổng bằng 0. Ngược lại, `describe` chủ động xử lý null để minh họa ba trường hợp.

## 7. Lưu ý khi phương thức ghi vào mảng tham chiếu

Truyền `String[]` cho `Object...` không thay đổi kiểu thực lúc chạy của mảng thành `Object[]`. Đoạn mã minh họa:

```java
static void replaceFirst(Object... values) {
    values[0] = Integer.valueOf(42);
}

// Bên trong một phương thức:
// String[] names = {"An"};
// replaceFirst((Object[]) names);
```

Lời gọi được chú thích ở trên biên dịch được nhưng khi thực hiện sẽ ném `ArrayStoreException`: đối tượng mảng thực vẫn là `String[]` và không thể chứa `Integer`. Kiểu khai báo `Object...` cho phép viết câu lệnh gán trong thân phương thức; kiểm tra kiểu của đối tượng mảng lúc chạy vẫn được giữ nguyên.

Vì vậy, với API nhận `Object...` để đọc dữ liệu, tránh tùy tiện dùng mảng đối số làm nơi chứa kết quả thuộc kiểu khác. Nếu cần bộ nhớ độc lập có kiểu thực là `Object[]`, hãy tạo đúng loại mảng đó trước khi ghi.

## 8. Thực hành và tự kiểm tra

1. Thay `sum(new int[0])` bằng `sum()`. Kết quả vẫn bằng `0`; khác biệt nằm ở cách tạo mảng đối số.
2. Thay `increaseFirst(numbers)` bằng `increaseFirst(numbers.clone())`. Mảng `numbers` sẽ không bị sửa; ở chương trình đầy đủ nó giữ `[10, 20, 30]`.
3. Với `String[] words = {"a", "b", "c"}`, dự đoán độ dài trong `inspect` khi truyền `(Object[]) words` và `(Object) words`: lần lượt là `3` và `1`.
4. Giải thích vì sao `sum(new Integer[] {1, 2})` không hợp lệ dù `sum(Integer.valueOf(1), Integer.valueOf(2))` hợp lệ: chuyển đổi từng đối số rời khác với chuyển đổi một đối tượng mảng.
5. Trước khi truyền mảng có sẵn vào API varargs, kiểm tra kiểu mảng, chính sách null và khả năng phương thức sửa hoặc lưu giữ mảng. Đây là những yếu tố quyết định tính đúng đắn của lời gọi.

## Tài liệu đối chiếu

- [JLS §8.4.1 — Tham số hình thức và tham số varargs](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.1).
- [JLS §15.12.2 và §15.12.4.2 — Chọn phương thức và đánh giá đối số](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12.4.2).
- [JLS §10.5 — Kiểm tra khi ghi phần tử mảng](https://docs.oracle.com/javase/specs/jls/se25/html/jls-10.html#jls-10.5).
