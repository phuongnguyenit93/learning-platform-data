# Giá trị mặc định của field và yêu cầu gán biến cục bộ trong Java

Trong Java, **field của đối tượng và field `static` luôn có giá trị ban đầu**, dù người viết chưa gán tường minh. Ngược lại, **biến cục bộ phải được gán chắc chắn trước khi đọc** (*definite assignment*). Hai quy tắc này cùng tồn tại nhưng áp dụng ở hai phạm vi khác nhau. Hiểu đúng chúng giúp phân biệt lỗi biên dịch với giá trị xuất hiện lúc chương trình chạy, đặc biệt khi làm việc với kiểu số nguyên.

## 1. Phân biệt field, biến cục bộ, tham số và phần tử mảng

| Vị trí khai báo | Ví dụ | Có giá trị mặc định khi không gán tường minh? | Quy tắc khi đọc |
| --- | --- | --- | --- |
| Field của đối tượng (*instance field*) | `class A { int count; }` | Có: `0` | Đọc được sau khi tạo đối tượng; giá trị có thể bị thay bởi initializer/constructor |
| Field của lớp (*static field*) | `static long total;` | Có: `0L` | Đọc được; dùng chung theo lớp, không riêng cho từng đối tượng |
| Biến cục bộ trong method, constructor hoặc block | `void run() { int n; }` | **Không** | Trình biên dịch phải chứng minh biến được gán trước mọi lần đọc |
| Tham số method/constructor | `void run(int n)` | Không áp dụng mặc định tại nơi khai báo | Giá trị đến từ lời gọi; có thể đọc ngay trong thân method |
| Phần tử của mảng mới tạo | `new int[3]` | Có: từng phần tử là `0` | Có thể đọc phần tử ngay sau khi tạo mảng |
| Biến cục bộ tham chiếu tới mảng | `int[] a;` | **Không** | Phải gán cho `a` trước khi dùng, dù phần tử của mảng được mặc định nếu mảng đã được tạo |

Một biến chỉ được coi là *local* vì nó được khai báo trong thân method, constructor hoặc block; không phải vì nó mang tên `int` hay được khai báo bằng `final`. Kiểu dữ liệu không quyết định quy tắc gán trước khi đọc: vị trí khai báo mới là yếu tố then chốt.

## 2. Giá trị mặc định của mọi loại field

Khi một đối tượng được tạo, các instance field của nó nhận giá trị mặc định trước khi chạy các phần khởi tạo tường minh. Khi một lớp được chuẩn bị khởi tạo, các static field có giá trị mặc định trước khi chạy static initializer. Phần tử của mảng mới tạo cũng được khởi tạo mặc định.

| Kiểu | Giá trị mặc định | Lưu ý |
| --- | --- | --- |
| `byte` | `0` | Số nguyên 8 bit có dấu |
| `short` | `0` | Số nguyên 16 bit có dấu |
| `int` | `0` | Số nguyên 32 bit có dấu |
| `long` | `0L` | Số nguyên 64 bit có dấu; cách viết `0L` cho thấy rõ kiểu `long` |
| `float` | `0.0f` | Số thực 32 bit |
| `double` | `0.0d` | Số thực 64 bit |
| `char` | `'\u0000'` | Ký tự NUL (mã số 0), khác `'0'` và dấu cách |
| `boolean` | `false` | Không phải `0` |
| Mọi kiểu tham chiếu, gồm `String`, `Integer`, object, array | `null` | Chưa tham chiếu tới đối tượng nào; **không phải** chuỗi rỗng hay mảng rỗng |

Các giá trị trong bảng áp dụng cho field **chưa được khởi tạo tường minh**, không phải cam kết field sẽ giữ giá trị đó mãi. Ví dụ `int quantity = 15;` có giá trị sử dụng là `15` sau khi phần khởi tạo field hoàn tất.

### Ví dụ đầy đủ: field, biến cục bộ đã gán và phần tử mảng

Tạo tệp `DefaultValuesDemo.java`:

```java
public class DefaultValuesDemo {
    private static long total;  // static field: 0
    private int count;          // instance field: 0
    private boolean active;     // instance field: false
    private char marker;        // instance field: '\u0000'
    private String label;       // reference field: null

    public static void main(String[] args) {
        DefaultValuesDemo demo = new DefaultValuesDemo();
        int localCount = 7;       // local: được gán trước khi đọc
        int[] scores = new int[2]; // phần tử mảng tự nhận 0

        System.out.println("total=" + total);
        System.out.println("count=" + demo.count);
        System.out.println("active=" + demo.active);
        System.out.println("markerCode=" + (int) demo.marker);
        System.out.println("label=" + demo.label);
        System.out.println("localCount=" + localCount);
        System.out.println("scores=" + scores[0] + "," + scores[1]);
    }
}
```

Biên dịch và chạy (JDK 17 trở lên):

```bash
javac DefaultValuesDemo.java
java DefaultValuesDemo
```

Kết quả chuẩn:

```text
total=0
count=0
active=false
markerCode=0
label=null
localCount=7
scores=0,0
```

Phép ép `(int) demo.marker` hiển thị mã số `0`, vì ký tự NUL thường không nhìn thấy nếu in trực tiếp. Phép nối chuỗi với tham chiếu `null` tạo ra chữ `null`; **gọi method trên `null` thì khác** và có thể gây `NullPointerException`.

## 3. Biến cục bộ: khai báo không đồng nghĩa đã gán

Java cho phép **khai báo** biến cục bộ trước rồi **gán** sau, nhưng không cho đọc trước khi biến được gán chắc chắn trên mọi đường đi dẫn tới lệnh đọc.

```java
class InvalidLocal {
    static void show() {
        int value;
        System.out.println(value); // LỖI BIÊN DỊCH
    }
}
```

Đây là đoạn **minh họa lỗi**, không phải chương trình để chạy. `javac` thường báo `variable value might not have been initialized`. Không có bước nào ở đây in `0`: trình biên dịch từ chối mã trước khi chạy.

Cách đúng là gán trước lần đọc:

```java
class ValidLocal {
    static void show() {
        int value;
        value = 42;
        System.out.println(value);
    }
}
```

`int value = 42;` là cách gộp khai báo và gán vào một dòng, nhưng **không bắt buộc phải viết cùng dòng**. Đọc cũng xảy ra ngầm trong biểu thức:

```java
class InvalidIncrement {
    static void show() {
        int count;
        // count++;      // sai: cần đọc count trước khi cộng
        // count += 1;    // sai: cũng cần đọc giá trị cũ
        // count = count + 1; // sai: vế phải đọc count
        count = 0;        // gán lần đầu, hợp lệ
        count++;          // đọc và tăng sau khi đã gán, hợp lệ
    }
}
```

Một biến cục bộ `Integer number;` cũng **không tự nhận `null`**; muốn cho phép nó mang giá trị `null` lúc đầu thì phải viết `Integer number = null;`. Tương tự, `int[] values;` không tạo mảng và cũng không khởi tạo biến tham chiếu đó.

## 4. Definite assignment phụ thuộc đường đi của chương trình

Trình biên dịch phân tích các luồng điều khiển có thể đi đến chỗ đọc biến, không chỉ kiểm tra có dấu `=` ở một dòng đứng trước hay không.

### Có `if` / `else`: mọi nhánh dẫn tới chỗ đọc đều gán

Tệp `DefiniteAssignmentDemo.java`:

```java
public class DefiniteAssignmentDemo {
    static int score(boolean passed) {
        int result;
        if (passed) {
            result = 100;
        } else {
            result = 0;
        }
        return result; // cả hai nhánh đều đã gán
    }

    public static void main(String[] args) {
        System.out.println("passed=" + score(true));
        System.out.println("failed=" + score(false));
    }
}
```

```bash
javac DefiniteAssignmentDemo.java
java DefiniteAssignmentDemo
```

```text
passed=100
failed=0
```

Nếu bỏ `else`, biến có thể chưa được gán khi điều kiện sai:

```java
class MissingBranch {
    static int score(boolean passed) {
        int result;
        if (passed) {
            result = 100;
        }
        return result; // LỖI BIÊN DỊCH: có đường đi chưa gán
    }
}
```

Có thể sửa bằng cách gán ban đầu (`int result = 0;`), gán ở nhánh `else`, hoặc `return` sớm tại nhánh không gán. Chỉ cần bảo đảm **mọi đường đi thực sự tới chỗ đọc** đều đã gán; không nhất thiết mọi nhánh phải gán nếu nhánh đó kết thúc method trước khi đọc.

### Vòng lặp: thân vòng có thể không chạy

```java
class LoopCase {
    static void show(boolean shouldRun) {
        int last;
        while (shouldRun) {
            last = 10;
            break;
        }
        // System.out.println(last); // sai: vòng while có thể không chạy
    }
}
```

Nếu cần dùng `last` sau vòng lặp, hãy cấp một giá trị ban đầu hợp lý hoặc tổ chức lại luồng điều khiển. Việc người lập trình “biết” điều kiện thường đúng không thay thế được chứng minh *definite assignment* của trình biên dịch.

### Tham số và biến cục bộ được gán `null`

```java
class AssignedDoesNotMeanNonNull {
    static void inspect(String text) {
        String local = text; // đã được gán, kể cả khi text là null
        // local.length() sẽ ném NullPointerException nếu local == null
        System.out.println(local == null ? "missing" : local.length());
    }
}
```

*Definite assignment* kiểm tra “đã có phép gán hợp lệ chưa”, **không** chứng minh một tham chiếu khác `null` hay một giá trị đáp ứng ràng buộc nghiệp vụ. Điều đó cần kiểm tra riêng, chẳng hạn `if (local != null)` hoặc `Objects.requireNonNull(...)` khi phù hợp.

## 5. Field có mặc định nhưng có thể được gán sau đó

Với một instance field kiểu `int`:

```java
class Counter {
    int count; // mặc định là 0

    Counter() {
        count = 5; // constructor đổi giá trị thành 5
    }
}
```

Một đối tượng `new Counter()` bình thường sẽ có `count == 5` sau khi constructor hoàn tất. Default `0` là trạng thái khởi tạo ban đầu; initializer và constructor có thể thay nó.

Ở mức khái quát, thứ tự liên quan là:

1. Static field nhận mặc định, rồi static initializer/khởi tạo tường minh của lớp chạy theo thứ tự mã nguồn khi lớp được khởi tạo.
2. Mỗi đối tượng mới nhận mặc định cho instance field; initializer/instance initialization block và phần thân constructor sau đó có thể gán giá trị khác theo thứ tự khởi tạo Java.
3. Phần tử mảng mới tạo nhận mặc định theo kiểu phần tử, rồi chương trình có thể sửa từng phần tử.

**Chú ý về thứ tự initializer:** một phương thức được gọi trong initializer có thể quan sát field khai báo phía sau trước khi initializer tường minh của field ấy chạy.

Tệp `InitializationOrderDemo.java`:

```java
public class InitializationOrderDemo {
    private int observed = readLater();
    private int later = 5;

    private int readLater() {
        return later;
    }

    public static void main(String[] args) {
        InitializationOrderDemo demo = new InitializationOrderDemo();
        System.out.println("observed=" + demo.observed);
        System.out.println("later=" + demo.later);
    }
}
```

```bash
javac InitializationOrderDemo.java
java InitializationOrderDemo
```

```text
observed=0
later=5
```

Ở thời điểm `readLater()` được gọi, `later` mới giữ mặc định `0`; lệnh `private int later = 5;` được thực thi sau đó. Ví dụ này **không** nói rằng mọi field sẽ vẫn bằng `0` sau khi constructor hoàn tất.

## 6. Trường hợp `final`: giá trị mặc định không bỏ qua nghĩa vụ gán

Một `final` field được gán ngay khi khai báo thì không cần gán thêm:

```java
class Config {
    final int retries = 3;
}
```

Nếu `final` field không có initializer (*blank final field*), chương trình phải bảo đảm gán theo đúng quy tắc Java: instance blank final được gán đúng một lần trên mỗi đường khởi tạo constructor hoàn tất bình thường; static blank final được gán khi lớp khởi tạo, ví dụ qua static initializer. Không được coi mặc định `0` là phép gán thay thế nghĩa vụ này.

Tệp `FinalFieldDemo.java`:

```java
public class FinalFieldDemo {
    private final int id;
    private static final int LIMIT;

    static {
        LIMIT = 10;
    }

    FinalFieldDemo(int id) {
        this.id = id;
    }

    public static void main(String[] args) {
        FinalFieldDemo demo = new FinalFieldDemo(7);
        System.out.println("id=" + demo.id);
        System.out.println("limit=" + LIMIT);
    }
}
```

```bash
javac FinalFieldDemo.java
java FinalFieldDemo
```

```text
id=7
limit=10
```

Một biến cục bộ `final` có thể khai báo rồi gán một lần: `final int n; n = 4;` là hợp lệ, nhưng `n = 5;` tiếp theo là lỗi biên dịch. Trong `if`/`else`, mỗi nhánh có thể gán cho cùng một biến `final` nếu mỗi đường chạy tới điểm dùng chỉ gán đúng một lần. `final` không có nghĩa “tự có mặc định”.

## 7. Mối liên hệ với `var` và kiểu tham chiếu bao số

Từ Java 10, `var` suy luận kiểu của **biến cục bộ có initializer**:

```java
class InferredLocal {
    static void show() {
        var count = 10;              // suy luận int
        var numbers = new int[2];    // suy luận int[]
        System.out.println(count + numbers[0]); // 10
    }
}
```

Không thể viết `var count;` (không có initializer để suy luận kiểu), `var unknown = null;` (không suy luận được kiểu từ `null`) hay `var` để khai báo field thông thường. Đây là yêu cầu riêng của `var`, bổ sung cho quy tắc gán chắc chắn của mọi biến cục bộ.

Phân biệt primitive field với wrapper field:

```java
class BoxedValues {
    int primitive;        // 0
    Integer boxed;        // null

    int unsafe() {
        return boxed;     // biên dịch được nhưng unboxing null gây NPE khi chạy
    }
}
```

`Integer` là kiểu tham chiếu nên mặc định là `null`, dù nó biểu diễn số nguyên. Không nên coi default của `Integer` là `0`; kiểm tra `null` hoặc gán giá trị trước khi unboxing nếu cần.

## 8. Những nhầm lẫn thường gặp

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| “Mọi biến `int` đều mặc định bằng `0`.” | Sai | Chỉ field/phần tử mảng thuộc diện khởi tạo mặc định; biến cục bộ chưa gán không được đọc |
| “`int x;` trong method rồi `print(x)` sẽ in `0`.” | Sai | Đây là lỗi biên dịch vì `x` chưa được gán chắc chắn |
| “`static int total;` có thể đọc ngay với giá trị `0`.” | Đúng | Static field có khởi tạo mặc định; initializer khác có thể thay đổi sau đó |
| “`String title;` là field thì tự thành chuỗi rỗng.” | Sai | Mặc định là `null`, không phải `""` |
| “`new int[4]` có bốn phần tử bằng `0`.” | Đúng | Phần tử mảng được khởi tạo mặc định |
| “`int[] numbers;` trong method là mảng rỗng.” | Sai | Đây chỉ là biến cục bộ chưa được gán tham chiếu mảng |
| “Đã gán `null` tức là chưa qua definite assignment.” | Sai | `null` cũng là một giá trị được gán hợp lệ cho kiểu tham chiếu |
| “Dùng `++` hoặc `+=` là cách gán đầu tiên cho local.” | Sai | Toán tử phải đọc giá trị cũ trước, nên local phải được gán từ trước |

### Cách quyết định nhanh khi đọc code

1. Xác định biến được khai báo **ở đâu**: field, local, tham số hay phần tử mảng.
2. Nếu là field/phần tử mảng mới, tìm giá trị mặc định theo kiểu; sau đó kiểm tra initializer/constructor/những lệnh gán có thể thay đổi nó.
3. Nếu là biến cục bộ, tìm mọi đường đi đến **lần đọc đầu tiên** và xác minh mỗi đường đã có phép gán.
4. Nếu có `final`, kiểm tra thêm ràng buộc chỉ được gán theo quy tắc một lần và mọi đường khởi tạo bắt buộc.
5. Nếu là kiểu tham chiếu, phân biệt **đã được gán** với **khác `null`**; nếu là wrapper như `Integer`, lưu ý unboxing.

Điểm cần ghi nhớ là: **giá trị mặc định của field và phần tử mảng là hành vi khởi tạo của Java; yêu cầu gán biến cục bộ trước khi đọc là quy tắc kiểm tra của trình biên dịch**. Vì vậy, cùng câu lệnh `int x;` có thể hợp lệ để đọc `x` khi `x` là field, nhưng chưa đủ để đọc `x` nếu `x` là biến cục bộ.