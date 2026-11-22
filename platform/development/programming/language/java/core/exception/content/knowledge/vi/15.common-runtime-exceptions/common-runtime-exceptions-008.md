# `NegativeArraySizeException` trong Java: khi tạo mảng với kích thước âm

`NegativeArraySizeException` là ngoại lệ **unchecked** của Java, phát sinh khi chương trình cố tạo mảng có **ít nhất một kích thước âm**. Ngoại lệ này khác với lỗi truy cập chỉ số mảng, lỗi truy cập `null`, lỗi hết bộ nhớ và lỗi đầu vào của những collection khác. Hiểu đúng nó giúp bạn tìm ra dữ liệu độ dài sai, phép tính bị tràn số hoặc cách phân bổ mảng nhiều chiều không hợp lệ.

Ví dụ tối giản:

~~~java
int requestedSize = -3;
int[] numbers = new int[requestedSize]; // Ném NegativeArraySizeException khi chạy.
~~~

Trong ví dụ trên, phép tạo `new int[-3]` **biên dịch được**; lỗi xuất hiện khi câu lệnh được thực thi. Số `-3` không phải giá trị phần tử, mà là độ dài yêu cầu của mảng.

Nếu độ dài là `0`:

~~~java
int[] empty = new int[0];
System.out.println(empty.length); // 0
~~~

đây là một mảng rỗng **hoàn toàn hợp lệ**. Điều kiện lỗi là **nhỏ hơn 0**, không phải nhỏ hơn hoặc bằng 0.

Bài học dành cho Java 17+, bao gồm: cơ chế tạo mảng, array một chiều và đa chiều, thứ tự đánh giá các biểu thức kích thước, phân biệt với ngoại lệ liên quan, trường hợp reflection, tràn số, validation an toàn, xử lý lỗi và các ví dụ Java chạy được với đầu ra xác thực.

## 1. `NegativeArraySizeException` nằm ở đâu trong phân cấp ngoại lệ?

~~~text
java.lang.Object
    └── java.lang.Throwable
        └── java.lang.Exception
            └── java.lang.RuntimeException
                └── java.lang.NegativeArraySizeException
~~~

Vì kế thừa `RuntimeException`, `NegativeArraySizeException` là **unchecked exception**: compiler không buộc phương thức có thể gây ra nó phải ghi `throws NegativeArraySizeException`, và không buộc caller phải `catch`.

Đặc điểm chính:

| Thuộc tính | Giá trị/ý nghĩa |
| --- | --- |
| Tên đầy đủ | `java.lang.NegativeArraySizeException` |
| Superclass trực tiếp | `java.lang.RuntimeException` |
| Checked hay unchecked? | Unchecked |
| Khi nào xuất hiện? | Yêu cầu tạo mảng với kích thước nguyên âm |
| Ví dụ trực tiếp | `new int[-1]`, `new String[-5]` |
| Tạo mảng rỗng | `new int[0]` hợp lệ |
| Có bắt buộc `throws` không? | Không |
| Cách phòng tránh | Kiểm tra dữ liệu đầu vào, miền hợp lệ, tràn số và giới hạn cấp phát |

`NegativeArraySizeException` có constructor không tham số và constructor nhận `String` như nhiều loại `RuntimeException`. Khi Java tự ném lỗi, nội dung `getMessage()` **không phải hợp đồng ổn định để phân tích chương trình**; hãy dựa vào loại ngoại lệ và dữ liệu độ dài gốc.

Không nên chủ động sử dụng `NegativeArraySizeException` để biểu diễn mọi giá trị số âm trong nghiệp vụ. Nó gắn với **thao tác tạo mảng**. Ví dụ số lượng đặt hàng âm hợp đồng API thường phù hợp với `IllegalArgumentException` hoặc lỗi domain cụ thể hơn.

## 2. Mảng trong Java cần kích thước không âm

Một array creation expression dùng cú pháp:

~~~java
int[] a = new int[3];
String[] names = new String[2];
double[] none = new double[0];
~~~

Các ví dụ này tạo lần lượt ba, hai và không phần tử. Giá trị phần tử ban đầu được gán mặc định theo loại, chẳng hạn `0` với `int` và `null` với tham chiếu `String`.

Độ dài mảng Java là một giá trị `int` không âm, có thể đọc qua field `length`. Sau khi tạo, **độ dài của chính mảng đó không thay đổi**; bạn có thể sửa phần tử, nhưng không tăng trực tiếp `array.length`.

~~~java
int[] scores = new int[2];
System.out.println(scores.length); // 2
scores[0] = 10;
scores[1] = 20;

// Không hợp lệ: array.length là field chỉ đọc.
// scores.length = 5;
~~~

Cú pháp `new int[-1]` được phép đi qua quá trình kiểm tra cú pháp và kiểu; biểu thức độ dài vẫn có kiểu `int`. Khi **đánh giá runtime** thấy một kích thước âm, Java ném `NegativeArraySizeException` và không trả về mảng vừa yêu cầu.

Điểm then chốt: **kích thước được tính bằng biểu thức**, không nhất thiết là một literal. Các giá trị âm thường bắt nguồn từ dữ liệu cấu hình, số lượng phần tử sau phép trừ, hoặc kết quả tính toán số nguyên.

## 3. Giá trị âm là kích thước, không phải phần tử

So sánh ba ví dụ:

~~~java
int[] a = new int[-3];   // Ném NegativeArraySizeException khi chạy.
int[] b = {-3};          // Hợp lệ: một phần tử có giá trị -3.
int[] c = new int[0];    // Hợp lệ: mảng rỗng.
~~~

- `a` yêu cầu **độ dài -3**: không thể tạo mảng.
- `b` có **độ dài 1**, và phần tử đầu tiên mang giá trị âm.
- `c` có **độ dài 0**; mảng tồn tại nhưng không có chỉ số phần tử hợp lệ.

Không được suy luận rằng chỉ cần trong dữ liệu xuất hiện một số âm là Java sẽ ném `NegativeArraySizeException`. Một mảng các số nguyên âm hoàn toàn bình thường:

~~~java
int[] temperatures = {-5, -2, 0, 7};
System.out.println(temperatures.length); // 4
System.out.println(temperatures[0]);     // -5
~~~

Điểm cần rà soát là **biểu thức ở trong dấu `[...]` của thao tác tạo mảng**, ví dụ `new int[size]`, chứ không phải mọi giá trị nằm trong array initializer `{...}`.

## 4. Java 17+: chương trình cơ bản thử kích thước âm, 0 và dương

Lưu tệp `NegativeArraySizeDemo.java`:

~~~java
public class NegativeArraySizeDemo {
    static void allocate(int size) {
        try {
            int[] numbers = new int[size];
            System.out.println("size=" + size + ", length=" + numbers.length);
        } catch (NegativeArraySizeException ex) {
            System.out.println("size=" + size + ", caught=" + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        allocate(-3);
        allocate(0);
        allocate(2);

        int[] values = {-3};
        System.out.println("Phần tử âm: " + values[0]);

        int[] empty = new int[0];
        System.out.println("Mảng rỗng: " + empty.length);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 NegativeArraySizeDemo.java
java NegativeArraySizeDemo
~~~

Stdout chính xác:

~~~text
size=-3, caught=NegativeArraySizeException
size=0, length=0
size=2, length=2
Phần tử âm: -3
Mảng rỗng: 0
~~~

### Phân tích

1. `allocate(-3)` tính biểu thức độ dài thành `-3`; Java ném `NegativeArraySizeException` ngay tại array creation expression.
2. `catch` bắt đúng ngoại lệ. Chương trình không in `numbers.length` trên đường thất bại, vì không có mảng được tạo thành công.
3. `allocate(0)` tạo mảng rỗng và in `length=0`.
4. `allocate(2)` tạo mảng hai phần tử.
5. `int[] values = {-3}` chỉ chứa một phần tử âm, không có kích thước âm.
6. `new int[0]` vẫn trả về một đối tượng array hợp lệ.

Trong hệ thống thật, nên xem **giá trị `size` đến từ đâu**, chứ không chỉ viết `catch (NegativeArraySizeException)` rồi tiếp tục bằng cách trả mảng rỗng. Việc silently coi yêu cầu độ dài âm là “không có dữ liệu” thường che giấu lỗi dữ liệu hoặc lỗi tính toán.

## 5. Ngoại lệ xuất hiện lúc nào: compile time hay runtime?

Java cho phép viết biểu thức:

~~~java
int[] numbers = new int[-1];
~~~

Mặc dù `-1` là một hằng số rõ ràng âm, cú pháp khai báo mảng này vẫn **biên dịch hợp lệ** theo Java 17. Khi thực thi biểu thức khởi tạo, JVM sẽ ném `NegativeArraySizeException`.

Đây không phải một lỗi kiểu (`type mismatch`) hoặc một lỗi cú pháp. Biểu thức `-1` có kiểu `int` phù hợp với yêu cầu của biểu thức kích thước. Giá trị không hợp lệ được phát hiện ở bước thực thi việc tạo mảng.

Phân biệt với lỗi compile time:

~~~java
// CỐ Ý SAI: yêu cầu kiểu số nguyên phù hợp cho array dimension.
int[] bad = new int[3.5];
~~~

Ở đây, `3.5` có kiểu `double`, không thể được sử dụng trực tiếp làm array dimension hợp lệ. Compiler từ chối vì **kiểu không phù hợp**, không phải vì kích thước âm.

Một biểu thức kiểu `long` cũng không được sử dụng trực tiếp như `new int[someLong]` nếu không có phép chuyển kiểu phù hợp. Việc ép kiểu `long` sang `int` có thể làm mất dữ liệu, nên chỉ cast sau khi kiểm tra miền giá trị.

## 6. Mảng nhiều chiều: bất kỳ kích thước âm đều là lỗi

Java hỗ trợ tạo mảng nhiều chiều theo cách khai báo:

~~~java
int[][] matrix = new int[2][3];
~~~

Trong ví dụ này, Java tạo một mảng ngoài có hai phần tử, mỗi phần tử là một tham chiếu tới mảng `int` dài ba. Java dùng **mảng của các mảng**, không yêu cầu mọi chiều có cùng độ dài khi bạn gán lại từng hàng.

Những trường hợp gây lỗi:

~~~java
int[][] a = new int[-1][3]; // Sai: chiều ngoài âm.
int[][] b = new int[2][-3]; // Sai: chiều trong âm.
int[][] c = new int[0][-1]; // Sai: chiều trong âm dù chiều ngoài bằng 0.
~~~

Điểm thứ ba dễ gây bất ngờ. Không thể suy luận rằng chiều đầu `0` làm Java bỏ qua mọi kiểm tra kích thước còn lại. **Mọi biểu thức kích thước được viết trong array creation expression đều được đánh giá và kiểm tra theo ngữ nghĩa tạo mảng**.

Ngược lại:

~~~java
int[][] rows = new int[2][];
System.out.println(rows.length);  // 2
System.out.println(rows[0]);      // null
~~~

Cách viết này hợp lệ. Chỉ chiều thứ nhất được cấp phát tại thời điểm đó; hai phần tử trong mảng ngoài ban đầu là `null`, và từng mảng con có thể được tạo/gán sau. Đây là cơ sở của **jagged arrays** (mảng răng cưa).

~~~java
rows[0] = new int[2];
rows[1] = new int[5];
System.out.println(rows[0].length); // 2
System.out.println(rows[1].length); // 5
~~~

Nếu bạn dùng `rows[0]` trước khi gán một mảng con, lỗi có thể là `NullPointerException`, không phải `NegativeArraySizeException`.

## 7. Thứ tự đánh giá biểu thức kích thước: một điểm quan trọng

Với biểu thức:

~~~java
int[][] array = new int[first()][second()];
~~~

Java **đánh giá các biểu thức kích thước từ trái sang phải**, trước khi tiến hành kiểm tra kích thước âm và cấp phát theo ngữ nghĩa array creation. Vì vậy **side effect** trong `second()` vẫn có thể xảy ra ngay cả khi `first()` trả số âm.

Nếu `second()` **tự ném một ngoại lệ**, ngoại lệ của `second()` xuất hiện trước bước kiểm tra kích thước âm; `NegativeArraySizeException` của giá trị âm ở `first()` sẽ không được ném trong lần đánh giá đó.

Tình huống này không có nghĩa giá trị âm trở nên hợp lệ. Nó có nghĩa **đánh giá biểu thức đã kết thúc bất thường trước khi đến bước kiểm tra giá trị**.

Sơ đồ:

~~~text
Đánh giá first()
    ↓
Nếu first() ném → dừng, truyền lỗi first()
    ↓ nếu trả bình thường
Đánh giá second()
    ↓
Nếu second() ném → dừng, truyền lỗi second()
    ↓ nếu trả bình thường
Kiểm tra các giá trị kích thước đã đánh giá
    ↓
Nếu có giá trị âm → NegativeArraySizeException
    ↓ nếu đều không âm
Cấp phát các mảng phù hợp
~~~

Không nên phụ thuộc vào side effect ở biểu thức kích thước để điều khiển logic nghiệp vụ. Cách dễ đọc và kiểm thử hơn là tính toán các biến độ dài, xác thực chúng, rồi mới tạo mảng.

## 8. Java 17+: kiểm chứng thứ tự đánh giá và mảng nhiều chiều

Tệp `DimensionEvaluationDemo.java`:

~~~java
public class DimensionEvaluationDemo {
    static int first() {
        System.out.println("Đánh giá chiều 1");
        return -1;
    }

    static int second() {
        System.out.println("Đánh giá chiều 2");
        return 2;
    }

    static int fails() {
        System.out.println("Chiều 2 ném lỗi");
        throw new IllegalStateException("lỗi biểu thức");
    }

    public static void main(String[] args) {
        try {
            int[][] numbers = new int[first()][second()];
            System.out.println(numbers.length);
        } catch (NegativeArraySizeException ex) {
            System.out.println("Bắt kích thước âm");
        }

        try {
            int[][] numbers = new int[first()][fails()];
            System.out.println(numbers.length);
        } catch (IllegalStateException ex) {
            System.out.println("Bắt lỗi biểu thức: " + ex.getMessage());
        }

        try {
            int[][] numbers = new int[0][-2];
            System.out.println(numbers.length);
        } catch (NegativeArraySizeException ex) {
            System.out.println("Chiều sau âm dù chiều đầu bằng 0");
        }

        int[][] rows = new int[2][];
        System.out.println("Mảng ngoài: " + rows.length
                + ", hàng đầu null: " + (rows[0] == null));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 DimensionEvaluationDemo.java
java DimensionEvaluationDemo
~~~

Stdout chính xác:

~~~text
Đánh giá chiều 1
Đánh giá chiều 2
Bắt kích thước âm
Đánh giá chiều 1
Chiều 2 ném lỗi
Bắt lỗi biểu thức: lỗi biểu thức
Chiều sau âm dù chiều đầu bằng 0
Mảng ngoài: 2, hàng đầu null: true
~~~

**Các kết luận được chứng minh:**

- Đường thứ nhất đánh giá cả `first()` và `second()`; dù `first()` trả `-1`, `second()` vẫn được gọi, sau đó Java ném `NegativeArraySizeException`.
- Đường thứ hai đánh giá `first()`, rồi `fails()` ném `IllegalStateException`. Không đến bước báo kích thước âm.
- `new int[0][-2]` thất bại vì kích thước chiều thứ hai âm.
- `new int[2][]` hợp lệ, nhưng chưa tạo các mảng con.

Nếu viết nhiều chiều hơn, cùng nguyên tắc áp dụng cho các biểu thức kích thước được chỉ định. Đừng nhầm các chiều **chưa được khai báo kích thước** (`[]` trống ở đuôi) với chiều được khai báo có giá trị `0`.

## 9. `NegativeArraySizeException` và `ArrayIndexOutOfBoundsException` khác nhau

Hai lỗi đều có thể liên quan đến mảng nhưng xảy ra ở **hai giai đoạn khác nhau**:

| Lỗi | Khi nào? | Ví dụ |
| --- | --- | --- |
| `NegativeArraySizeException` | **Tạo mảng** với một biểu thức kích thước âm | `new int[-1]` |
| `ArrayIndexOutOfBoundsException` | **Truy cập mảng đã có** với chỉ số nằm ngoài `[0, length)` | `new int[2]` rồi đọc `a[2]` |
| `NullPointerException` | Dùng tham chiếu mảng đang là `null` | `int[] a = null; a[0]` |

Các ví dụ là mảnh code minh họa, không phải chương trình độc lập. `NegativeArraySizeException` kế thừa trực tiếp `RuntimeException`, còn `ArrayIndexOutOfBoundsException` kế thừa `IndexOutOfBoundsException`; do đó `catch (IndexOutOfBoundsException)` **không bắt lỗi kích thước âm**. Lỗi truy cập chỉ số và các quy tắc `[from, to)` là trọng tâm của bài về bounds; tại đây cần truy ngược **giá trị được tính ra cho kích thước lúc tạo mảng**, kể cả khả năng `int` overflow.

## 10. Reflection: `Array.newInstance` cũng có thể ném ngoại lệ

Java hỗ trợ tạo array qua reflection:

~~~java
Object array = java.lang.reflect.Array.newInstance(String.class, 3);
~~~

Khi sử dụng `Array.newInstance(componentType, length)`, nếu `length` âm, API cũng có thể ném `NegativeArraySizeException`. Với dạng nhiều chiều nhận các kích thước, một kích thước âm cũng là lỗi.

Điều này hữu ích trong framework, serializer, thư viện xử lý bảng động hoặc những phần code chỉ biết component type tại runtime. **Không chỉ cú pháp `new T[n]` mới gặp lỗi kích thước âm.**

Nhưng phải đọc hợp đồng của API cụ thể. Ví dụ một `ArrayList` không phải Java array ở mức runtime; constructor `new ArrayList<>(-1)` sử dụng quy tắc tham số capacity và có thể ném **`IllegalArgumentException`**, không phải `NegativeArraySizeException`.

## 11. Java 17+: reflection, ArrayList và lỗi index

Tệp `ReflectionAndIndexDemo.java`:

~~~java
import java.lang.reflect.Array;
import java.util.ArrayList;

public class ReflectionAndIndexDemo {
    public static void main(String[] args) {
        try {
            Array.newInstance(String.class, -5);
        } catch (NegativeArraySizeException ex) {
            System.out.println("Reflection: " + ex.getClass().getSimpleName());
        }

        try {
            Array.newInstance(int.class, 2, -3);
        } catch (NegativeArraySizeException ex) {
            System.out.println("Reflection nhiều chiều: "
                    + ex.getClass().getSimpleName());
        }

        try {
            new ArrayList<String>(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("ArrayList capacity: " + ex.getClass().getSimpleName());
        }

        int[] numbers = new int[2];
        try {
            System.out.println(numbers[-1]);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("Index: " + ex.getClass().getSimpleName());
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 ReflectionAndIndexDemo.java
java ReflectionAndIndexDemo
~~~

Stdout chính xác:

~~~text
Reflection: NegativeArraySizeException
Reflection nhiều chiều: NegativeArraySizeException
ArrayList capacity: IllegalArgumentException
Index: ArrayIndexOutOfBoundsException
~~~

Từ đó thấy **không thể chỉ nhìn một tham số âm để đoán đúng loại exception**. Phải biết thao tác cụ thể:

- Tạo Java array kích thước âm → `NegativeArraySizeException`.
- Tạo `ArrayList` với capacity âm → `IllegalArgumentException` theo hợp đồng constructor `ArrayList(int)`.
- Truy cập phần tử array bằng index âm → `ArrayIndexOutOfBoundsException`.

`NegativeArraySizeException` phát sinh từ thao tác cấp phát mảng, không phải loại lỗi tổng quát của mọi collection.

## 12. Nguồn phát sinh thường gặp: độ dài tính sai

Trong sản phẩm thật, ít người cố ý viết `new int[-1]`. Lỗi thường xảy ra khi **biểu thức kích thước** bị âm ngoài dự kiến.

### 12.1. Trừ nhầm một đơn vị

~~~java
int remaining = endExclusive - startInclusive;
int[] data = new int[remaining];
~~~

Nếu `endExclusive < startInclusive`, `remaining` âm. Cần xác định hợp đồng của cặp chỉ số:

- Có cho phép đoạn rỗng (`startInclusive == endExclusive`) không?
- Có cho phép `startInclusive > endExclusive` không?
- Hai giá trị có nằm trong giới hạn nguồn dữ liệu không?
- Phép trừ có nguy cơ **tràn số `int`** không?

Không phải cứ `Math.max(0, remaining)` là sửa đúng. Nếu cặp chỉ số bị đảo vì bug, ép độ dài về 0 sẽ **giấu lỗi và thay đổi ngữ nghĩa**.

### 12.2. Giá trị sentinel `-1`

Nhiều API dùng `-1` làm giá trị đặc biệt, ví dụ “không tìm thấy”, “không xác định” hoặc “EOF” tùy hợp đồng. Nếu bạn đưa giá trị đó trực tiếp vào `new byte[count]`, bạn đang dùng **mã trạng thái như kích thước mảng**.

~~~java
int count = -1; // Minh họa sentinel "chưa xác định".
byte[] payload = new byte[count]; // Sai nếu không chuyển trạng thái.
~~~

Cần xử lý `-1` theo ý nghĩa của API nguồn **trước khi** dùng làm độ dài. Không tự động coi `-1` là mảng rỗng.

### 12.3. Giá trị từ cấu hình hoặc người dùng

~~~java
int configuredSize = Integer.parseInt(input);
byte[] buffer = new byte[configuredSize];
~~~

Trong đoạn minh họa này, `input` là biến ở phạm vi chứa. Có hai đường lỗi khác nhau:

- Nếu chuỗi không phân tích được thành số nguyên → có thể là `NumberFormatException`.
- Nếu chuỗi phân tích thành `-7` → `new byte[-7]` có thể ném `NegativeArraySizeException`.

Nếu cấu hình quá lớn dù dương, cấp phát vẫn có thể gặp vấn đề bộ nhớ. Vì vậy validation phải bao gồm **cận dưới và cận trên**, không chỉ kiểm tra `>=0`.

### 12.4. Kích thước suy ra từ phép nhân

~~~java
int totalCells = rows * columns;
int[] matrix = new int[totalCells];
~~~

Cả `rows` và `columns` có thể dương nhưng phép nhân `int` bị tràn, tạo ra giá trị âm hoặc số dương sai. Do đó kiểm tra `totalCells >= 0` **sau khi nhân** chưa đủ bảo đảm phép tính đúng.

## 13. Tràn số nguyên: giá trị âm không phải luôn từ input âm

Số nguyên `int` trong Java có miền từ `-2_147_483_648` đến `2_147_483_647`. Phép cộng số nguyên thông thường có thể bị tràn, và Java không tự ném `ArithmeticException` cho mọi phép cộng tràn.

Ví dụ:

~~~java
int max = Integer.MAX_VALUE;
int overflowed = max + 1;
System.out.println(overflowed); // -2147483648
byte[] data = new byte[overflowed]; // NegativeArraySizeException.
~~~

Hai số đầu vào có thể không âm, nhưng kết quả trung gian âm vì overflow.

Sử dụng các phương thức kiểm tra overflow khi thích hợp:

~~~java
int safeSum = Math.addExact(a, b);
int safeProduct = Math.multiplyExact(a, b);
int narrowed = Math.toIntExact(longLength);
~~~

Đây là **đoạn minh họa**, các biến `a`, `b`, `longLength` cần được khai báo. Các phương thức trên ném `ArithmeticException` khi phép tính/ép hẹp không thể biểu diễn chính xác trong kiểu kết quả. Chúng **không cấp phát bộ nhớ** và không tự xác thực giới hạn nghiệp vụ; bạn vẫn cần kiểm tra độ dài tối đa hợp lý.

Đối với số lượng tính từ hai chỉ số, dùng `long` cho bước trung gian có thể giúp tránh overflow `int`:

~~~java
long length = (long) endExclusive - startInclusive;
if (length < 0 || length > MAX_ALLOWED) {
    throw new IllegalArgumentException("Khoảng dữ liệu không hợp lệ");
}
int[] data = new int[Math.toIntExact(length)];
~~~

Đây là **đoạn minh họa trong phương thức** có `endExclusive`, `startInclusive`, `MAX_ALLOWED` được khai báo hợp lệ. Cách làm phân biệt rõ **kiểm tra miền giá trị** và **cấp phát**.

## 14. Java 17+: overflow và xác thực kích thước trước khi tạo mảng

Tệp `LengthOverflowDemo.java`:

~~~java
public class LengthOverflowDemo {
    static int validatedLength(long length) {
        if (length < 0 || length > 1_000_000) {
            throw new IllegalArgumentException("độ dài ngoài miền cho phép");
        }
        return Math.toIntExact(length);
    }

    public static void main(String[] args) {
        int max = Integer.MAX_VALUE;
        int overflowed = max + 1;
        System.out.println("Sau tràn số: " + overflowed);
        try {
            byte[] bytes = new byte[overflowed];
            System.out.println(bytes.length);
        } catch (NegativeArraySizeException ex) {
            System.out.println("Cấp phát: NegativeArraySizeException");
        }

        try {
            Math.addExact(max, 1);
        } catch (ArithmeticException ex) {
            System.out.println("addExact: ArithmeticException");
        }

        for (long candidate : new long[] {-2, 0, 2, 2_147_483_648L}) {
            try {
                byte[] data = new byte[validatedLength(candidate)];
                System.out.println("candidate=" + candidate + ", length=" + data.length);
            } catch (IllegalArgumentException ex) {
                System.out.println("candidate=" + candidate + ", invalid");
            }
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 LengthOverflowDemo.java
java LengthOverflowDemo
~~~

Stdout chính xác:

~~~text
Sau tràn số: -2147483648
Cấp phát: NegativeArraySizeException
addExact: ArithmeticException
candidate=-2, invalid
candidate=0, length=0
candidate=2, length=2
candidate=2147483648, invalid
~~~

Giải thích:

1. `Integer.MAX_VALUE + 1` tràn thành `Integer.MIN_VALUE`, tức `-2147483648`.
2. Dùng giá trị đó làm kích thước mảng ném `NegativeArraySizeException`.
3. `Math.addExact(max,1)` **phát hiện overflow** và ném `ArithmeticException`, giúp lỗi được nhận diện ở **phép tính** trước khi đến bước cấp phát.
4. `validatedLength` chặn số âm và số vượt giới hạn của **ví dụ** (1.000.000), rồi dùng `Math.toIntExact`.
5. `0` và `2` hợp lệ, tạo mảng có độ dài tương ứng.
6. `2_147_483_648L` vượt miền `int` và giới hạn của ứng dụng; hàm xác thực báo `IllegalArgumentException` thay vì để cast bị mất dữ liệu.

Giới hạn 1.000.000 trong ví dụ **không phải giới hạn cố định của mọi Java array**; đó là chính sách kích thước có chủ đích. Một chương trình cần lựa chọn ngưỡng theo yêu cầu và ngân sách bộ nhớ của nó.

## 15. Kích thước dương lớn có thể gặp lỗi khác

`NegativeArraySizeException` chỉ nói rằng **một kích thước âm** đã được sử dụng. Không thể kết luận kích thước dương là chắc chắn tạo được mảng.

Ví dụ:

~~~java
// KHÔNG chạy tùy tiện: có thể yêu cầu lượng bộ nhớ rất lớn.
// byte[] huge = new byte[Integer.MAX_VALUE];
~~~

Kết quả phụ thuộc khả năng cấp phát của JVM, memory heap, giới hạn kích thước array và môi trường chạy. Với yêu cầu quá lớn, có thể xuất hiện `OutOfMemoryError` hoặc thông báo liên quan tới giới hạn kích thước mảng. **`OutOfMemoryError` là nhánh `Error`, không phải `NegativeArraySizeException`**.

Đừng viết test sản phẩm cố cấp phát mảng cực lớn chỉ để “xem lỗi gì” trên một môi trường dùng chung; có thể làm JVM chậm, thu hồi bộ nhớ liên tục hoặc hết tài nguyên.

Chính sách tốt:

- Xác định **giới hạn kích thước hợp lý** của bài toán.
- Kiểm tra `length >= 0` và `length <= maxAllowed`.
- Kiểm tra overflow trong phép cộng/nhân tạo ra độ dài.
- Với dữ liệu lớn, xem xét **streaming, chia khối/batching** hoặc cấu trúc dữ liệu không cần cấp một mảng liên tục rất lớn.
- Không dựa vào việc catch `OutOfMemoryError` như giải pháp quản lý tài nguyên bình thường.

## 16. Có nên `catch (NegativeArraySizeException)` trong ứng dụng thật?

Về mặt cú pháp, bạn có thể bắt trực tiếp:

~~~java
try {
    int[] data = new int[requestedSize];
    use(data);
} catch (NegativeArraySizeException ex) {
    logInvalidSize(requestedSize, ex);
}
~~~

Đoạn trên là **minh họa** với `requestedSize`, `use`, `logInvalidSize` thuộc ngữ cảnh chứa. Nhưng cần đánh giá mục đích:

- Nếu độ dài âm có thể do **input không tin cậy**, nên validate input **trước khi cấp phát**, chọn loại lỗi đầu vào có ý nghĩa với caller.
- Nếu độ dài âm do **bug tính toán nội bộ**, bắt rồi bỏ qua thường che bug. Nên log đủ ngữ cảnh và sửa phép tính.
- Nếu đang triển khai một **boundary nhận dữ liệu tùy ý** hoặc công cụ kiểm thử, bắt `NegativeArraySizeException` để chuyển thành thông báo an toàn có thể hợp lý.
- Nếu catch ngoại lệ rồi tự trả mảng rỗng, cần chắc chắn đó là **quy tắc nghiệp vụ được quy định**, không phải cách che trạng thái sai.
- Không được đồng nhất loại ngoại lệ unchecked với lỗi có thể tùy tiện bỏ qua.

Ví dụ tốt hơn ở tầng validation:

~~~java
static byte[] allocateBuffer(long requested) {
    final int maxAllowed = 1_000_000;
    if (requested < 0 || requested > maxAllowed) {
        throw new IllegalArgumentException(
                "requested phải trong [0, " + maxAllowed + "]");
    }
    return new byte[Math.toIntExact(requested)];
}
~~~

Đây là **phương thức Java có thể biên dịch** khi đặt trong lớp. Nó xác định rõ điều kiện đầu vào và giới hạn nghiệp vụ trước khi khởi tạo. `IllegalArgumentException` giúp caller thấy **hợp đồng phương thức bị vi phạm**, thay vì phụ thuộc vào lỗi cấp phát phát sinh sâu bên trong.

## 17. `throw` thủ công và ngoại lệ do runtime tạo

Bạn có thể tự ném đối tượng:

~~~java
throw new NegativeArraySizeException("Kích thước không hợp lệ: " + requested);
~~~

Cú pháp đó hợp lệ khi `requested` tồn tại. Nhưng đối với **validation của API**, một `IllegalArgumentException` chuẩn hoặc exception domain cụ thể thường rõ nghĩa hơn. `NegativeArraySizeException` đặc biệt nói rằng điều kiện gây lỗi liên quan tới **việc tạo mảng**, nên đặt loại đó cho một lỗi không liên quan sẽ gây khó hiểu.

`NegativeArraySizeException` được runtime tạo ra khi array creation expression gặp kích thước âm có thể có message khác với ngoại lệ bạn tự tạo. **Không parse `getMessage()`** để suy ra kích thước hoặc khôi phục dữ liệu; message không nên được coi như API cấu trúc ổn định.

Nếu cần giá trị kích thước âm để điều tra, ghi log input và bước tính toán liên quan, nhưng bảo đảm không đưa dữ liệu nhạy cảm ra log ngoài chính sách.

## 18. So sánh các lỗi thường gặp quanh array

| Tình huống | Ngoại lệ/lỗi điển hình |
| --- | --- |
| `new int[-4]` | `NegativeArraySizeException` |
| `new int[0]` | Thành công, mảng rỗng |
| `new String[2][-1]` | `NegativeArraySizeException` |
| `new int[2][]` | Thành công, các mảng con chưa tạo (ban đầu `null`) |
| `int[] a = new int[2]; a[-1]` | `ArrayIndexOutOfBoundsException` |
| `int[] a = new int[2]; a[2]` | `ArrayIndexOutOfBoundsException` |
| `int[] a = null; a[0]` | `NullPointerException` |
| `Integer.parseInt("abc")` | `NumberFormatException` |
| `new ArrayList<>(-1)` | `IllegalArgumentException` |
| `Math.addExact(Integer.MAX_VALUE,1)` | `ArithmeticException` |
| `new byte[giá_trị_dương_rất_lớn]` | Có thể gặp `OutOfMemoryError`; không suy ra chắc chắn kết quả ở mọi JVM |
| `Array.newInstance(int.class, -2)` | `NegativeArraySizeException` |

Bảng giả định các biểu thức được thực thi và không có một ngoại lệ khác xuất hiện trước bước quan tâm; ví dụ một hàm tính độ dài có side effect và tự ném trước khi hoàn tất có thể tạo loại lỗi khác.

## 19. Xác định bug bằng cách lần ngược giá trị kích thước

Khi gặp stack trace có `NegativeArraySizeException`, hãy truy ngược từ nơi tạo array:

1. **Tìm array creation expression**: `new byte[size]`, `new T[n][m]`, `Array.newInstance(...)` hay API gián tiếp?
2. **Ghi lại giá trị kích thước thực tế** (nếu có thể làm an toàn), gồm từng chiều của mảng đa chiều.
3. **Theo dấu nguồn dữ liệu**: tham số, cấu hình, số dòng đọc được, phép trừ chỉ số, sentinel `-1`, kết quả parser hay phép toán?
4. **Kiểm tra overflow**: phép nhân/tổng độ dài có thể vượt `int` không? Có cast `long → int` không?
5. **Kiểm tra logic độ dài bằng 0**: trường hợp rỗng có được phép không, hay là dấu hiệu dữ liệu lỗi?
6. **Kiểm tra thứ tự đánh giá các dimension expressions**, nếu có nhiều chiều hoặc side effect.
7. **Bổ sung validation ở boundary thích hợp** trước khi cấp phát.
8. **Viết test cho các miền biên**: âm, 0, 1, giới hạn tối đa cho phép, và giá trị vượt giới hạn.
9. Nếu mảng được tạo trong constructor/factory, xem xét liệu **trạng thái/tài nguyên đã cấp phát trước điểm lỗi** được xử lý đúng hay không.
10. Không thay mọi giá trị âm thành `0` khi chưa biết tại sao âm xuất hiện.

Với bài toán tính độ dài đoạn `[start,end)`, có thể assert `start <= end` rồi kiểm tra phạm vi; với kích thước buffer phụ thuộc payload, cần kiểm soát payload tối đa. Điều quan trọng là **mối quan hệ nghiệp vụ**, không chỉ cú pháp `new int[n]`.

## 20. Hướng dẫn kiểm thử các trường hợp biên

Một tập test hợp lý:

| Input kích thước | Kỳ vọng của array allocation trực tiếp | Kỳ vọng của API có validation |
| --- | --- | --- |
| `-1` | `NegativeArraySizeException` | Lỗi đầu vào theo hợp đồng, ví dụ `IllegalArgumentException` |
| `0` | Thành công, `length=0` | Thành công nếu ứng dụng cho phép dữ liệu rỗng |
| `1` | Thành công, `length=1` | Thành công |
| `maxAllowed` | Có thể tạo nếu cấp phát đủ bộ nhớ | Thành công nếu tài nguyên cho phép |
| `maxAllowed+1` | Có thể tạo hoặc không, tùy số cụ thể và môi trường | Bị từ chối theo hợp đồng trước khi cấp phát |
| Giá trị sau overflow thành âm | `NegativeArraySizeException` | Nên phát hiện overflow ở phép tính trước |
| Đầu vào không phân tích thành số | Lỗi parser trước array allocation | Lỗi dữ liệu có thông báo/mã phù hợp |

Trong test unit, đừng cố cấp phát mảng sát giới hạn JVM; thay bằng **giới hạn ứng dụng nhỏ** để kiểm thử validation ổn định và không ngốn heap.

Có thể kiểm tra cả **loại exception** và **thông tin lỗi được công bố**, không cần assert message được tạo bởi JVM:

~~~java
// Ví dụ JUnit-style minh họa ý định; cần thư viện JUnit nếu chạy.
assertThrows(NegativeArraySizeException.class, () -> new int[-1]);
~~~

Đoạn này chỉ mô tả ý tưởng kiểm thử, **không phải chương trình Java 17 độc lập**, và cần kiểm tra ngữ cảnh lambda/method reference theo API test cụ thể. Các chương trình Java 17 ở mục 4, 8, 11 và 14 là các ví dụ hoàn chỉnh không cần phụ thuộc bên ngoài.

## 21. Những hiểu nhầm phổ biến

| Hiểu nhầm | Sự thật |
| --- | --- |
| “`new int[-1]` không biên dịch.” | Biên dịch được; lỗi phát sinh lúc chạy khi biểu thức cấp phát được đánh giá. |
| “`new int[0]` cũng bị lỗi vì không có phần tử.” | Không. Kích thước 0 hợp lệ. |
| “Có một phần tử âm thì mảng không hợp lệ.” | Không. `int[] a={-5}` hoàn toàn hợp lệ. |
| “Chiều đầu 0 nên các chiều sau không được kiểm tra.” | Sai. `new int[0][-1]` vẫn ném `NegativeArraySizeException`. |
| “Nếu chiều đầu âm thì Java không gọi biểu thức của chiều sau.” | Sai khi chiều đầu **trả bình thường**: Java tiếp tục đánh giá các dimension expressions trước khi kiểm tra âm. |
| “Dimension expression sau ném lỗi nhưng vẫn bắt `NegativeArraySizeException` của dimension đầu.” | Lỗi từ biểu thức phía sau có thể kết thúc đánh giá trước bước kiểm tra kích thước âm. |
| “`NegativeArraySizeException` là subclass của `IndexOutOfBoundsException`.” | Không; superclass trực tiếp là `RuntimeException`. |
| “Index âm và size âm là cùng một lỗi.” | Truy cập index âm thường là `ArrayIndexOutOfBoundsException`; cấp phát size âm là `NegativeArraySizeException`. |
| “`new ArrayList<>(-1)` cũng ném `NegativeArraySizeException`.” | Constructor `ArrayList(int)` ném `IllegalArgumentException` cho capacity âm. |
| “Không bao giờ có size âm nếu input ban đầu dương.” | Overflow hoặc phép tính sai vẫn có thể tạo số âm. |
| “Chỉ cần ép `Math.max(0,size)` là luôn đúng.” | Có thể che bug, làm sai ngữ nghĩa và mất dữ liệu. |
| “Giá trị dương chắc chắn cấp phát thành công.” | Kích thước lớn vẫn có thể vượt ngân sách bộ nhớ/giới hạn JVM. |
| “Chỉ cần catch exception là đã khắc phục.” | Nếu size được tính sai, cần sửa nguồn và kiểm tra điều kiện. |
| “Thông điệp `getMessage()` của lỗi runtime là API ổn định.” | Không nên phụ thuộc vào cấu trúc message cụ thể do JVM tạo. |

## 22. Câu hỏi tự kiểm tra

**Câu 1.** `new int[-2]` gây lỗi gì và ở thời điểm nào?

**Đáp án:** `NegativeArraySizeException` tại runtime khi biểu thức tạo mảng được thực thi.

**Câu 2.** `new int[0]` có hợp lệ không?

**Đáp án:** Có. Mảng rỗng có `length=0`.

**Câu 3.** `int[] x={-2}` có ném `NegativeArraySizeException` không?

**Đáp án:** Không. `-2` là giá trị phần tử, mảng dài 1.

**Câu 4.** `new int[0][-1]` có hợp lệ không?

**Đáp án:** Không. Kích thước âm của chiều thứ hai vẫn bị kiểm tra.

**Câu 5.** Với `new int[first()][second()]`, `first()` trả `-1` còn `second()` có side effect nhưng trả `2`, `second()` có chạy không?

**Đáp án:** Có. Java đánh giá các biểu thức kích thước theo thứ tự trái sang phải trước khi kiểm tra giá trị âm.

**Câu 6.** Nếu `second()` ném `IllegalStateException`, Java có nhất thiết ném thêm `NegativeArraySizeException` vì `first()=-1` không?

**Đáp án:** Không. Việc đánh giá biểu thức đã kết thúc bất thường ở `second()`.

**Câu 7.** `int[] a=new int[2]; a[-1]` ném gì?

**Đáp án:** `ArrayIndexOutOfBoundsException`, do truy cập phần tử ở index không hợp lệ.

**Câu 8.** `new ArrayList<String>(-1)` có ném `NegativeArraySizeException` không?

**Đáp án:** Không. Constructor capacity của `ArrayList` ném `IllegalArgumentException`.

**Câu 9.** `Math.addExact(Integer.MAX_VALUE,1)` ném gì?

**Đáp án:** `ArithmeticException` do phép cộng tràn `int`.

**Câu 10.** Nếu một buffer cần kích thước lấy từ `long`, làm sao phòng lỗi do ép hẹp?

**Đáp án:** Kiểm tra giá trị nằm trong miền hợp lệ và ngân sách bộ nhớ, rồi dùng `Math.toIntExact` hoặc chuyển kiểu sau validation có kiểm soát.

**Câu 11.** `NegativeArraySizeException` có bắt buộc khai báo `throws` không?

**Đáp án:** Không, vì đây là unchecked exception.

**Câu 12.** Vì sao không nên chỉ viết `catch (NegativeArraySizeException)` rồi trả mảng rỗng?

**Đáp án:** Vì có thể che lỗi input hoặc tính toán; giá trị âm thường cần được nhận diện và xử lý đúng ngữ nghĩa ở nguồn tạo kích thước.

## 23. Tài liệu tham khảo chính thức

- [Java SE 17 API — `NegativeArraySizeException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NegativeArraySizeException.html): phân cấp, điều kiện phát sinh và constructors.
- [Java Language Specification 17 — §15.10.1, Array Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.10.1): cú pháp tạo mảng.
- [Java Language Specification 17 — §15.10.2, Run-Time Evaluation of Array Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.10.2): thứ tự đánh giá các dimension expressions và kiểm tra kích thước âm.
- [Java Language Specification 17 — §10, Arrays](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html): mảng, `length`, kiểu thành phần và cấu trúc đa chiều.
- [Java SE 17 API — `java.lang.reflect.Array`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Array.html): `newInstance` và các thao tác reflection với array.
- [Java SE 17 API — `ArrayList`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html): phân biệt hợp đồng initial capacity với kích thước Java array.
- [Java SE 17 API — `Math`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `addExact`, `multiplyExact`, `toIntExact` để kiểm tra overflow.
- [Java SE 17 API — `ArrayIndexOutOfBoundsException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ArrayIndexOutOfBoundsException.html): lỗi truy cập chỉ số, khác lỗi cấp phát.

**Kết luận:** `NegativeArraySizeException` xuất hiện khi **kích thước dùng để tạo Java array là số âm**, bao gồm mảng nhiều chiều và các API tạo mảng qua reflection. Độ dài `0` hợp lệ; giá trị phần tử âm cũng hợp lệ. Để tránh lỗi, hãy **xác thực nguồn dữ liệu, tính toán độ dài không tràn số, kiểm tra giới hạn cấp phát và phân biệt rõ lỗi kích thước với lỗi truy cập index**.
