# Chỉ số bắt đầu từ 0 và trường `length` — Mảng một chiều Java 17+

## 1. Mục tiêu

Trong Java, **mảng (*array*) đánh số phần tử từ `0`**, không phải từ `1`. Mảng có `n` phần tử thì:

- Phần tử đầu tiên nằm ở `array[0]`, nếu `n > 0`.
- Phần tử cuối cùng nằm ở `array[n - 1]`, nếu `n > 0`.
- Chỉ số hợp lệ là các số nguyên trong khoảng **`0 <= index && index < array.length`**.
- `array.length` là **trường** chứa số phần tử của mảng, **không phải phương thức**; không có cặp ngoặc `()`.
- Nếu `array.length == 0`, **không tồn tại chỉ số hợp lệ**.

Ví dụ:

~~~java
int[] numbers = {7, 0, -3, 5};
System.out.println(numbers.length); // 4
System.out.println(numbers[0]);      // 7
System.out.println(numbers[3]);      // 5
~~~

Mảng này có bốn phần tử nhưng phần tử cuối có chỉ số **3**, không phải 4.

## 2. Hình dung cấu trúc chỉ số

~~~text
int[] numbers = { 7, 0, -3, 5 };

             +----+----+----+----+
Giá trị      |  7 |  0 | -3 |  5 |
             +----+----+----+----+
Chỉ số       |  0 |  1 |  2 |  3 |
             +----+----+----+----+

numbers.length = 4
Chỉ số đầu     = 0
Chỉ số cuối    = length - 1 = 3
~~~

| Biểu thức | Kết quả | Giải thích |
|---|---:|---|
| `numbers.length` | `4` | Mảng chứa bốn phần tử |
| `numbers[0]` | `7` | Giá trị đầu tiên |
| `numbers[1]` | `0` | Giá trị thứ hai |
| `numbers[2]` | `-3` | Giá trị thứ ba |
| `numbers[3]` | `5` | Giá trị cuối |
| `numbers[-1]` | Lỗi lúc chạy | Chỉ số âm |
| `numbers[4]` | Lỗi lúc chạy | Chỉ số bằng `length` không hợp lệ |

**Ghi nhớ:** số phần tử và chỉ số cuối là hai đại lượng khác nhau. Với mảng không rỗng, **`lastIndex = length - 1`**.

## 3. Trường `length` có đặc điểm gì?

Với mọi mảng trong Java:

~~~java
int[] values = {4, 8};
int size = values.length; // Hợp lệ.
~~~

Trường `length` là một thành viên **`public final int` của kiểu mảng**. Vì là trường `final`, không được gán lại:

~~~java
// values.length = 10; // LỖI BIÊN DỊCH: không gán được final field.
// int x = values.length(); // LỖI BIÊN DỊCH: mảng không có method length().
~~~

**Độ dài cố định sau khi tạo mảng.** Muốn có mảng dài hơn hoặc ngắn hơn, phải tạo **mảng mới**, có thể dùng `Arrays.copyOf`:

~~~java
int[] oldArray = {1, 2, 3};
int[] larger = java.util.Arrays.copyOf(oldArray, 5);
System.out.println(java.util.Arrays.toString(larger));
~~~

**Exact expected stdout:**

~~~text
[1, 2, 3, 0, 0]
~~~

`larger` là mảng mới dài 5; `oldArray` vẫn dài 3. Trường `length` không đồng nghĩa với số lượng phần tử “đã được điền dữ liệu hữu ích”. Một mảng `new int[100]` luôn có `length == 100`, dù tất cả phần tử còn là 0 mặc định.

## 4. Điều kiện kiểm tra chỉ số an toàn

Trước khi dùng `array[index]` với `index` đến từ người dùng hoặc từ phép tính, hãy bảo đảm:

~~~java
static boolean validIndex(int[] array, int index) {
    return array != null
            && index >= 0
            && index < array.length;
}
~~~

Thứ tự các điều kiện có ý nghĩa:

1. Kiểm tra mảng **khác null** trước.
2. Chặn chỉ số âm.
3. Chặn chỉ số **bằng hoặc lớn hơn `length`**.

Toán tử `&&` **ngắn mạch**: nếu `array == null` thì không truy cập `array.length`. Đừng chỉ kiểm tra `index < array.length` vì `index = -1` vẫn thỏa điều kiện đó đối với mảng không rỗng.

**Ví dụ kết quả khi mảng dài 4:**

| `index` | `index >= 0` | `index < 4` | Hợp lệ |
|---:|---|---|---|
| `-1` | false | true | Không |
| `0` | true | true | Có |
| `3` | true | true | Có |
| `4` | true | false | Không |
| `5` | true | false | Không |

Có thể để runtime ném ngoại lệ tự nhiên nếu truy cập chỉ số không hợp lệ là lỗi lập trình; nhưng với chỉ số do người dùng cung cấp, xác thực đầu vào thường giúp báo lỗi rõ ràng hơn.

## 5. Lỗi vượt chỉ số `ArrayIndexOutOfBoundsException`

Các biểu thức sau **biên dịch được**, nhưng gây ngoại lệ lúc chạy:

~~~java
int[] numbers = {7, 0, -3, 5};

// System.out.println(numbers[-1]); // ArrayIndexOutOfBoundsException.
// System.out.println(numbers[4]);  // ArrayIndexOutOfBoundsException.
~~~

`ArrayIndexOutOfBoundsException` là ngoại lệ **runtime** do chỉ số âm hoặc chỉ số từ `length` trở lên. Java thực hiện kiểm tra biên để bảo vệ bộ nhớ của mảng.

Ví dụ bắt lỗi minh họa:

~~~java
try {
    System.out.println(numbers[numbers.length]);
} catch (ArrayIndexOutOfBoundsException ex) {
    System.out.println("index == length is invalid");
}
~~~

**Exact expected stdout:**

~~~text
index == length is invalid
~~~

**Không dùng bắt ngoại lệ để thay vòng lặp đúng biên.** Trong code thông thường, sửa `i <= numbers.length` thành `i < numbers.length`; điều đó rõ ràng hơn và tránh phát sinh ngoại lệ lặp đi lặp lại.

## 6. Duyệt từ đầu đến cuối bằng `for`

Cách phổ biến:

~~~java
int[] data = {7, 0, -3, 5};
for (int i = 0; i < data.length; i++) {
    System.out.println("index=" + i + ",value=" + data[i]);
}
~~~

**Exact expected stdout:**

~~~text
index=0,value=7
index=1,value=0
index=2,value=-3
index=3,value=5
~~~

Phân tích ba thành phần:

- **Khởi tạo:** `int i = 0`, bắt đầu từ chỉ số đầu.
- **Điều kiện:** `i < data.length`, chỉ truy cập khi chỉ số còn hợp lệ.
- **Cập nhật:** `i++`, chuyển sang phần tử kế tiếp.

Nếu dùng `i <= data.length`, body sẽ chạy khi `i == 4`; biểu thức `data[4]` vượt biên. Đây là lỗi **off-by-one** điển hình.

### Duyệt ngược

~~~java
for (int i = data.length - 1; i >= 0; i--) {
    System.out.println(data[i]);
}
~~~

**Exact expected stdout:**

~~~text
5
-3
0
7
~~~

Với mảng rỗng, `data.length - 1` là `-1`, điều kiện `i >= 0` false ngay nên body không chạy.

## 7. Mảng rỗng: `length == 0`

~~~java
int[] empty = new int[0];
System.out.println(empty.length);
~~~

**Exact expected stdout:**

~~~text
0
~~~

Mảng rỗng là một **mảng hợp lệ**, khác với `null`:

- `empty.length == 0`.
- Không có `empty[0]`; truy cập sẽ ném `ArrayIndexOutOfBoundsException`.
- `for (int i = 0; i < empty.length; i++)` có **0 lượt**.
- `for (int value : empty)` cũng có **0 lượt**.
- Muốn lấy phần tử đầu hoặc cuối, phải kiểm tra `empty.length > 0` trước.

~~~java
if (empty.length == 0) {
    System.out.println("EMPTY");
} else {
    System.out.println(empty[0]);
}
~~~

**Exact expected stdout:**

~~~text
EMPTY
~~~

**Không giả định** mảng luôn có ít nhất một phần tử chỉ vì biến được khai báo `int[]`.

## 8. `array.length`, `String.length()` và `List.size()` khác nhau

Dễ nhầm ba cách lấy kích thước:

| Đối tượng | Cách viết | Bản chất |
|---|---|---|
| Mảng `int[]`, `String[]`, `Object[]` | `array.length` | **Trường** `int` của mảng |
| Chuỗi `String` | `text.length()` | **Phương thức** của String |
| `List` | `list.size()` | **Phương thức** của List |

~~~java
int[] numbers = {1, 2, 3};
String text = "Java";
java.util.List<String> words = java.util.List.of("a", "b");

System.out.println(numbers.length);
System.out.println(text.length());
System.out.println(words.size());
~~~

**Exact expected stdout:**

~~~text
3
4
2
~~~

**Lưu ý về `String`:** `String.length()` đo số **đơn vị mã UTF-16**, không nhất thiết là số ký tự người dùng nhìn thấy. Đó là quy tắc của String, **khác hoàn toàn** việc đếm số phần tử mảng qua `array.length`.

Dù các phép truy cập kích thước khác nhau về cú pháp, khi duyệt bằng chỉ số vẫn cần bảo đảm cận dưới 0 và cận trên phù hợp với cấu trúc dữ liệu.

## 9. Chương trình Java 17+ tự chứa, chạy bằng CLI

Tạo file đúng tên **`ArrayIndexLengthDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.List;

public final class ArrayIndexLengthDemo {
    private ArrayIndexLengthDemo() {}

    static boolean validIndex(int[] array, int index) {
        return array != null && index >= 0 && index < array.length;
    }

    static int sum(int[] array) {
        int total = 0;
        for (int i = 0; i < array.length; i++) {
            total += array[i];
        }
        return total;
    }

    public static void main(String[] args) {
        int[] numbers = {7, 0, -3, 5};

        System.out.println("length=" + numbers.length);
        System.out.println("first=" + numbers[0]);
        System.out.println("last=" + numbers[numbers.length - 1]);

        for (int i = 0; i < numbers.length; i++) {
            System.out.println("index=" + i + ",value=" + numbers[i]);
        }
        System.out.println("sum=" + sum(numbers));

        System.out.println("valid -1=" + validIndex(numbers, -1));
        System.out.println("valid 0=" + validIndex(numbers, 0));
        System.out.println("valid 3=" + validIndex(numbers, 3));
        System.out.println("valid 4=" + validIndex(numbers, 4));
        System.out.println("valid null=" + validIndex(null, 0));

        try {
            System.out.println(numbers[-1]);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("negative index=OUT_OF_BOUNDS");
        }
        try {
            System.out.println(numbers[numbers.length]);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("length index=OUT_OF_BOUNDS");
        }

        int[] zeros = new int[3];
        System.out.println("new array=" + Arrays.toString(zeros));
        int[] larger = Arrays.copyOf(numbers, 6);
        System.out.println("copied length=" + larger.length);
        System.out.println("copied=" + Arrays.toString(larger));
        System.out.println("original length=" + numbers.length);

        int[] empty = new int[0];
        System.out.println("empty length=" + empty.length);
        int emptyVisits = 0;
        for (int i = 0; i < empty.length; i++) {
            emptyVisits++;
        }
        System.out.println("empty visits=" + emptyVisits);

        int[] absent = null;
        System.out.println("null reference=" + (absent == null));

        String text = "Java";
        List<String> words = List.of("A", "B");
        System.out.println("string length()=" + text.length());
        System.out.println("list size()=" + words.size());

        int[][] rows = {{1, 2}, {3}, {}};
        System.out.println("row count=" + rows.length);
        for (int row = 0; row < rows.length; row++) {
            System.out.println("row " + row + " length=" + rows[row].length);
        }

        for (int i = numbers.length - 1; i >= 0; i--) {
            System.out.println("reverse index=" + i + ",value=" + numbers[i]);
        }
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên, terminal ở thư mục có file. Không dùng Maven, Gradle hay preview feature.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 ArrayIndexLengthDemo.java
java -cp . ArrayIndexLengthDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ArrayIndexLengthDemo.java
java -cp . ArrayIndexLengthDemo
~~~

### Exact expected stdout

~~~text
length=4
first=7
last=5
index=0,value=7
index=1,value=0
index=2,value=-3
index=3,value=5
sum=9
valid -1=false
valid 0=true
valid 3=true
valid 4=false
valid null=false
negative index=OUT_OF_BOUNDS
length index=OUT_OF_BOUNDS
new array=[0, 0, 0]
copied length=6
copied=[7, 0, -3, 5, 0, 0]
original length=4
empty length=0
empty visits=0
null reference=true
string length()=4
list size()=2
row count=3
row 0 length=2
row 1 length=1
row 2 length=0
reverse index=3,value=5
reverse index=2,value=-3
reverse index=1,value=0
reverse index=0,value=7
~~~

**Đối chiếu:** mảng `numbers` có `length == 4`, nhưng chỉ số cuối là 3; tổng bằng 9. Chỉ số -1 và 4 không hợp lệ; `new int[3]` có ba số 0 mặc định. `Arrays.copyOf` tạo mảng mới dài 6 và giữ nguyên độ dài mảng gốc. Mảng rỗng không có lượt duyệt; tham chiếu `null` khác mảng rỗng. Các hàng mảng hai chiều có `length` riêng.

## 10. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Cho chỉ số bắt đầu từ 1 | Bỏ qua phần tử đầu | Bắt đầu `i = 0` |
| Cho chỉ số cuối bằng `length` | `ArrayIndexOutOfBoundsException` | Cuối là `length - 1` khi mảng không rỗng |
| `i <= array.length` khi truy cập `array[i]` | Vượt biên tại `i == length` | `i < array.length` |
| Chỉ kiểm tra `index < length` | Chỉ số âm vẫn lọt | Thêm `index >= 0` |
| Dùng `array.length()` | Lỗi biên dịch | `array.length` |
| Dùng `array.length = n` | Lỗi vì trường final | Tạo mảng mới |
| Lấy `array[0]` khi `length == 0` | Vượt biên | Kiểm tra mảng không rỗng |
| Dùng `array.length` khi `array == null` | `NullPointerException` | Kiểm tra null trước |
| Đồng nhất `length` với số phần tử không rỗng | Sai nghĩa độ dài | `length` là số vị trí được cấp phát |
| Nhầm `String.length()` với `array.length` | Lỗi cú pháp/kiểu | Nhớ trường của array và method của String |
| Dùng `rows.length` làm số cột mọi hàng | Sai với jagged array | `rows[row].length` |
| Bắt ngoại lệ như cách duyệt mảng | Code khó đọc, tốn chi phí lỗi | Kiểm tra cận trước |

## 11. Bài tập có đáp án

### Bài A — Chỉ số hợp lệ

Cho `int[] a = {3, 6, 9, 12, 15};`. Hỏi `a.length`, chỉ số đầu, chỉ số cuối và `a[4]`?

**Đáp án:** `length = 5`, chỉ số đầu `0`, cuối `4`, `a[4] = 15`. `a[5]` không hợp lệ.

### Bài B — Sửa lỗi off-by-one

~~~java
int[] a = {2, 4, 6};
// Sai: for (int i = 0; i <= a.length; i++) System.out.println(a[i]);
~~~

**Đáp án:**

~~~java
for (int i = 0; i < a.length; i++) {
    System.out.println(a[i]);
}
~~~

**Expected stdout:**

~~~text
2
4
6
~~~

### Bài C — Mảng rỗng

~~~java
int[] a = {};
System.out.println(a.length);
~~~

**Đáp án:** in `0`. Không thể đọc `a[0]`, vì mảng không có phần tử.

### Bài D — Kiểm tra chỉ số âm

Vì sao `if (index < a.length) ...` chưa đủ?

**Đáp án:** khi `index = -1` và `a.length = 3`, điều kiện vẫn true nhưng `a[-1]` không hợp lệ. Cần `index >= 0 && index < a.length`.

### Bài E — Phân biệt ba cách đọc kích thước

Hoàn thành các lệnh lấy kích thước từ `int[] a`, `String s`, `List<String> list`.

**Đáp án:**

~~~java
int arraySize = a.length;
int stringUnits = s.length();
int listSize = list.size();
~~~

### Bài F — Tạo mảng mới dài hơn

~~~java
int[] a = {1, 2};
int[] b = Arrays.copyOf(a, 4);
System.out.println(Arrays.toString(a));
System.out.println(Arrays.toString(b));
~~~

**Đáp án:**

~~~text
[1, 2]
[1, 2, 0, 0]
~~~

Mảng `a` không tăng độ dài; `b` là mảng mới.

## 12. Checklist và kết luận

- [ ] Biết `array[0]` là phần tử đầu tiên.
- [ ] Nhớ chỉ số hợp lệ là `0 <= i && i < array.length`.
- [ ] Biết `length - 1` là chỉ số cuối **chỉ khi mảng không rỗng**.
- [ ] Phân biệt số phần tử `length` và giá trị tại chỉ số.
- [ ] Sử dụng `array.length` như một **trường**, không gọi `length()`.
- [ ] Biết không thể đổi `length` sau khi tạo mảng; phải tạo mảng mới.
- [ ] Duyệt đúng biên bằng `for (int i=0; i<a.length; i++)`.
- [ ] Phân biệt `ArrayIndexOutOfBoundsException` với `NullPointerException`.
- [ ] Biết mảng rỗng có `length == 0` và không có chỉ số hợp lệ.
- [ ] Phân biệt `array.length`, `String.length()` và `List.size()`.
- [ ] Chạy `ArrayIndexLengthDemo.java` bằng Java 17+, đối chiếu từng dòng stdout.

**Kết luận:** Trong mảng Java, `length` cho biết **bao nhiêu phần tử**, còn chỉ số bắt đầu từ **0**. Vì thế cận trên hợp lệ là `length - 1`, không phải `length`. Hãy dùng điều kiện `0 <= index && index < array.length`, xử lý mảng rỗng/null đúng cách và nhớ `length` là trường cố định của mảng.