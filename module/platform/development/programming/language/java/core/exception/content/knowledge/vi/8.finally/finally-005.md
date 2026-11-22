# Thay đổi đối tượng trả về khác thay đổi biến cục bộ như thế nào trong `finally`?

## 1. Mục tiêu học tập

Trong Java, câu lệnh `return` trong khối `try` và khối `finally` có một thứ tự thực thi rất quan trọng: **biểu thức `return` được đánh giá trước, rồi `finally` chạy, sau đó phương thức mới hoàn tất trả về** nếu `finally` hoàn thành bình thường.

Điều này dẫn đến hai kết quả tưởng như mâu thuẫn:

- Nếu `try` chuẩn bị trả về một **giá trị nguyên thủy** hoặc một **tham chiếu được giữ trong biến cục bộ**, việc gán lại biến cục bộ trong `finally` không làm thay đổi giá trị đã được chuẩn bị để trả về.
- Nếu `try` chuẩn bị trả về **tham chiếu tới một đối tượng có thể thay đổi**, `finally` có thể sửa **trạng thái của chính đối tượng ấy**. Bên gọi nhận cùng đối tượng và quan sát trạng thái đã được sửa.

Bài này giúp bạn nắm chắc sự khác nhau giữa **giá trị biến**, **giá trị tham chiếu**, **đối tượng được tham chiếu**, và **giá trị của biểu thức `return`**; dự đoán đầu ra chương trình; nhận biết trường hợp `return` hoặc `throw` trong `finally` ghi đè kết quả trước đó; và thiết kế mã xử lý ngoại lệ không gây bất ngờ.

Ví dụ dùng Java 17+; các tệp có `main`, lệnh `javac`/`java` và `stdout` bên dưới là chương trình độc lập.

## 2. Thứ tự thực thi của `return` và `finally`

Xét cấu trúc:

```java
static int compute() {
    int result = 10;
    try {
        return result;
    } finally {
        result = 20;
    }
}
```

Đây là một phương thức minh họa. Một cách hiểu sai phổ biến là “`finally` chạy sau `return` nên việc gán `result = 20` sẽ đổi kết quả trả về thành 20”. Java **không** hoạt động như vậy.

Theo Java Language Specification (JLS `14.17 và `14.20.2), khi thực hiện `return expression;`:

1. Java đánh giá `expression`. Ở đây biểu thức là biến `result` đang mang giá trị `10`.
2. Kết quả đánh giá được lưu như **giá trị sắp trả về** cho lời gọi hiện tại.
3. Khi rời `try`, `finally` liên quan được thực thi.
4. Nếu `finally` hoàn thành bình thường, phương thức thực hiện việc trả **giá trị đã được chuẩn bị ở bước 2**.
5. Nếu `finally` tự hoàn thành đột ngột (chẳng hạn `throw` hoặc `return` riêng), lý do thoát mới **thay thế** lý do thoát đang chờ; kết quả cũ có thể không còn được trả về.

Do đó, trong ví dụ trên `compute()` trả về **10**, dù biến cục bộ mang giá trị 20 khi `finally` kết thúc.

Sơ đồ thời gian:

```text
result = 10
    |
    v
try: đánh giá return result
    |
    +--> giá trị trả về dự kiến = 10
    |
    v
finally: result = 20
    |
    v
finally kết thúc bình thường
    |
    v
bên gọi nhận 10
```

Điểm cốt lõi là **biểu thức `return` đã được đánh giá**, chứ phương thức chưa hoàn tất rời stack. Khi `finally` thay đổi biến, nó đang làm việc với biến cục bộ, không viết lại bản sao giá trị đã được tính cho lệnh trả về.

## 3. Giá trị nguyên thủy: thay đổi biến không đổi kết quả `return`

Tạo tệp **`PrimitiveFinallyDemo.java`**:

```java
public class PrimitiveFinallyDemo {
    static int number() {
        int value = 10;
        try {
            return value;
        } finally {
            value = 99;
            System.out.println("finally value=" + value);
        }
    }

    public static void main(String[] args) {
        System.out.println("returned=" + number());
    }
}
```

Biên dịch và chạy:

```bash
javac PrimitiveFinallyDemo.java
java PrimitiveFinallyDemo
```

Kết quả `stdout` chính xác:

```text
finally value=99
returned=10
```

Giải thích:

- `value` là biến cục bộ kiểu `int`, ban đầu bằng 10.
- Khi gặp `return value`, Java đánh giá và chuẩn bị trả về số 10.
- Khối `finally` vẫn chạy và thay đổi biến thành 99; vì thế dòng đầu in 99.
- Khi `finally` kết thúc bình thường, phương thức trả lại 10 cho lời gọi ở `main`.
- Không tồn tại một “liên kết sống” giữa kết quả trả về kiểu `int` và biến cục bộ `value` sau thời điểm đánh giá `return`.

Các kiểu nguyên thủy khác (`long`, `double`, `boolean`, ...) cũng theo nguyên tắc đánh giá biểu thức trả về trước khi xử lý `finally`.

### Đừng nhầm `return value` với `return 99` nằm trong `finally`

Hai đoạn sau có ý nghĩa khác nhau:

```java
// A: gán lại biến, KHÔNG tạo một return mới.
try {
    return value;
} finally {
    value = 99;
}
```

```java
// B: chính finally có return khác, thay thế return cũ.
try {
    return value;
} finally {
    return 99;
}
```

Đây là hai **mảnh mã minh họa** bên trong phương thức trả về `int`. A trả giá trị đã được đánh giá ở `try`. B trả `99` do câu lệnh `return` **của `finally`**, không phải vì việc gán lại biến. Viết `return` trong `finally` có thể che lỗi và thường là thực hành nên tránh; phần 9 phân tích kỹ hơn.

## 4. Tham chiếu đối tượng: Java vẫn truyền/trả về **giá trị**

Với đối tượng Java, biến cục bộ kiểu tham chiếu chứa **giá trị tham chiếu** đến đối tượng, không chứa chính toàn bộ đối tượng trong biến theo kiểu sao chép khi `return`.

Xem tình huống:

```java
StringBuilder text = new StringBuilder("A");
try {
    return text;
} finally {
    text.append("B");
}
```

Đây là mảnh mã đặt trong phương thức trả về `StringBuilder`. Khi đánh giá `return text`, Java chuẩn bị trả **giá trị tham chiếu** đến đối tượng `StringBuilder` hiện tại. Sau đó `finally` dùng cùng tham chiếu để gọi `append("B")`, làm **thay đổi trạng thái của đối tượng** từ `"A"` thành `"AB"`.

Bên gọi nhận tham chiếu đã được chuẩn bị trước đó, nhưng đối tượng đằng sau tham chiếu đã bị thay đổi. Vì vậy bên gọi thấy `"AB"`.

So sánh với trường hợp:

```java
StringBuilder text = new StringBuilder("A");
try {
    return text;
} finally {
    text = new StringBuilder("B");
}
```

Ở đây `finally` **gán biến `text` sang đối tượng mới**. Nó không sửa đối tượng cũ. Giá trị tham chiếu của biểu thức `return text` đã được giữ trước khi gán lại, nên bên gọi vẫn nhận đối tượng cũ chứa `"A"`.

Vì thế cần phân biệt:

| Hành động trong `finally` | Cái gì thay đổi? | Đối tượng mà `return` ban đầu đã tham chiếu |
| --- | --- | --- |
| `text.append("B")` | Trạng thái của đối tượng hiện tại | **Bị thay đổi**, bên gọi có thể thấy `"AB"` |
| `text = new StringBuilder("B")` | Biến cục bộ `text` trỏ tới đối tượng khác | **Không bị thay đổi** bởi phép gán này |
| `text = null` | Biến cục bộ nhận `null` | Đối tượng cũ vẫn là đối tượng sắp trả về |
| `text.append("B"); text = new StringBuilder("C");` | Đối tượng cũ bị sửa rồi biến trỏ nơi khác | Bên gọi nhận đối tượng cũ đã chứa `"AB"` |
| `text.delete(0, text.length())` | Nội dung của đối tượng cũ | Bên gọi thấy đối tượng cũ đã bị xóa nội dung |

Đây là khác biệt **mutation (sửa trạng thái của đối tượng)** và **reassignment/rebinding (gán lại biến tham chiếu)**.

## 5. Chương trình chạy được: đối chiếu mutation và reassignment

Tạo tệp **`ReferenceFinallyDemo.java`**:

```java
public class ReferenceFinallyDemo {
    static StringBuilder mutated() {
        StringBuilder text = new StringBuilder("A");
        try {
            return text;
        } finally {
            text.append("B");
        }
    }

    static StringBuilder reassigned() {
        StringBuilder text = new StringBuilder("A");
        try {
            return text;
        } finally {
            text = new StringBuilder("B");
        }
    }

    static StringBuilder both() {
        StringBuilder text = new StringBuilder("A");
        try {
            return text;
        } finally {
            text.append("!");
            text = new StringBuilder("C");
        }
    }

    static StringBuilder assignedNull() {
        StringBuilder text = new StringBuilder("A");
        try {
            return text;
        } finally {
            text = null;
        }
    }

    public static void main(String[] args) {
        System.out.println("mutated=" + mutated());
        System.out.println("reassigned=" + reassigned());
        System.out.println("both=" + both());
        System.out.println("assignedNull=" + assignedNull());
    }
}
```

```bash
javac ReferenceFinallyDemo.java
java ReferenceFinallyDemo
```

Kết quả `stdout`:

```text
mutated=AB
reassigned=A
both=A!
assignedNull=A
```

Diễn giải:

- `mutated()`: biểu thức `return` giữ tham chiếu đến đối tượng A; `finally` sửa **chính đối tượng đó** thành AB.
- `reassigned()`: biểu thức `return` đã giữ tham chiếu đến đối tượng A; `finally` chỉ đổi biến cục bộ sang đối tượng B.
- `both()`: đối tượng A nhận thêm `!` trước khi biến được gán sang C; bên gọi nhận A!.
- `assignedNull()`: biến cục bộ thành `null` nhưng giá trị tham chiếu đã chuẩn bị để trả vẫn chỉ đến đối tượng A; bên gọi nhận đối tượng không null.

Lưu ý `StringBuilder` là mutable (có thể thay đổi). `System.out.println("..." + someStringBuilder)` sử dụng nội dung hiện thời của đối tượng để tạo chuỗi hiển thị; đó là lý do dòng in phản ánh các thay đổi trong `finally`.

### Một quy tắc đủ để dự đoán cả bốn kết quả

**Giá trị tham chiếu được đánh giá khi gặp `return`; đối tượng được tham chiếu có thể tiếp tục bị thay đổi trước khi phương thức thực sự trả về.** Việc gán lại biến cục bộ không thay thế giá trị tham chiếu đã được chuẩn bị.

## 6. Đối tượng do người lập trình định nghĩa và aliasing

Không chỉ `StringBuilder` mới có hành vi này. Mọi đối tượng có trạng thái mutable đều có thể bị sửa trong `finally` và cho bên gọi quan sát.

Tạo tệp **`HolderFinallyDemo.java`**:

```java
public class HolderFinallyDemo {
    static class Holder {
        int count;

        Holder(int count) {
            this.count = count;
        }
    }

    static Holder create() {
        Holder holder = new Holder(1);
        try {
            return holder;
        } finally {
            holder.count = 2;
        }
    }

    public static void main(String[] args) {
        Holder result = create();
        System.out.println("count=" + result.count);
    }
}
```

```bash
javac HolderFinallyDemo.java
java HolderFinallyDemo
```

`stdout`:

```text
count=2
```

`result` trỏ đến đúng đối tượng `Holder` mà biến cục bộ `holder` đã trỏ tới khi `return` được đánh giá. `finally` sửa trường `count` trên cùng đối tượng đó thành 2.

Khái niệm *aliasing* là có nhiều tham chiếu trỏ đến cùng một đối tượng. Thay đổi trạng thái qua bất kỳ tham chiếu hợp lệ nào sẽ làm thay đổi đối tượng, nên các tham chiếu khác có thể quan sát thay đổi (trong phạm vi các quy tắc đồng bộ/visibility thích hợp nếu có nhiều luồng).

### Phân biệt “sửa đối tượng” và “đổi một tham chiếu khác”

```java
Holder first = new Holder(1);
Holder alias = first;
alias.count = 2;          // Sửa cùng một đối tượng; first.count cũng là 2.
alias = new Holder(99);   // Chỉ đổi biến alias, first vẫn trỏ tới đối tượng cũ.
```

Đây là đoạn mã minh họa, giả định lớp `Holder` ở ví dụ trên. Tương tự, trong `finally`, biến đang được gán lại là một ô lưu giá trị tham chiếu riêng; nó không tự cập nhật giá trị trả về đã được đánh giá.

## 7. Mảng và collection: nội dung thay đổi, tham chiếu đã giữ vẫn như cũ

Mảng Java là đối tượng có thể thay đổi phần tử. Xét:

```java
static int[] values() {
    int[] data = {1, 2};
    try {
        return data;
    } finally {
        data[0] = 99;
    }
}
```

Đây là mảnh phương thức minh họa. Bên gọi nhận **cùng mảng** sau khi phần tử đầu đã được sửa thành 99. Không có một bản sao mảng tự động nào phát sinh vì `return data`.

Chương trình đầy đủ **`ArrayFinallyDemo.java`**:

```java
import java.util.Arrays;

public class ArrayFinallyDemo {
    static int[] create() {
        int[] values = {1, 2, 3};
        try {
            return values;
        } finally {
            values[0] = 7;
            values = new int[] {9, 9, 9};
        }
    }

    public static void main(String[] args) {
        System.out.println(Arrays.toString(create()));
    }
}
```

```bash
javac ArrayFinallyDemo.java
java ArrayFinallyDemo
```

Kết quả:

```text
[7, 2, 3]
```

Dòng `values[0] = 7` sửa mảng được chuẩn bị trả về. Dòng `values = new int[] {9, 9, 9}` chỉ gán biến `values` sang một mảng mới nên không thay thế mảng trả về.

Điều tương tự áp dụng cho collection mutable như `ArrayList`:

```java
static java.util.List<String> createList() {
    java.util.List<String> items = new java.util.ArrayList<>();
    try {
        return items;
    } finally {
        items.add("added in finally");
    }
}
```

Đây là mảnh phương thức minh họa. Nếu hoàn thành bình thường, bên gọi nhận danh sách có phần tử `"added in finally"`. Tuy nhiên, đừng dùng `finally` như một chỗ “âm thầm bổ sung dữ liệu trước khi trả về”; điều đó khiến hợp đồng phương thức khó đọc và dễ gây nhầm lẫn.

## 8. Đối tượng immutable: gán lại biến không sửa đối tượng đã trả

`String` trong Java là immutable: không có thao tác nào sửa nội dung của đối tượng `String` hiện có. Biểu thức `text + "B"` tạo ra một giá trị chuỗi mới (hoặc được runtime tối ưu theo cách vẫn giữ ngữ nghĩa immutable), rồi gán giá trị tham chiếu mới cho biến `text`.

Tạo **`ImmutableFinallyDemo.java`**:

```java
public class ImmutableFinallyDemo {
    static String text() {
        String value = "A";
        try {
            return value;
        } finally {
            value = value + "B";
        }
    }

    public static void main(String[] args) {
        System.out.println(text());
    }
}
```

```bash
javac ImmutableFinallyDemo.java
java ImmutableFinallyDemo
```

`stdout`:

```text
A
```

Cơ chế giống `reassigned()`: `try` đã chuẩn bị trả tham chiếu đến chuỗi `"A"`. Trong `finally`, phép nối chuỗi tạo nội dung mới và gán biến cục bộ `value`, không làm đối tượng chuỗi `"A"` thay đổi.

Lưu ý: “trả về đối tượng” không tự đồng nghĩa “bên gọi sẽ thấy nội dung thay đổi”. Phải xét **đối tượng có mutable hay không** và `finally` thực sự làm gì.

Các kiểu bao như `Integer`, `Long` cũng là immutable. Nếu `finally` gán `number = number + 1` cho một biến `Integer`, đó là thao tác tính/gán lại giá trị tham chiếu của biến, không sửa đối tượng `Integer` đã được chuẩn bị trả về.

## 9. `finally` tự `return` hoặc `throw`: ngoại lệ quan trọng

Cho đến lúc này, các ví dụ đều có `finally` **hoàn thành bình thường**. Khi `finally` tự `return` hoặc ném ngoại lệ, Java áp dụng quy tắc ưu tiên lý do hoàn thành đột ngột mới: `finally` có thể **thay thế** kết quả hoặc ngoại lệ đang chờ.

### 9.1. `return` trong `finally` ghi đè kết quả cũ

Tạo tệp **`FinallyReturnOverrideDemo.java`**:

```java
public class FinallyReturnOverrideDemo {
    static int value() {
        try {
            return 10;
        } finally {
            return 20;
        }
    }

    public static void main(String[] args) {
        System.out.println(value());
    }
}
```

```bash
javac FinallyReturnOverrideDemo.java
java FinallyReturnOverrideDemo
```

Kết quả:

```text
20
```

`return 10` đã được đánh giá, nhưng `finally` tự thực hiện `return 20`. Đây là **câu lệnh trả về khác** làm thay thế kết quả đang chờ. Không được lẫn với việc chỉ thay đổi biến cục bộ như `value = 20` trong `finally`.

### 9.2. `return` trong `finally` còn có thể che khuất ngoại lệ

Tạo tệp **`FinallySwallowDemo.java`**:

```java
public class FinallySwallowDemo {
    static int risky() {
        try {
            throw new IllegalStateException("original failure");
        } finally {
            return 42;
        }
    }

    public static void main(String[] args) {
        System.out.println(risky());
    }
}
```

```bash
javac FinallySwallowDemo.java
java FinallySwallowDemo
```

`stdout`:

```text
42
```

Ngoại lệ `IllegalStateException` được ném trong `try`, nhưng `finally` trả 42 nên lý do kết thúc mới thay thế ngoại lệ đang lan truyền. Trình biên dịch Java chấp nhận cấu trúc này, nhưng nó **che mất lỗi** và thường gây khó chẩn đoán.

**Khuyến nghị:** không viết `return`, `break` hay `continue` để chuyển hướng luồng thực thi ra khỏi `finally` khi đang xử lý tài nguyên/ngoại lệ; để khối `finally` chuyên thực hiện dọn dẹp cần thiết.

### 9.3. `finally` ném ngoại lệ mới cũng có thể ghi đè kết quả cũ

Ví dụ mảnh mã:

```java
static String read() {
    try {
        return "ready";
    } finally {
        throw new IllegalStateException("cleanup failed");
    }
}
```

Khi gọi `read()`, lời gọi không trả `"ready"`; nó kết thúc bằng `IllegalStateException("cleanup failed")`. Quy tắc này cũng áp dụng khi `try` đã ném ngoại lệ khác: một ngoại lệ mới từ `finally` có thể che nguyên nhân ban đầu.

Đây là lý do việc dọn dẹp trong `finally` cần được thiết kế cẩn thận. Với tài nguyên triển khai `AutoCloseable`, `try-with-resources` có cơ chế quản lý lỗi đóng tài nguyên bằng **suppressed exceptions**; đừng tự giả định rằng một `finally` thủ công cũng tự động lưu ngoại lệ ban đầu dưới dạng suppressed.

## 10. Thời điểm đánh giá biểu thức trả về và các side effect

Không chỉ `return variable;`, Java còn đánh giá các biểu thức phức tạp **trước khi chạy `finally`**. Ví dụ:

```java
static int next() {
    int count = 1;
    try {
        return count++;
    } finally {
        count += 10;
    }
}
```

Đây là mảnh phương thức. `count++` trả về **giá trị cũ 1** cho biểu thức, đồng thời tăng biến thành 2. Sau đó `finally` tăng biến thành 12. Giá trị trả về vẫn là **1**.

Nếu dùng `return ++count;`, biểu thức sẽ tạo kết quả là 2 trước khi `finally` chạy, vì toán tử tiền tố tăng rồi trả giá trị mới.

### Ví dụ chạy được: kiểm tra thứ tự in

Tạo tệp **`ReturnEvaluationOrderDemo.java`**:

```java
public class ReturnEvaluationOrderDemo {
    static StringBuilder make() {
        System.out.println("evaluate return expression");
        return new StringBuilder("created");
    }

    static StringBuilder produce() {
        try {
            return make();
        } finally {
            System.out.println("execute finally");
        }
    }

    public static void main(String[] args) {
        StringBuilder result = produce();
        System.out.println("caller sees: " + result);
    }
}
```

```bash
javac ReturnEvaluationOrderDemo.java
java ReturnEvaluationOrderDemo
```

Kết quả:

```text
evaluate return expression
execute finally
caller sees: created
```

Từ kết quả có thể rút ra: phương thức `make()` được gọi và cho kết quả **trước khi** `finally` của `produce()` chạy; chỉ sau đó `main` mới nhận đối tượng.

Nếu việc đánh giá **chính biểu thức trả về** ném ngoại lệ (ví dụ `return make();` nhưng `make()` ném lỗi), không có giá trị trả về được tạo ra. `finally` liên quan vẫn được xử lý theo quy tắc thoát đột ngột, rồi ngoại lệ tiếp tục lan truyền nếu `finally` hoàn thành bình thường.

## 11. `finally`, đồng bộ hóa và aliasing: các giới hạn thực tế

### 11.1. Quan sát đối tượng sau khi nhận khác với dữ liệu snapshot

Khi API cần **snapshot bất biến**, bạn không nên vô tình trả đối tượng mutable rồi sửa nó trong `finally`. Ví dụ một phương thức trả về `List` mà `finally` còn thêm/xóa phần tử sẽ tạo kết quả khó đoán cho người đọc. Một lựa chọn dễ hiểu là hoàn tất các thay đổi **trước khi `return`**, sau đó trả giá trị hoàn chỉnh hoặc snapshot phù hợp.

Dùng `List.copyOf(items)` có thể tạo danh sách không sửa đổi được ở tầng container, nhưng đó không nhất thiết là *deep copy* của các đối tượng phần tử mutable. Việc chọn snapshot và ranh giới sao chép phụ thuộc hợp đồng dữ liệu.

### 11.2. Không phải mọi sửa đổi đối tượng đều có nghĩa mọi luồng nhìn thấy ngay

Trong các ví dụ đơn luồng của bài, bên gọi thực hiện tiếp sau khi `finally` chạy nên quan sát thay đổi xác định. Với nhiều luồng cùng truy cập đối tượng mutable, cần xem thêm Java Memory Model: đồng bộ hóa, `volatile`, khóa hoặc cấu trúc concurrent thích hợp. Việc sửa một trường trong `finally` **không tự tạo ra** bảo đảm visibility cho mọi luồng không đồng bộ.

### 11.3. `finally` không phải hệ thống giao dịch

Sửa đối tượng rồi ném ngoại lệ có thể để trạng thái đã thay đổi. Java **không tự rollback** các thay đổi đối tượng chỉ vì khối `try` có lỗi. Nếu một bất biến dữ liệu quan trọng, hãy thiết kế bước chuẩn bị, xác thực và commit rõ ràng hoặc dùng cơ chế transaction phù hợp.

### 11.4. Tránh cố thao tác quá nhiều trong `finally`

Mục đích điển hình của `finally` là dọn dẹp tài nguyên cần thiết khi rời phạm vi, như nhả một tài nguyên không được quản lý tự động. Trong mã hiện đại, ưu tiên `try-with-resources` cho `AutoCloseable`. Trộn việc chỉnh sửa giá trị kết quả vào `finally` gây bất ngờ và khiến API khó bảo trì.

## 12. Bảng đối chiếu nhanh

| Biểu thức trong `try` | Thao tác trong `finally` | Kết quả nếu `finally` hoàn thành bình thường |
| --- | --- | --- |
| `int x = 1; return x;` | `x = 9;` | Trả **1** |
| `int x = 1; return x++;` | `x = 9;` | Trả **1** (hậu tố trả giá trị cũ) |
| `int x = 1; return ++x;` | `x = 9;` | Trả **2** |
| `String s = "A"; return s;` | `s = "B";` | Trả `"A"` |
| `StringBuilder b = new StringBuilder("A"); return b;` | `b.append("B");` | Trả cùng đối tượng hiện chứa `"AB"` |
| `StringBuilder b = new StringBuilder("A"); return b;` | `b = new StringBuilder("B");` | Trả đối tượng chứa `"A"` |
| `int[] a = {1}; return a;` | `a[0] = 7;` | Trả mảng có phần tử đầu **7** |
| `Holder h = new Holder(1); return h;` | `h.count = 2;` | Trả `Holder` có `count == 2` |
| `return 1;` | `return 2;` | Trả **2**, vì `finally` có lệnh return riêng |
| `return 1;` | `throw new IllegalStateException();` | **Ném ngoại lệ**, không trả số |

Bảng ghi kết quả theo Java 17 và giả định thao tác bên trong không có lỗi mới ngoài những trường hợp đã nêu. Các đoạn viết gọn ở cột `try`/`finally` dùng để so sánh ý nghĩa, không phải từng tệp Java độc lập.

## 13. Các lỗi hiểu nhầm phổ biến

**“`finally` chạy sau `return` nên thay đổi biến trong `finally` sẽ luôn cập nhật giá trị trả về.”** Sai. Biểu thức `return` đã được đánh giá và giá trị dự kiến đã được lưu trước khi `finally` bắt đầu.

**“`finally` chạy nên không thể ảnh hưởng đối tượng đang trả về.”** Sai. Nếu `finally` dùng một tham chiếu tới **cùng đối tượng mutable** để sửa nội dung, bên gọi có thể nhận đối tượng đã bị sửa.

**“Gán biến tham chiếu sang đối tượng mới giống như sửa đối tượng cũ.”** Sai. Gán lại biến đổi **giá trị tham chiếu trong biến**; nó không thay đổi đối tượng mà giá trị trả về đã trỏ tới.

**“`text = null` trong `finally` khiến phương thức trả `null`.”** Không đúng nếu `return text` đã đánh giá trước đó với tham chiếu không null và `finally` hoàn thành bình thường.

**“`String` và `StringBuilder` thay đổi giống nhau.”** Sai. `String` immutable; `StringBuilder` mutable. Phép `String.concat` hay `+` không sửa đối tượng `String` gốc.

**“Tham số, biến cục bộ và giá trị trả về đều trỏ vào một ô nhớ tham chiếu duy nhất.”** Sai. Chúng có thể chứa **các bản sao giá trị tham chiếu** đến cùng đối tượng, nhưng là những biến/giá trị khác nhau. Thay đổi một tham chiếu không bắt buộc thay đổi tham chiếu còn lại.

**“`finally` chỉ dọn dẹp nên không thể thay đổi kiểu hoàn thành của phương thức.”** Sai. `return` hoặc `throw` trong `finally` có thể thay thế giá trị trả về hoặc ngoại lệ cũ.

**“Nếu `finally` ném lỗi mới, Java tự bảo toàn lỗi cũ dưới dạng suppressed.”** Không đúng với `finally` thủ công nói chung. Cơ chế suppressed có quy tắc cụ thể của `try-with-resources`; cần phân biệt.

**“Thấy một đối tượng được sửa trong `finally` nghĩa là Java return-by-reference.”** Sai. Java luôn truyền/trả **giá trị**; với kiểu tham chiếu, giá trị ấy là **tham chiếu tới đối tượng**, và việc hai nơi cùng trỏ tới một đối tượng giải thích hành vi mutation.

**“Đã `return` nghĩa là `finally` có thể bị bỏ qua trong mọi trường hợp.”** Sai. Khi trả về theo đường bình thường của ngôn ngữ, `finally` liên quan được chạy. Tuy nhiên, điều này không phải bảo đảm dọn dẹp khi JVM/tiến trình bị kết thúc cưỡng bức.

## 14. Bài tập tự kiểm tra

### Bài 1: Biến nguyên thủy

```java
static int test() {
    int n = 2;
    try {
        return n;
    } finally {
        n += 5;
    }
}
```

**Kết quả?** `test()` trả **2**. `finally` sửa biến thành 7 nhưng không thay đổi giá trị đã chuẩn bị trả về.

### Bài 2: Sửa đối tượng

```java
static StringBuilder test() {
    StringBuilder b = new StringBuilder("X");
    try {
        return b;
    } finally {
        b.append("Y");
    }
}
```

**Bên gọi quan sát chuỗi gì?** `XY`, vì chính đối tượng được trả về đã bị sửa.

### Bài 3: Gán lại biến

```java
static StringBuilder test() {
    StringBuilder b = new StringBuilder("X");
    try {
        return b;
    } finally {
        b = new StringBuilder("Y");
    }
}
```

**Bên gọi quan sát chuỗi gì?** `X`. Biến cục bộ mới trỏ sang đối tượng Y, còn kết quả `return` vẫn giữ tham chiếu đến đối tượng X.

### Bài 4: Mảng

```java
static int[] test() {
    int[] a = {3};
    try {
        return a;
    } finally {
        a[0] = 8;
        a = new int[]{99};
    }
}
```

**Bên gọi thấy phần tử đầu tiên là mấy?** **8**. Thao tác ghi phần tử sửa mảng cũ, còn phép gán biến sau đó chỉ đổi tham chiếu trong biến.

### Bài 5: `return` trong `finally`

```java
static int test() {
    try {
        return 1;
    } finally {
        return 2;
    }
}
```

**Kết quả?** **2**. `finally` tự có `return` mới, ghi đè kết quả đang chờ. Đây là một ví dụ cần tránh trong ứng dụng thực tế.

### Bài 6: Ngoại lệ khi chuẩn bị trả về

Giả sử `return produce();` nằm trong `try` và `produce()` ném `IOException` trước khi tạo kết quả, còn `finally` chỉ ghi log rồi kết thúc bình thường. **Phương thức có trả giá trị không?** Không. Ngoại lệ `IOException` tiếp tục lan truyền sau `finally` nếu không bị một handler phù hợp xử lý.

### Bài 7: Thiết kế API

Nếu một phương thức muốn trả snapshot bất biến của một danh sách, có nên trả `ArrayList` rồi tiếp tục `add` phần tử trong `finally` không? **Không nên**. Nên hoàn tất dữ liệu trước khi trả và chọn kiểu/cách sao chép biểu thị đúng mức bất biến cần thiết.

## 15. Tài liệu tham khảo chuẩn

- [Java Language Specification 17 — `14.17 The return Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.17): đánh giá biểu thức trả về và cách `return` hoàn thành đột ngột.
- [Java Language Specification 17 — `14.20.2 Execution of try-finally and try-catch-finally](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.2): thứ tự chạy `finally` và quy tắc thay thế lý do thoát.
- [Java Language Specification 17 — `4.3 Reference Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.3): ý nghĩa giá trị tham chiếu và đối tượng.
- [Java SE 17 API — StringBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html): đối tượng chuỗi mutable.
- [Java SE 17 API — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): chuỗi immutable.

**Ghi nhớ:** `return` đánh giá và giữ **giá trị trả về** trước khi `finally` chạy. Với biến nguyên thủy, đó là giá trị nguyên thủy; với biến tham chiếu, đó là giá trị tham chiếu đến đối tượng. Thay đổi **biến cục bộ** không viết lại kết quả đã giữ, nhưng thay đổi **trạng thái của đối tượng đã được tham chiếu** có thể hiển thị ở bên gọi. Quy tắc này áp dụng khi `finally` hoàn thành bình thường; `return` hoặc `throw` mới trong `finally` có thể thay thế toàn bộ kết quả.
