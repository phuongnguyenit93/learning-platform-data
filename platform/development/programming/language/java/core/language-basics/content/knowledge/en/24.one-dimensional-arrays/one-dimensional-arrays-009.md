# Gán mảng chỉ sao chép tham chiếu — Java 17+

## 1. Bản chất của phép gán mảng

Mảng trong Java là **đối tượng (object)**. Biến có kiểu mảng như `int[]` giữ **giá trị tham chiếu** tới đối tượng ấy. Phép gán từ biến mảng này sang biến mảng khác **sao chép giá trị tham chiếu**, không tạo mảng mới và không sao chép từng phần tử.

~~~java
int[] a = {10, 20, 30};
int[] b = a;             // Cùng tham chiếu một mảng.
b[0] = 99;               // Sửa phần tử trong mảng chung.
System.out.println(a[0]);
~~~

**Exact stdout:**

~~~text
99
~~~

Mô hình:

~~~text
Biến a ───────┐
              ▼
          int[] {99, 20, 30}
              ▲
Biến b ───────┘
~~~

`a` và `b` là **hai biến khác nhau**, nhưng tại thời điểm đó trỏ **cùng đối tượng mảng**. Thuật ngữ thường dùng là **alias** (bí danh/tham chiếu cùng đối tượng).

**Quy tắc:** `b = a;` không tương đương `b = a.clone();` hoặc `b = Arrays.copyOf(a, a.length);`.

## 2. Phân biệt sửa phần tử và gán lại tham chiếu

~~~java
int[] a = {1, 2};
int[] b = a;

b[0] = 7;            // Sửa object mà cả a và b cùng trỏ.
System.out.println(java.util.Arrays.toString(a));

b = new int[]{8, 9}; // Chỉ thay tham chiếu được giữ trong biến b.
System.out.println(java.util.Arrays.toString(a));
System.out.println(java.util.Arrays.toString(b));
~~~

**Exact stdout:**

~~~text
[7, 2]
[7, 2]
[8, 9]
~~~

Hai loại thao tác:

| Thao tác | Tác động lên |
|---|---|
| `b = a;` | Tham chiếu trong **biến b**; không tạo mảng |
| `b[0] = 7;` | **Phần tử** ở mảng mà b đang chỉ tới |
| `b = new int[]{8, 9};` | Chuyển **biến b** sang đối tượng mảng mới |
| `a[0]` sau khi b chuyển sang mảng khác | Vẫn đọc mảng cũ mà a chỉ tới |

Một lần gán lại `b` không “kéo theo” `a`, dù trước đó `a == b`. **Đừng nhầm việc thay nội dung object với việc thay biến tham chiếu.**

## 3. `==` kiểm tra có phải cùng đối tượng mảng

~~~java
int[] first = {1, 2};
int[] alias = first;
int[] other = new int[]{1, 2};

System.out.println(first == alias);
System.out.println(first == other);
System.out.println(java.util.Arrays.equals(first, other));
~~~

**Exact stdout:**

~~~text
true
false
true
~~~

- Với hai tham chiếu mảng, `==` kiểm tra chúng trỏ đến **cùng object** hay không.
- Hai đối tượng mảng khác nhau vẫn có thể chứa các phần tử **bằng nhau**.
- `Arrays.equals(int[], int[])` so nội dung lần lượt từng phần tử của hai mảng một chiều `int[]`.

| Muốn kiểm tra | Dùng |
|---|---|
| Hai biến có trỏ cùng mảng? | `a == b` |
| Hai mảng `int[]` có cùng dãy giá trị? | `Arrays.equals(a, b)` |
| Muốn in các phần tử mảng `int[]` | `Arrays.toString(a)` |

`a.equals(b)` với mảng Java thông thường **không tự so sánh từng phần tử** như `Arrays.equals`. Không dùng `==` để kết luận hai mảng có nội dung bằng nhau.

## 4. Vì sao truyền mảng vào phương thức cũng có thể làm đổi dữ liệu?

Java **truyền đối số theo giá trị** (*pass-by-value*). Khi đối số là biến tham chiếu mảng, **giá trị được sao chép chính là tham chiếu**.

~~~java
static void changeElement(int[] values) {
    values[0] = 50;
}

static void rebindParameter(int[] values) {
    values = new int[]{7, 8}; // Chỉ gán lại biến tham số cục bộ.
    values[0] = 70;
}
~~~

~~~java
int[] original = {1, 2, 3};
changeElement(original);
System.out.println(java.util.Arrays.toString(original));

rebindParameter(original);
System.out.println(java.util.Arrays.toString(original));
~~~

**Exact stdout:**

~~~text
[50, 2, 3]
[50, 2, 3]
~~~

Trong `changeElement`, tham số `values` là **bản sao tham chiếu** nhưng trỏ đến **cùng mảng** như `original`; sửa `values[0]` làm thay dữ liệu caller. Trong `rebindParameter`, phép gán `values = new int[]{...}` chỉ đổi **tham số trong lần gọi**; biến `original` ở caller vẫn trỏ tới mảng cũ.

Đây **không phải pass-by-reference** theo nghĩa phương thức có thể gán lại biến tham chiếu của caller. Nếu cần caller sử dụng mảng mới, phương thức có thể **trả mảng mới**, rồi caller tự gán: `original = createNewArray(original);`.

## 5. Sao chép nội dung để tránh chia sẻ mảng `int[]`

Các cách thông dụng:

~~~java
import java.util.Arrays;

int[] original = {1, 2, 3};
int[] clone = original.clone();
int[] copy = Arrays.copyOf(original, original.length);

System.out.println(original == clone);
System.out.println(Arrays.equals(original, clone));
~~~

**Exact stdout:**

~~~text
false
true
~~~

`clone()` trên `int[]` tạo **mảng mới cùng kiểu, cùng độ dài và cùng giá trị phần tử**. `Arrays.copyOf(original, original.length)` cũng tạo mảng mới. Sau khi có bản sao:

~~~java
clone[0] = 99;
System.out.println(Arrays.toString(original));
System.out.println(Arrays.toString(clone));
~~~

**Exact stdout:**

~~~text
[1, 2, 3]
[99, 2, 3]
~~~

Vì hai mảng `int[]` giờ độc lập, sửa giá trị nguyên thủy ở bản sao không ảnh hưởng bản gốc.

| Kỹ thuật | Tạo mảng đích mới? | Độ dài đích |
|---|---|---|
| `int[] b = a;` | **Không** | Không có mảng mới |
| `int[] b = a.clone();` | **Có** | Bằng `a.length` |
| `int[] b = Arrays.copyOf(a, a.length);` | **Có** | Bằng `a.length` |
| `int[] b = Arrays.copyOf(a, 5);` | **Có** | Bằng `5` |
| `System.arraycopy(a, 0, b, 0, n)` | **Không tự tạo b** | B phải được cấp phát sẵn đủ chỗ |

Với `Arrays.copyOf(a, 5)`, nếu mảng gốc dài 3, hai vị trí thêm vào của `int[]` có giá trị mặc định `0`. Nếu độ dài mới nhỏ hơn, các phần tử vượt quá sẽ không được sao chép.

**Cẩn thận:** `clone()` hay `copyOf` vẫn là **shallow copy** khi các phần tử mảng là tham chiếu tới đối tượng có thể thay đổi. Điều này sẽ được phân biệt ngay sau đây.

## 6. Mảng chứa đối tượng: sao chép mảng không sao chép đối tượng phần tử

~~~java
StringBuilder[] first = {
    new StringBuilder("A"),
    new StringBuilder("B")
};
StringBuilder[] second = first.clone(); // Mảng ngoài khác, item tham chiếu chung.

second[0].append("!");
System.out.println(first[0]);

second[1] = new StringBuilder("C");
System.out.println(first[1]);
System.out.println(second[1]);
~~~

**Exact stdout:**

~~~text
A!
B
C
~~~

`second[0].append("!")` sửa **object `StringBuilder` được hai mảng cùng tham chiếu**, nên `first[0]` cũng hiển thị `A!`. Trái lại, `second[1] = new StringBuilder("C")` chỉ thay **tham chiếu phần tử** tại vị trí 1 của mảng `second`; `first[1]` vẫn trỏ tới `"B"`.

Vì vậy cần phân biệt hai tầng:

1. **Mảng**: `first` và `second` là hai đối tượng mảng khác nhau sau `clone()`.
2. **Object phần tử**: các phần tử tương ứng vẫn có thể là cùng tham chiếu tới một object mutable.

Muốn tách biệt cả nội dung mutable, cần tạo **bản sao của từng object phần tử**, theo hợp đồng của kiểu ấy. Với `String` (bất biến), chia sẻ tham chiếu thường không gây vấn đề thay đổi nội dung. Còn với `StringBuilder`, sửa nội dung sẽ tác động lên mọi tham chiếu tới object đó.

## 7. Khi gán `null` hoặc trả về mảng mới

~~~java
int[] a = {3, 4};
int[] b = a;
b = null;

System.out.println(b == null);
System.out.println(java.util.Arrays.toString(a));
~~~

**Exact stdout:**

~~~text
true
[3, 4]
~~~

Gán `b = null` chỉ khiến **biến b** không còn trỏ tới mảng; `a` vẫn giữ mảng đó. Nếu sau đó truy cập `b.length` hoặc `b[0]`, Java ném `NullPointerException`.

Một phương thức có thể trả một tham chiếu **mới** để caller chủ động thay biến:

~~~java
static int[] appendZero(int[] source) {
    return java.util.Arrays.copyOf(source, source.length + 1);
}
~~~

~~~java
int[] a = {3, 4};
int[] longer = appendZero(a);
System.out.println(java.util.Arrays.toString(a));
System.out.println(java.util.Arrays.toString(longer));
~~~

**Exact stdout:**

~~~text
[3, 4]
[3, 4, 0]
~~~

Mảng có độ dài cố định. `appendZero` không “nới dài” object cũ mà **cấp phát mảng khác**. Nếu caller muốn dùng mảng dài hơn cho biến `a`, cần `a = appendZero(a);`.

## 8. Chương trình Java 17+ hoàn chỉnh

Lưu đúng file **`ArrayReferenceAssignmentDemo.java`**:

~~~java
import java.util.Arrays;

public final class ArrayReferenceAssignmentDemo {
    private ArrayReferenceAssignmentDemo() {}

    static void mutateElement(int[] values) {
        values[0] = 99;
    }

    static void rebindParameter(int[] values) {
        values = new int[]{7, 8};
        values[0] = 70;
    }

    public static void main(String[] args) {
        int[] original = {10, 20, 30};
        int[] alias = original;

        System.out.println("original start=" + Arrays.toString(original));
        System.out.println("alias same array=" + (original == alias));

        alias[1] = 77;
        System.out.println("original after alias write=" + Arrays.toString(original));

        mutateElement(alias);
        System.out.println("original after mutate=" + Arrays.toString(original));

        rebindParameter(alias);
        System.out.println("original after reassign parameter="
                + Arrays.toString(original));

        int[] copy = original.clone();
        System.out.println("clone same array=" + (original == copy));
        System.out.println("clone contents equal=" + Arrays.equals(original, copy));
        copy[0] = 1;
        System.out.println("original after clone write=" + Arrays.toString(original));
        System.out.println("clone=" + Arrays.toString(copy));

        int[] extended = Arrays.copyOf(original, 5);
        System.out.println("extended=" + Arrays.toString(extended));
        System.out.println("original length=" + original.length);

        int[] destination = new int[3];
        System.arraycopy(original, 0, destination, 0, original.length);
        destination[2] = -5;
        System.out.println("arraycopy dest=" + Arrays.toString(destination));
        System.out.println("original after arraycopy dest write="
                + Arrays.toString(original));

        alias = new int[]{4, 5};
        System.out.println("alias after rebinding=" + Arrays.toString(alias));
        System.out.println("original after rebinding=" + Arrays.toString(original));
        System.out.println("same after rebinding=" + (original == alias));

        int[] missing = original;
        missing = null;
        System.out.println("null reference=" + (missing == null));
        System.out.println("original survives null=" + Arrays.toString(original));

        StringBuilder[] objects = {
            new StringBuilder("A"), new StringBuilder("B")
        };
        StringBuilder[] shallow = objects.clone();
        System.out.println("object array shared item=" + (objects[0] == shallow[0]));
        shallow[0].append("!");
        System.out.println("object after item edit=" + objects[0]);
        shallow[1] = new StringBuilder("C");
        System.out.println("object original second=" + objects[1]);
        System.out.println("object new second=" + shallow[1]);
        System.out.println("object shared array=" + (objects == shallow));
    }
}
~~~

Yêu cầu **JDK 17 trở lên**; không dùng thư viện ngoài JDK hoặc preview feature.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 ArrayReferenceAssignmentDemo.java
java -cp . ArrayReferenceAssignmentDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ArrayReferenceAssignmentDemo.java
java -cp . ArrayReferenceAssignmentDemo
~~~

### Exact expected stdout

~~~text
original start=[10, 20, 30]
alias same array=true
original after alias write=[10, 77, 30]
original after mutate=[99, 77, 30]
original after reassign parameter=[99, 77, 30]
clone same array=false
clone contents equal=true
original after clone write=[99, 77, 30]
clone=[1, 77, 30]
extended=[99, 77, 30, 0, 0]
original length=3
arraycopy dest=[99, 77, -5]
original after arraycopy dest write=[99, 77, 30]
alias after rebinding=[4, 5]
original after rebinding=[99, 77, 30]
same after rebinding=false
null reference=true
original survives null=[99, 77, 30]
object array shared item=true
object after item edit=A!
object original second=B
object new second=C
object shared array=false
~~~

Phân tích theo trình tự: `alias` ban đầu cùng tham chiếu với `original`, nên ghi qua alias và qua tham số `mutateElement` làm mảng gốc đổi. Gán lại tham số `values` trong `rebindParameter` không làm caller trỏ mảng mới. `clone()` và `copyOf` tạo các mảng `int[]` độc lập. `System.arraycopy` sao chép phần tử vào mảng đích có sẵn. Ở phần `StringBuilder[]`, clone chỉ tách **mảng**, không tạo bản sao các đối tượng phần tử mutable.

## 9. Sai lầm thường gặp

| Sai lầm | Hậu quả / cách hiểu sai | Cách đúng |
|---|---|---|
| `int[] b = a;` là copy dữ liệu | Hai biến vẫn cùng object | Dùng `a.clone()` hoặc `Arrays.copyOf` |
| `b[0] = 5` chỉ ảnh hưởng b | Khi alias, a cũng thấy thay đổi | Phân biệt biến tham chiếu với mảng |
| `b = new int[2]` khiến a đổi theo | Chỉ b trỏ sang object mới | Phép gán biến không sửa biến khác |
| `a == b` kiểm tra phần tử bằng nhau | Nó so identity | Dùng `Arrays.equals` cho nội dung `int[]` |
| `values = new int[]{...}` trong method gán lại array của caller | Tham số là bản sao tham chiếu | Trả mảng mới, caller tự gán |
| `clone()` trên `StringBuilder[]` clone từng StringBuilder | Các object phần tử vẫn có thể dùng chung | Sao chép từng object khi cần |
| `System.arraycopy` tự tạo mảng đích | Đích phải tồn tại, đủ kích thước | Khởi tạo đích trước |
| `b = null` làm a cũng null | Chỉ b bị gán lại | a vẫn có thể trỏ tới mảng cũ |

## 10. Bài tập và đáp án

**A — Dự đoán giá trị:**

~~~java
int[] a = {2, 4};
int[] b = a;
b[1] = 9;
System.out.println(a[1]);
~~~

**Đáp án:** `9`, vì hai biến trỏ cùng mảng.

**B — Gán lại biến:**

~~~java
int[] a = {2, 4};
int[] b = a;
b = new int[]{7};
System.out.println(a.length + "," + b.length);
~~~

**Đáp án:** `2,1`. Việc chuyển b sang mảng mới không đổi a.

**C — So sánh tham chiếu và nội dung:**

~~~java
int[] a = {1, 2};
int[] b = {1, 2};
System.out.println(a == b);
System.out.println(Arrays.equals(a, b));
~~~

**Đáp án:**

~~~text
false
true
~~~

**D — Phương thức nhận mảng:**

~~~java
static void edit(int[] a) {
    a[0] = 5;
    a = new int[]{8};
}
~~~

Sau `int[] x = {1}; edit(x);`, giá trị `x[0]` là **5**. Gán `a = new int[]{8}` không đổi tham chiếu biến `x` ở caller.

**E — Khi clone mảng object:** `StringBuilder[] copy = original.clone();` làm `copy == original` thành **false**, nhưng `copy[0] == original[0]` có thể **true**. Muốn thay đổi trạng thái `StringBuilder` độc lập, cần sao chép chính object đó.

## 11. Checklist và kết luận

- [ ] Hiểu biến kiểu `T[]` chứa tham chiếu tới đối tượng mảng.
- [ ] Biết phép gán `b = a` chỉ sao chép tham chiếu, không copy phần tử.
- [ ] Phân biệt sửa `b[i]` với gán lại `b`.
- [ ] Dùng `==` kiểm tra cùng object, `Arrays.equals` kiểm tra nội dung `int[]`.
- [ ] Hiểu Java truyền tham chiếu mảng **theo giá trị** khi gọi phương thức.
- [ ] Dùng `clone()`/`Arrays.copyOf` để tạo mảng nguyên thủy mới độc lập.
- [ ] Biết `System.arraycopy` sao chép vào mảng đích đã được tạo.
- [ ] Nhận diện shallow copy khi mảng chứa các object mutable.
- [ ] Không nhầm `null` của một biến với trạng thái biến khác.
- [ ] Chạy `ArrayReferenceAssignmentDemo.java` với Java 17+ và đối chiếu exact stdout.

**Kết luận:** Với mảng một chiều trong Java, `b = a` chỉ **sao chép tham chiếu**; cả hai tên biến cùng nhìn một đối tượng mảng cho tới khi một biến được gán lại. Sửa phần tử qua alias làm thay đổi dữ liệu chung. Muốn có mảng `int[]` độc lập, cần **tạo bản sao đối tượng mảng**; nếu phần tử là object mutable, có thể phải sao chép thêm chính các object phần tử.