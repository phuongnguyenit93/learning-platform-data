# `ArrayIndexOutOfBoundsException` và `NegativeArraySizeException` — Java 17+

## 1. Hai lỗi mảng khác nhau

Khi làm việc với mảng một chiều trong Java, cần phân biệt **lỗi truy cập phần tử** và **lỗi cấp phát mảng**:

| Ngoại lệ | Phát sinh khi nào? | Ví dụ |
|---|---|---|
| `ArrayIndexOutOfBoundsException` | Đọc/ghi phần tử tại chỉ số ngoài miền `0..length-1` | `a[-1]`, `a[a.length]` |
| `NegativeArraySizeException` | Cấp phát mảng với kích thước âm | `new int[-2]` |
| `NullPointerException` (liên quan) | Truy cập mảng qua tham chiếu `null` | `a.length` với `a == null` |

Cả hai ngoại lệ chính đều là **unchecked exceptions** (các lớp con của `RuntimeException`), không bắt buộc khai báo `throws` hoặc `catch`. Chúng phát sinh **khi chạy**; nhiều biểu thức liên quan vẫn biên dịch hợp lệ.

Ví dụ độc lập:

~~~java
int[] a = {10, 20, 30};

System.out.println(a.length); // 3
System.out.println(a[0]);     // 10
System.out.println(a[2]);     // 30

// a[3] hoặc a[-1]: chỉ số không hợp lệ.
// new int[-2]: kích thước cấp phát không hợp lệ.
~~~

**Quy tắc nhớ:** *Đã có mảng, truy cập sai vị trí → index out of bounds; đang tạo mảng, kích thước âm → negative array size.*

## 2. `ArrayIndexOutOfBoundsException` khi đọc

~~~java
int[] numbers = {4, 8, 12};

// System.out.println(numbers[3]);
// Khi chạy: ArrayIndexOutOfBoundsException.
~~~

Java kiểm tra miền chỉ số lúc truy cập. Việc ghi `numbers[3]` có thể **qua biên dịch** vì chỉ số là `int`, nhưng thất bại lúc thực thi do mảng chỉ có ba phần tử.

Minh họa có bắt ngoại lệ, không phụ thuộc thông điệp lỗi của JDK:

~~~java
try {
    System.out.println(numbers[3]);
} catch (ArrayIndexOutOfBoundsException ex) {
    System.out.println("READ_OUT_OF_BOUNDS");
}
~~~

**Exact stdout:**

~~~text
READ_OUT_OF_BOUNDS
~~~

Thông điệp `ex.getMessage()` có thể phụ thuộc phiên bản và ngữ cảnh; ví dụ dùng một thông báo tự kiểm soát để bảo đảm đầu ra dự kiến chính xác.

## 3. `ArrayIndexOutOfBoundsException` khi ghi

Không chỉ đọc, **ghi** vào chỉ số sai cũng vượt biên:

~~~java
int[] numbers = {4, 8, 12};

try {
    numbers[-1] = 99;
} catch (ArrayIndexOutOfBoundsException ex) {
    System.out.println("WRITE_OUT_OF_BOUNDS");
}
~~~

**Exact stdout:**

~~~text
WRITE_OUT_OF_BOUNDS
~~~

Lệnh gán không tạo vị trí mới. Mảng Java có **độ dài cố định**: `numbers[numbers.length] = 99` không có nghĩa là “thêm phần tử vào cuối”.

Muốn bổ sung phần tử, hãy tạo mảng mới với kích thước phù hợp (ví dụ `Arrays.copyOf`) hoặc chọn `ArrayList` nếu nghiệp vụ cần danh sách có kích thước linh hoạt.

## 4. Lỗi `NegativeArraySizeException` khi tạo mảng

Khi cấp phát bằng `new`, biểu thức kích thước phải là số nguyên **không âm**:

~~~java
int[] empty = new int[0]; // Hợp lệ: length = 0.
int[] data = new int[3];  // Hợp lệ: length = 3.

// int[] bad = new int[-2]; // Biên dịch được, ném NegativeArraySizeException khi chạy.
~~~

Minh họa:

~~~java
try {
    int requestedLength = -2;
    int[] bad = new int[requestedLength];
    System.out.println(bad.length);
} catch (NegativeArraySizeException ex) {
    System.out.println("NEGATIVE_ARRAY_SIZE");
}
~~~

**Exact stdout:**

~~~text
NEGATIVE_ARRAY_SIZE
~~~

Đây là lỗi của **tham số kích thước khi cấp phát**, không phải lỗi đọc chỉ số. Mảng dài 0 được phép tạo; chỉ số âm **không bao giờ** hợp lệ khi truy cập.

## 5. Kiểm tra trước khi cấp phát mảng

Một API nhận kích thước từ bên ngoài nên quyết định chính sách dữ liệu âm:

~~~java
static int[] createChecked(int size) {
    if (size < 0) {
        throw new IllegalArgumentException("size must be >= 0");
    }
    return new int[size];
}
~~~

Ưu điểm: thay vì để `NegativeArraySizeException` phát sinh từ nơi cấp phát, API nêu rõ yêu cầu đầu vào bằng `IllegalArgumentException`. Đây là **quyết định thiết kế API**, không phải luật bắt buộc phải chuyển mọi lỗi sang `IllegalArgumentException`.

Ví dụ:

~~~java
System.out.println(createChecked(0).length); // 0
System.out.println(createChecked(3).length); // 3
~~~

Khi gọi `createChecked(-1)`, phương thức ném `IllegalArgumentException` với thông điệp đã định.

**Quan trọng:** kích thước không âm chưa bảo đảm cấp phát thành công. Yêu cầu mảng quá lớn có thể dẫn tới `OutOfMemoryError`; đó là vấn đề khác, không phải `NegativeArraySizeException`. Không cấp phát thử những mảng cực lớn chỉ để kiểm tra trên máy học.

Khi đã xác định được hai điểm phát sinh lỗi, kiểm tra dữ liệu đầu vào là cách phòng ngừa lỗi thường dùng:

## 6. Kiểm tra biên trước khi đọc/ghi

Hàm đọc trả nhãn thay vì truy cập sai:

~~~java
static String readSafely(int[] array, int index) {
    if (array == null) {
        return "NULL_ARRAY";
    }
    if (index < 0 || index >= array.length) {
        return "BAD_INDEX";
    }
    return "VALUE:" + array[index];
}
~~~

Với mảng `{10, 20, 30}`:

| Thao tác | Giá trị trả |
|---|---|
| `readSafely(a, -1)` | `BAD_INDEX` |
| `readSafely(a, 0)` | `VALUE:10` |
| `readSafely(a, 2)` | `VALUE:30` |
| `readSafely(a, 3)` | `BAD_INDEX` |
| `readSafely(null, 0)` | `NULL_ARRAY` |

Trong ứng dụng thực tế, bạn có thể trả `OptionalInt`, một kết quả nghiệp vụ có cấu trúc hoặc ném `IllegalArgumentException` tùy hợp đồng API. Chuỗi trong ví dụ chỉ nhằm quan sát luồng dễ dàng.

**Không đủ:** `index < array.length`, vì `-1 < length` vẫn true với mảng không rỗng. Cần cả **cận dưới** `index >= 0` lẫn **cận trên** `index < length`.

## 7. Hai ngoại lệ phát sinh ở hai bước khác nhau

~~~mermaid
flowchart TD
    A["Thao tác với mảng"] --> B{"Đang tạo mảng mới?"}
    B -- "Có" --> C{"size < 0?"}
    C -- "Có" --> D["NegativeArraySizeException"]
    C -- "Không" --> E["Tạo mảng; cần đủ bộ nhớ"]
    B -- "Không, đang đọc/ghi" --> F{"array == null?"}
    F -- "Có" --> G["NullPointerException"]
    F -- "Không" --> H{"index < 0 hoặc index >= length?"}
    H -- "Có" --> I["ArrayIndexOutOfBoundsException"]
    H -- "Không" --> J["Truy cập hợp lệ"]
~~~

Sơ đồ giả định thao tác cấp phát và đọc/ghi mảng một chiều với kích thước/chỉ số kiểu số nguyên. Nó chỉ làm rõ **kiểu lỗi thường gặp**, không biểu diễn hết mọi trường hợp lỗi cấp phát hoặc các biểu thức có tác dụng phụ.

Quy tắc debug: nếu thông báo chứa `NegativeArraySizeException`, hãy kiểm tra biểu thức kích thước ở vị trí `new T[size]`; nếu chứa `ArrayIndexOutOfBoundsException`, hãy xem độ dài mảng và chỉ số tại phép truy cập `array[index]`.

## 8. Chương trình Java 17+ độc lập, chạy được

Tạo đúng file **`ArrayExceptionsDemo.java`**:

~~~java
import java.util.Arrays;

public final class ArrayExceptionsDemo {
    private ArrayExceptionsDemo() {}

    static boolean validIndex(int[] array, int index) {
        return array != null && index >= 0 && index < array.length;
    }

    static String readSafely(int[] array, int index) {
        if (array == null) return "NULL_ARRAY";
        if (index < 0 || index >= array.length) return "BAD_INDEX";
        return "VALUE:" + array[index];
    }

    static int[] createChecked(int size) {
        if (size < 0) {
            throw new IllegalArgumentException("size must be >= 0");
        }
        return new int[size];
    }

    static int sum(int[] array) {
        int total = 0;
        for (int i = 0; i < array.length; i++) {
            total += array[i];
        }
        return total;
    }

    public static void main(String[] args) {
        int[] values = {10, 20, 30};

        System.out.println("length=" + values.length);
        System.out.println("first=" + values[0]);
        System.out.println("last=" + values[values.length - 1]);
        System.out.println("sum=" + sum(values));

        System.out.println("valid -1=" + validIndex(values, -1));
        System.out.println("valid 0=" + validIndex(values, 0));
        System.out.println("valid 2=" + validIndex(values, 2));
        System.out.println("valid 3=" + validIndex(values, 3));
        System.out.println("valid null=" + validIndex(null, 0));

        System.out.println("safe -1=" + readSafely(values, -1));
        System.out.println("safe 0=" + readSafely(values, 0));
        System.out.println("safe 2=" + readSafely(values, 2));
        System.out.println("safe 3=" + readSafely(values, 3));
        System.out.println("safe null=" + readSafely(null, 0));

        try {
            System.out.println(values[-1]);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("read -1=ArrayIndexOutOfBoundsException");
        }

        try {
            values[values.length] = 99;
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("write length=ArrayIndexOutOfBoundsException");
        }

        try {
            int requestedLength = -2;
            int[] bad = new int[requestedLength];
            System.out.println(bad.length);
        } catch (NegativeArraySizeException ex) {
            System.out.println("size -2=NegativeArraySizeException");
        }

        int[] empty = new int[0];
        System.out.println("empty length=" + empty.length);
        try {
            System.out.println(empty[0]);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("empty[0]=ArrayIndexOutOfBoundsException");
        }

        int[] missing = null;
        try {
            System.out.println(missing.length);
        } catch (NullPointerException ex) {
            System.out.println("null.length=NullPointerException");
        }

        System.out.println("checked size 0=" + createChecked(0).length);
        System.out.println("checked size 3=" + createChecked(3).length);
        try {
            createChecked(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("guard -1=" + ex.getMessage());
        }

        int[] extended = Arrays.copyOf(values, 5);
        System.out.println("original=" + Arrays.toString(values));
        System.out.println("extended=" + Arrays.toString(extended));

        for (int i = values.length - 1; i >= 0; i--) {
            System.out.println("reverse=" + values[i]);
        }
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên, terminal ở thư mục chứa file. Chương trình không cần thư viện ngoài JDK, Maven, Gradle hoặc preview feature.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 ArrayExceptionsDemo.java
java -cp . ArrayExceptionsDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ArrayExceptionsDemo.java
java -cp . ArrayExceptionsDemo
~~~

### Exact expected stdout

~~~text
length=3
first=10
last=30
sum=60
valid -1=false
valid 0=true
valid 2=true
valid 3=false
valid null=false
safe -1=BAD_INDEX
safe 0=VALUE:10
safe 2=VALUE:30
safe 3=BAD_INDEX
safe null=NULL_ARRAY
read -1=ArrayIndexOutOfBoundsException
write length=ArrayIndexOutOfBoundsException
size -2=NegativeArraySizeException
empty length=0
empty[0]=ArrayIndexOutOfBoundsException
null.length=NullPointerException
checked size 0=0
checked size 3=3
guard -1=size must be >= 0
original=[10, 20, 30]
extended=[10, 20, 30, 0, 0]
reverse=30
reverse=20
reverse=10
~~~

**Giải thích nhanh:**

1. `values.length = 3`; chỉ số 0 và 2 hợp lệ, -1 và 3 không hợp lệ.
2. `readSafely` phát hiện null hoặc chỉ số ngoài biên trước khi đọc mảng.
3. Hai trường hợp đọc -1, ghi vào chỉ số bằng `length` ném `ArrayIndexOutOfBoundsException`.
4. `new int[-2]` ném `NegativeArraySizeException`; `new int[0]` hợp lệ, nhưng `empty[0]` vẫn vượt biên.
5. `missing.length` ném `NullPointerException`, không phải lỗi chỉ số.
6. `createChecked` chuyển đầu vào âm thành lỗi `IllegalArgumentException` theo hợp đồng API.
7. `Arrays.copyOf` tạo mảng mới dài 5, giữ mảng gốc nguyên độ dài 3.

## 9. Lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách đúng |
|---|---|---|
| `a[a.length]` để lấy phần tử cuối | `ArrayIndexOutOfBoundsException` | `a[a.length - 1]` khi không rỗng |
| Dùng `i <= a.length` để duyệt | Vượt biên ở `i == length` | `i < a.length` |
| Chỉ kiểm tra `i < a.length` | Chỉ số âm lọt | `0 <= i && i < a.length` |
| Tạo `new int[-1]` | `NegativeArraySizeException` | Kiểm tra `size >= 0` |
| Nghĩ `new int[0]` là lỗi | Hiểu sai điều kiện cấp phát | Mảng rỗng là hợp lệ |
| Đọc `a[0]` khi `length == 0` | Vượt biên | Kiểm tra `length > 0` |
| Dùng `a.length` khi `a == null` | `NullPointerException` | Kiểm tra null trước |
| Gán `a[a.length] = item` để thêm phần tử | Vượt biên; độ dài cố định | Tạo mảng mới/List phù hợp |
| Trộn hai ngoại lệ trong một `catch` rồi đoán nguyên nhân | Chẩn đoán khó hơn | Xác định lỗi cấp phát hay truy cập |
| Dựa vào `getMessage()` của exception làm exact stdout | Dễ khác môi trường/JDK | In thông điệp ổn định do code định nghĩa |
| Bắt `RuntimeException` quanh cả thuật toán để che mọi lỗi | Có thể giấu bug thật | Sửa cận/kích thước tại nơi gây lỗi |
| Dùng kích thước không âm nhưng quá lớn | Có thể thiếu bộ nhớ | Hạn chế kích thước đầu vào theo yêu cầu |

**Không dùng `try/catch` để thay thế thuật toán duyệt đúng biên.** Trong ví dụ, catch chỉ giúp thấy rõ loại ngoại lệ, còn cách phòng ngừa là xác thực trước khi đọc/ghi/cấp phát.

## 10. Bài tập có đáp án

### A — Hai biểu thức có cùng loại lỗi không?

~~~java
int[] a = {1, 2};
// a[2];
// new int[-2];
~~~

**Đáp án:** không. `a[2]` gây `ArrayIndexOutOfBoundsException` vì mảng dài 2, còn `new int[-2]` gây `NegativeArraySizeException`.

### B — Mảng rỗng

~~~java
int[] a = new int[0];
System.out.println(a.length);
~~~

**Đáp án:** in `0`. Nếu tiếp tục truy cập `a[0]`, runtime ném `ArrayIndexOutOfBoundsException`.

### C — Sửa vòng `for` sai

~~~java
int[] a = {2, 4, 6};
// for (int i = 0; i <= a.length; i++) {
//     System.out.println(a[i]);
// }
~~~

**Đáp án:**

~~~java
for (int i = 0; i < a.length; i++) {
    System.out.println(a[i]);
}
~~~

**Exact stdout:**

~~~text
2
4
6
~~~

### D — Kiểm tra null và biên

Viết hàm cho biết `index` có hợp lệ với `int[] a` hay không.

**Đáp án:**

~~~java
static boolean isValid(int[] a, int index) {
    return a != null && index >= 0 && index < a.length;
}
~~~

Không gọi `a.length` khi `a == null` và không bỏ sót chỉ số âm.

### E — Chính sách kích thước âm

Yêu cầu từ chối kích thước âm bằng ngoại lệ có thông điệp rõ ràng.

**Đáp án:**

~~~java
static int[] allocate(int requested) {
    if (requested < 0) {
        throw new IllegalArgumentException("negative size");
    }
    return new int[requested];
}
~~~

Trường hợp `requested = 0` vẫn hợp lệ, còn `-1` tạo lỗi `IllegalArgumentException` theo chính sách API.

## 11. Checklist và kết luận

- [ ] Biết `ArrayIndexOutOfBoundsException` phát sinh khi đọc **hoặc ghi** vào chỉ số không hợp lệ.
- [ ] Nhớ miền chỉ số `0 <= index < array.length`.
- [ ] Biết `NegativeArraySizeException` phát sinh lúc tạo mảng bằng kích thước âm.
- [ ] Hiểu `new int[0]` hợp lệ nhưng `empty[0]` không hợp lệ.
- [ ] Không nhầm `null` với mảng rỗng; `null.length` gây `NullPointerException`.
- [ ] Sử dụng vòng lặp `i < array.length` thay vì `i <= array.length`.
- [ ] Kiểm tra kích thước không âm ở ranh giới API nếu cần thông báo rõ ràng.
- [ ] Không cho rằng kích thước không âm luôn có đủ bộ nhớ để cấp phát.
- [ ] Phân biệt thời điểm cấp phát mảng với thời điểm truy cập phần tử.
- [ ] Không dựa vào thông điệp exception mặc định để tạo stdout có thể tái lập.
- [ ] Chạy `ArrayExceptionsDemo.java` trên JDK 17+, so sánh exact stdout và xác nhận các biên `-1`, `0`, `length-1`, `length`.

**Kết luận:** `ArrayIndexOutOfBoundsException` báo lỗi **vị trí truy cập** trong mảng đã tạo; `NegativeArraySizeException` báo lỗi **kích thước âm khi cấp phát**. Cả hai đều có thể tránh được trong luồng xử lý thông thường bằng cách kiểm tra đúng dữ liệu đầu vào, luôn duyệt theo cận `0 <= i < length`, và xử lý rõ ràng hai trường hợp mảng rỗng và mảng null.