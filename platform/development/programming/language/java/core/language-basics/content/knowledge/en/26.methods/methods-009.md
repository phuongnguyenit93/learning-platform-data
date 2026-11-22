# Varargs và mối quan hệ với mảng — Java 17+

## 1. Varargs là gì?

**Varargs** (*variable-length arguments*) cho phép một phương thức nhận **số lượng đối số thay đổi**. Ký hiệu là ba dấu chấm `...` sau kiểu phần tử:

~~~java
static int sum(int... numbers) {
    int total = 0;
    for (int number : numbers) {
        total += number;
    }
    return total;
}
~~~

Có thể gọi cùng phương thức bằng các cách sau:

~~~java
System.out.println(sum());                  // Không truyền phần tử nào.
System.out.println(sum(7));                 // Một phần tử.
System.out.println(sum(1, 2, 3));           // Ba phần tử.
System.out.println(sum(new int[]{4, 5}));   // Truyền mảng int[] có sẵn.
~~~

**Exact expected stdout:**

~~~text
0
7
6
9
~~~

**Điểm cốt lõi:** trong thân phương thức, `numbers` có **kiểu `int[]`**, nên dùng được `numbers.length`, `numbers[i]` và enhanced `for` như với một mảng bình thường. Varargs chủ yếu là cú pháp tiện lợi cho **người gọi**, không phải một cấu trúc lưu trữ dữ liệu mới.

## 2. So sánh `int...` và `int[]`

| Định nghĩa | `sum()` | `sum(1, 2)` | `sum(new int[]{1, 2})` |
|---|---|---|---|
| `static int sum(int... a)` | Hợp lệ | Hợp lệ | Hợp lệ |
| `static int sum(int[] a)` | Không hợp lệ | Không hợp lệ | Hợp lệ |

Bên trong phương thức, hai khai báo đều cho tham số kiểu `int[]`. Tuy nhiên, chỉ dạng `int...` cho phép trình biên dịch tạo mảng **từ danh sách nhiều đối số** ở vị trí gọi.

~~~java
static void inspect(int... data) {
    System.out.println("length=" + data.length);
}
~~~

~~~java
inspect();               // length=0
inspect(10, 20);         // length=2
inspect(new int[]{30});  // length=1
~~~

Không được khai báo hai phương thức chỉ khác `int[]` và `int...` cùng tên trong cùng lớp: về **chữ ký sau biên dịch**, chúng là cùng kiểu tham số mảng.

~~~java
// Không thể cùng tồn tại:
// static void f(int[] a) { }
// static void f(int... a) { } // Trùng chữ ký f(int[]).
~~~

## 3. Varargs phải là tham số cuối cùng

Varargs có thể đứng sau những tham số cố định:

~~~java
static void log(String prefix, int... values) {
    System.out.println(prefix + ":" + values.length);
}
~~~

~~~java
log("empty");       // empty:0
log("count", 1, 2); // count:2
~~~

Các quy tắc cú pháp:

- Mỗi khai báo phương thức có **tối đa một** tham số varargs.
- Tham số varargs phải là **tham số cuối cùng**.
- `static void bad(int... a, String tag)` không hợp lệ vì sau varargs còn tham số khác.
- `static void bad(int... a, String... b)` cũng không hợp lệ.

Số lượng tham số **cố định** trước varargs vẫn phải được truyền đúng: `log()` không hợp lệ vì thiếu `prefix`, còn `log("ok")` hợp lệ và tạo dãy số rỗng.

## 4. Mảng tạm và mảng có sẵn: khác biệt về tham chiếu

Với lời gọi `sum(1, 2, 3)`, Java có thể coi ba đối số đó như nội dung của **một mảng `int[]` mới** để truyền vào tham số varargs. Caller không có biến nào trỏ tới mảng tạm ấy.

Với lời gọi `sum(existing)` khi `existing` là `int[]`, Java truyền **tham chiếu mảng có sẵn**; nó không tự sao chép mảng.

~~~java
static void changeFirst(int... data) {
    if (data.length > 0) {
        data[0] = 99;
    }
}

int[] original = {2, 3, 4};
changeFirst(original);
System.out.println(java.util.Arrays.toString(original));
changeFirst(8, 9);
System.out.println(java.util.Arrays.toString(original));
~~~

**Exact expected stdout:**

~~~text
[99, 3, 4]
[99, 3, 4]
~~~

Lời gọi đầu sửa **chính phần tử mảng của caller**. Lời gọi thứ hai sửa mảng được tạo cho danh sách đối số `8, 9`, không làm `original` thay đổi. Java truyền đối số **theo giá trị**, nhưng với mảng giá trị được truyền là **tham chiếu tới object mảng**.

Nếu không muốn phương thức làm đổi mảng được truyền vào, hãy không sửa phần tử hoặc chủ động sao chép bằng `Arrays.copyOf`.

## 5. `sum()` tạo mảng rỗng; truyền null thì khác

Không truyền đối số varargs:

~~~java
sum(); // numbers là int[] không null, độ dài 0.
~~~

Khác với cố ý truyền tham chiếu mảng `null`:

~~~java
sum((int[]) null); // Truyền null làm đối số mảng.
~~~

Nếu thân phương thức duyệt `numbers` hay truy cập `numbers.length` ngay, trường hợp thứ hai có thể gây `NullPointerException`. Một API có thể chọn từ chối null rõ ràng:

~~~java
static int checkedSum(int... numbers) {
    if (numbers == null) {
        throw new IllegalArgumentException("null array");
    }
    int result = 0;
    for (int n : numbers) result += n;
    return result;
}
~~~

| Lời gọi | Trạng thái của `numbers` |
|---|---|
| `checkedSum()` | Mảng rỗng, `length == 0` |
| `checkedSum(1, 2)` | Mảng chứa `1, 2` |
| `checkedSum(new int[0])` | Mảng rỗng đã có |
| `checkedSum((int[]) null)` | Chính là `null`; ví dụ ném `IllegalArgumentException` |

**Lưu ý:** `null` có thể làm lời gọi varargs kiểu tham chiếu trở nên khó phân giải hoặc xuất hiện cảnh báo; dùng ép kiểu mảng rõ ràng khi chủ đích là truyền mảng null.

## 6. Varargs với mảng nhiều chiều

Kiểu phần tử của varargs có thể là **một mảng**:

~~~java
static void showRows(int[]... rows) {
    System.out.println("rows=" + rows.length);
    for (int[] row : rows) {
        System.out.println(java.util.Arrays.toString(row));
    }
}
~~~

Hai cách gọi hợp lệ:

~~~java
showRows(new int[]{1, 2}, new int[]{3});
int[][] matrix = {{4}, {5, 6}};
showRows(matrix);
~~~

**Exact expected stdout:**

~~~text
rows=2
[1, 2]
[3]
rows=2
[4]
[5, 6]
~~~

Ở đây `int[]... rows` có kiểu thực tế **`int[][]`** bên trong phương thức. Mỗi phần tử `row` là `int[]`. Nếu hàng có thể null, cần kiểm tra riêng trước khi truy cập `row.length`.

## 7. Nạp chồng phương thức với varargs

~~~java
static String choose(int value) {
    return "single";
}

static String choose(int... values) {
    return "varargs count=" + values.length;
}
~~~

~~~java
System.out.println(choose(4));
System.out.println(choose(4, 5));
System.out.println(choose());
~~~

**Exact expected stdout:**

~~~text
single
varargs count=2
varargs count=0
~~~

Với một đối số `int`, overload cố định `choose(int)` được chọn trước dạng varargs có thể áp dụng. Với không đối số hoặc hai đối số, chỉ overload varargs trong cặp trên áp dụng.

**Cẩn thận:** nhiều overload varargs gần giống nhau có thể tạo lời gọi **mơ hồ** (*ambiguous*). Ví dụ nếu có cả `f(String...)` và `f(Integer...)`, lời gọi `f()` không xác định được overload nào. Tránh thiết kế overload varargs khó đoán chỉ để rút ngắn cách gọi.

## 8. Lưu ý với varargs kiểu tham chiếu hoặc generic

Với `String... words`, tham số trong thân là `String[]`; mỗi phần tử có thể là null nên code dùng `words[i].length()` cần kiểm tra null ở phần tử.

Với varargs chứa kiểu generic, ví dụ `List<String>... groups`, Java có thể phát cảnh báo về **heap pollution** vì mảng và generic có những quy tắc kiểu khác nhau. Không bỏ qua cảnh báo một cách máy móc hoặc tự thêm `@SafeVarargs` khi chưa chắc phương thức an toàn; với Java cơ bản nên ưu tiên kiểu varargs đơn giản như `int...` và `String...`.

Nếu đối số nhiều và dữ liệu đã nằm sẵn trong mảng, truyền mảng trực tiếp vừa rõ ràng vừa tránh tạo thêm mảng từ danh sách phần tử tại lời gọi.

## 9. Chương trình Java 17+ chạy bằng CLI

Tạo file đúng tên **`VarargsArrayDemo.java`**:

~~~java
import java.util.Arrays;

public final class VarargsArrayDemo {
    private VarargsArrayDemo() {}

    static int sum(int... values) {
        if (values == null) {
            throw new IllegalArgumentException("null array");
        }
        int total = 0;
        for (int value : values) total += value;
        return total;
    }

    static String describe(String title, String... names) {
        return title + " count=" + names.length
                + " " + Arrays.toString(names);
    }

    static void changeFirst(int... values) {
        if (values != null && values.length > 0) {
            values[0] = 99;
        }
    }

    static void showRows(int[]... rows) {
        System.out.println("row count=" + rows.length);
        for (int i = 0; i < rows.length; i++) {
            System.out.println("row " + i + "=" + Arrays.toString(rows[i]));
        }
    }

    static String choose(int value) {
        return "single";
    }

    static String choose(int... values) {
        return "varargs count=" + values.length;
    }

    public static void main(String[] args) {
        System.out.println("sum empty=" + sum());
        System.out.println("sum one=" + sum(7));
        System.out.println("sum many=" + sum(1, 2, 3));

        int[] existing = {2, 3, 4};
        System.out.println("array before=" + Arrays.toString(existing));
        System.out.println("sum array=" + sum(existing));
        changeFirst(existing);
        System.out.println("array after change=" + Arrays.toString(existing));
        changeFirst(8, 9);
        System.out.println("array after temporary=" + Arrays.toString(existing));

        System.out.println(describe("empty"));
        System.out.println(describe("names", "Lan", "Minh"));
        String[] savedNames = {"An", "Binh"};
        System.out.println(describe("array", savedNames));

        showRows(new int[]{1, 2}, new int[]{3});
        int[][] matrix = {{4}, {5, 6}};
        showRows(matrix);

        System.out.println("choose one=" + choose(4));
        System.out.println("choose two=" + choose(4, 5));
        System.out.println("choose empty=" + choose());

        try {
            sum((int[]) null);
        } catch (IllegalArgumentException ex) {
            System.out.println("null input=" + ex.getMessage());
        }
    }
}
~~~

**Bash (Linux/macOS), JDK 17+:**

~~~bash
javac --release 17 -encoding UTF-8 VarargsArrayDemo.java
java -cp . VarargsArrayDemo
~~~

**PowerShell (Windows), JDK 17+:**

~~~powershell
javac --release 17 -encoding UTF-8 .\VarargsArrayDemo.java
java -cp . VarargsArrayDemo
~~~

### Exact expected stdout

~~~text
sum empty=0
sum one=7
sum many=6
array before=[2, 3, 4]
sum array=9
array after change=[99, 3, 4]
array after temporary=[99, 3, 4]
empty count=0 []
names count=2 [Lan, Minh]
array count=2 [An, Binh]
row count=2
row 0=[1, 2]
row 1=[3]
row count=2
row 0=[4]
row 1=[5, 6]
choose one=single
choose two=varargs count=2
choose empty=varargs count=0
null input=null array
~~~

## 10. Lỗi thường gặp và bài tập

| Sai lầm | Nguyên nhân | Cách sửa |
|---|---|---|
| Nghĩ `int...` là kiểu dữ liệu mới | Trong thân nó là `int[]` | Dùng `.length`, `[i]`, vòng duyệt mảng |
| Đặt tham số sau varargs | Varargs phải đứng cuối | `f(String label, int... values)` |
| Có hai varargs trong một phương thức | Cú pháp không hợp lệ | Chỉ dùng một tham số varargs |
| Khai báo đồng thời `f(int[])` và `f(int...)` | Trùng chữ ký | Giữ một định nghĩa |
| Cho rằng `f(existingArray)` tự copy mảng | Truyền giá trị tham chiếu mảng cũ | Tránh mutate hoặc sao chép rõ ràng |
| Nghĩ `f()` tạo tham số null | Lời gọi varargs rỗng tạo mảng dài 0 | Phân biệt `f((int[]) null)` |
| Nhầm `int[]...` với `int...` | Kiểu phần tử khác nhau | `int[]...` tương ứng `int[][]` |
| Lạm dụng overload varargs | Dễ mơ hồ ở lời gọi | Dùng tên/phân loại tham số rõ ràng |

**Bài A.** Với `static int count(String... words) { return words.length; }`, `count()` trả bao nhiêu? **0**; `count("a", "b")` trả **2**; `count(new String[]{"a"})` trả **1**.

**Bài B.** Vì sao không định nghĩa cùng lúc `print(int[] a)` và `print(int... a)`? Vì Java coi hai dạng có **cùng kiểu tham số mảng**, gây trùng chữ ký phương thức.

**Bài C.** `changeFirst(existing)` có sửa mảng caller không? **Có**, nếu mảng có phần tử và method gán vào `values[0]`. Với danh sách đối số riêng `changeFirst(1, 2)`, caller không có mảng gốc tương ứng để quan sát.

**Bài D.** Nếu `int[][] a = {{1}, {2, 3}}`, `showRows(a)` nhận tham số kiểu gì? **`int[][]`**, vì khai báo `int[]... rows` là varargs của `int[]`.

## 11. Checklist và kết luận

- [ ] Biết cú pháp `T... values` và varargs phải là tham số cuối.
- [ ] Hiểu trong thân phương thức, varargs chính là `T[]`.
- [ ] Gọi được với 0, 1, nhiều đối số hoặc với mảng có sẵn.
- [ ] Phân biệt mảng tạm từ danh sách đối số với mảng caller truyền trực tiếp.
- [ ] Không tự giả định varargs luôn sao chép mảng được truyền.
- [ ] Phân biệt mảng rỗng và giá trị null truyền chủ đích.
- [ ] Biết `int[]...` tương ứng kiểu tham số `int[][]`.
- [ ] Nhận diện trường hợp overload varargs mơ hồ.
- [ ] Chạy `VarargsArrayDemo.java` trên JDK 17+ và đối chiếu exact stdout.

**Kết luận:** Varargs `T...` làm cách **gọi** phương thức linh hoạt hơn, nhưng trong **thân** nó vẫn là mảng `T[]`. Khi truyền danh sách phần tử, Java tạo mảng chứa các giá trị đó; khi truyền một mảng có sẵn, phương thức nhận tham chiếu tới **chính mảng ấy**, nên thay đổi phần tử có thể ảnh hưởng caller.