# Mảng rỗng khác tham chiếu mảng `null` trong Java

> **Java core — language-basics / Mảng một chiều**  
> **Môi trường:** JDK 17+, một file Java tự chứa, chỉ sử dụng thư viện chuẩn.  
> **Mục tiêu:** Phân biệt mảng có `length == 0` với tham chiếu không trỏ tới mảng (`null`), dự đoán hành vi khi đọc `length`, truy cập phần tử hay duyệt bằng `for-each`, và thiết kế cách xử lý null/rỗng rõ ràng.

## 1. Hai trạng thái hoàn toàn khác nhau

~~~java
int[] empty = new int[0]; // Có đối tượng mảng; length = 0.
int[] alsoEmpty = {};     // Một đối tượng mảng rỗng khác.
int[] missing = null;     // Không trỏ tới đối tượng mảng nào.

System.out.println(empty.length);    // 0
System.out.println(missing == null);  // true
~~~

**Mảng rỗng** tồn tại trong bộ nhớ, có kiểu mảng cụ thể và có thuộc tính `length` bằng 0. **Tham chiếu mảng null** không trỏ tới bất kỳ đối tượng nào; nó không có thuộc tính `length` để truy cập.

Đây không phải khác biệt về **giá trị các phần tử**: mảng rỗng hoàn toàn **không có phần tử**. Mảng `new int[2]` có hai phần tử bằng 0, còn mảng `new String[2]` có hai phần tử bằng `null` — cả hai đều **không rỗng**.

| Khía cạnh | Mảng rỗng `new int[0]` | Tham chiếu `int[] a = null` |
| --- | --- | --- |
| Có đối tượng mảng? | Có | Không |
| `a == null` | `false` | `true` |
| `a.length` | `0` | Ném `NullPointerException` |
| Duyệt `for (int x : a)` | 0 lượt, không lỗi | Ném `NullPointerException` |
| Đọc `a[0]` | `ArrayIndexOutOfBoundsException` | `NullPointerException` |
| `a instanceof int[]` | `true` | `false` |

Khai báo `int[] data;` làm biến cục bộ **chưa được gán**, khác với `int[] data = null;`. Java không cho đọc một biến cục bộ chưa được khởi tạo.

## 2. Cách tạo mảng rỗng và độ dài cố định

Có thể tạo một mảng rỗng theo nhiều cách:

~~~java
int[] first = new int[0];
int[] second = {};
int[] third = new int[] {};
String[] names = {};
~~~

Mỗi lần thực hiện biểu thức tạo mảng là tạo **một đối tượng mảng mới**. Các đối tượng có thể cùng độ dài và cùng nội dung nhưng không nhất thiết cùng tham chiếu:

~~~java
int[] a = {};
int[] b = {};
System.out.println(a == b);                     // false
System.out.println(java.util.Arrays.equals(a,b)); // true
~~~

`a == b` so sánh **tham chiếu**; `Arrays.equals(a, b)` so sánh **phần tử** (hai mảng rỗng cùng kiểu thành phần có nội dung bằng nhau theo phép so sánh phù hợp).

Độ dài mảng là cố định. Muốn chuyển từ mảng rỗng sang một mảng có hai phần tử, ta phải tạo mảng mới và gán lại biến tham chiếu:

~~~java
int[] data = {};
data = new int[] {5, 7}; // data trỏ đối tượng khác, length = 2.
~~~

Điều này không làm “mở rộng” đối tượng rỗng ban đầu. Nếu có một biến khác đang tham chiếu đối tượng rỗng cũ, nó vẫn trỏ tới mảng dài 0.

## 3. `length`, chỉ số và hai kiểu ngoại lệ

Với một mảng hợp lệ có `n` phần tử, chỉ số hợp lệ là từ `0` đến `n - 1`. Với `n = 0`, **không có chỉ số hợp lệ**:

~~~java
int[] empty = new int[0];
System.out.println(empty.length); // 0
// int x = empty[0]; // Nếu chạy: ArrayIndexOutOfBoundsException.
~~~

Còn với tham chiếu `null`, thao tác cần truy cập đối tượng sẽ không thành công:

~~~java
int[] missing = null;
// int size = missing.length; // Nếu chạy: NullPointerException.
// int x = missing[0];        // Nếu chạy: NullPointerException.
~~~

Đọc `empty.length` hợp lệ vì đối tượng tồn tại; đọc `missing.length` không thể. `ArrayIndexOutOfBoundsException` xảy ra khi **đã có mảng** nhưng chỉ số nằm ngoài phạm vi; `NullPointerException` xảy ra khi cố truy cập qua **tham chiếu null**.

Java không tự chuyển `null` thành mảng rỗng và không tự cho `a[0]` bằng 0 khi mảng không có phần tử.

## 4. Duyệt `for-each` và tích lũy an toàn

~~~java
static long sum(int[] values) {
    long total = 0;
    for (int value : values) {
        total += value;
    }
    return total;
}
~~~

Nếu truyền một mảng rỗng, thân `for-each` chạy **0 lần** và phương thức trả `0`. Nếu truyền `null`, vòng `for-each` sẽ cố lấy nguồn dữ liệu để duyệt và ném `NullPointerException`.

Với dữ liệu có thể null, cần quyết định **hợp đồng phương thức**:

**Cách A — null là lỗi đầu vào (strict):**

~~~java
static long strictSum(int[] values) {
    java.util.Objects.requireNonNull(values, "values");
    long sum = 0;
    for (int value : values) {
        sum += value;
    }
    return sum;
}
~~~

**Cách B — null được coi như không có phần tử (có chủ đích):**

~~~java
static long sumOrZero(int[] values) {
    if (values == null) {
        return 0;
    }
    long sum = 0;
    for (int value : values) {
        sum += value;
    }
    return sum;
}
~~~

Hai lựa chọn có ngữ nghĩa khác nhau: *strict* giúp phát hiện sai hợp đồng sớm; *null-as-empty* có thể tiện cho dữ liệu tùy chọn nhưng cũng có thể che lỗi nguồn. **Đừng tự ý biến null thành mảng rỗng** nếu nghiệp vụ phân biệt “chưa có dữ liệu” và “có dữ liệu nhưng rỗng”.

## 5. Phân biệt ba trạng thái: null, rỗng, có phần tử

Khi cần trả thông báo khác nhau, nên kiểm tra null **trước**:

~~~java
static String classify(int[] values) {
    if (values == null) {
        return "NULL";
    }
    if (values.length == 0) {
        return "EMPTY";
    }
    return "NON_EMPTY:" + values.length;
}
~~~

Thứ tự trên vừa tránh `NullPointerException`, vừa giữ rõ ý nghĩa trạng thái:

| Đầu vào | Giá trị trả về |
| --- | --- |
| `null` | `"NULL"` |
| `new int[0]` | `"EMPTY"` |
| `new int[] {0}` | `"NON_EMPTY:1"` |
| `new int[] {4, 5}` | `"NON_EMPTY:2"` |

Nếu chỉ cần tính tổng hay đếm, có thể dùng chính sách null-as-empty. Nếu ứng dụng cần phân biệt dữ liệu chưa được tải với dữ liệu đã tải nhưng không có phần tử, nên giữ hai trạng thái riêng.

## 6. `Arrays.toString`, sao chép và mảng chứa phần tử `null`

`java.util.Arrays.toString(...)` hữu ích khi in nội dung mảng và **xử lý được tham chiếu mảng null**:

~~~java
int[] empty = {};
int[] missing = null;
System.out.println(java.util.Arrays.toString(empty));   // []
System.out.println(java.util.Arrays.toString(missing)); // null
~~~

Dòng thứ hai in chuỗi chữ `null`, **không có nghĩa mảng đã được tạo**. Đó là hành vi của phương thức định dạng, không phải của `missing.length`.

Một mảng tham chiếu có thể chứa giá trị `null` trong các vị trí tồn tại:

~~~java
String[] slots = new String[2];
System.out.println(java.util.Arrays.toString(slots)); // [null, null]
System.out.println(slots.length); // 2.
~~~

`slots` không rỗng dù mỗi phần tử đang null. `slots[0] == null` kiểm tra phần tử đầu tiên; `slots == null` kiểm tra chính **tham chiếu mảng**.

Có thể `clone()` một mảng rỗng để tạo một mảng rỗng **khác**. Nếu cố gọi `missing.clone()` khi `missing == null`, Java ném `NullPointerException`.

## 7. Chương trình Java 17+ chạy độc lập

Tạo file **EmptyVsNullArrayDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public final class EmptyVsNullArrayDemo {
    private static String classify(int[] values) {
        if (values == null) {
            return "NULL";
        }
        if (values.length == 0) {
            return "EMPTY";
        }
        return "NON_EMPTY:" + values.length;
    }

    private static long strictSum(int[] values) {
        Objects.requireNonNull(values, "values");
        long sum = 0;
        for (int value : values) {
            sum += value;
        }
        return sum;
    }

    private static long sumOrZero(int[] values) {
        if (values == null) {
            return 0;
        }
        long sum = 0;
        for (int value : values) {
            sum += value;
        }
        return sum;
    }

    public static void main(String[] args) {
        int[] empty = new int[0];
        int[] anotherEmpty = {};
        int[] missing = null;
        int[] oneZero = {0};
        String[] references = new String[2];

        System.out.println("emptyNull=" + (empty == null));
        System.out.println("missingNull=" + (missing == null));
        System.out.println("emptyLength=" + empty.length);
        System.out.println("emptyIsArray=" + (empty instanceof int[]));
        System.out.println("missingIsArray=" + (missing instanceof int[]));
        System.out.println("differentObjects=" + (empty != anotherEmpty));
        System.out.println("equalContents="
                + Arrays.equals(empty, anotherEmpty));

        System.out.println("classNull=" + classify(missing));
        System.out.println("classEmpty=" + classify(empty));
        System.out.println("classZero=" + classify(oneZero));
        System.out.println("classTwo="
                + classify(new int[] {4, 5}));

        System.out.println("emptyText=" + Arrays.toString(empty));
        System.out.println("missingText=" + Arrays.toString(missing));
        System.out.println("nullElements="
                + Arrays.toString(references));
        System.out.println("referenceLength=" + references.length);

        System.out.println("strictEmpty=" + strictSum(empty));
        System.out.println("strictValues="
                + strictSum(new int[] {3, 5}));
        System.out.println("nullAsEmpty=" + sumOrZero(missing));

        int visits = 0;
        for (int value : empty) {
            visits++;
        }
        System.out.println("emptyVisits=" + visits);

        try {
            int ignored = empty[0];
            System.out.println(ignored);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("emptyIndex=ArrayIndexOutOfBoundsException");
        }

        try {
            System.out.println(missing.length);
        } catch (NullPointerException ex) {
            System.out.println("missingLength=NullPointerException");
        }

        try {
            strictSum(missing);
        } catch (NullPointerException ex) {
            System.out.println("strictMissing=NullPointerException");
        }

        int[] alias = empty;
        empty = new int[] {9, 10};
        System.out.println("newLength=" + empty.length);
        System.out.println("oldAliasLength=" + alias.length);
    }
}
~~~

Biên dịch và chạy tại thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 EmptyVsNullArrayDemo.java
java EmptyVsNullArrayDemo
~~~

**Expected stdout chính xác:**

~~~text
emptyNull=false
missingNull=true
emptyLength=0
emptyIsArray=true
missingIsArray=false
differentObjects=true
equalContents=true
classNull=NULL
classEmpty=EMPTY
classZero=NON_EMPTY:1
classTwo=NON_EMPTY:2
emptyText=[]
missingText=null
nullElements=[null, null]
referenceLength=2
strictEmpty=0
strictValues=8
nullAsEmpty=0
emptyVisits=0
emptyIndex=ArrayIndexOutOfBoundsException
missingLength=NullPointerException
strictMissing=NullPointerException
newLength=2
oldAliasLength=0
~~~

`differentObjects=true` minh họa hai mảng rỗng có thể khác tham chiếu; `nullElements` cho thấy mảng dài 2 vẫn có thể chứa các phần tử null. `emptyIndex` và `missingLength` phân biệt rõ hai ngoại lệ; `oldAliasLength=0` chứng minh gán biến sang một mảng khác không biến đổi mảng cũ.

## 8. Sai lầm phổ biến và bài tập

| Hiểu lầm / lỗi | Cách hiểu đúng |
| --- | --- |
| `new int[0] == null` | Sai: mảng rỗng vẫn là một đối tượng |
| Có thể gọi `missing.length` | Sai: tham chiếu null gây `NullPointerException` |
| `empty[0]` có giá trị mặc định 0 | Sai: không tồn tại phần tử số 0; truy cập vượt chỉ số |
| `new String[2]` là mảng rỗng vì phần tử đều null | Sai: có hai phần tử, `length == 2` |
| `for-each` trên null bỏ qua như trên mảng rỗng | Sai: null gây `NullPointerException` |
| `Arrays.toString(nullArray)` in `null` tức là đã tạo mảng | Sai: đó chỉ là chuỗi định dạng tham chiếu null |
| Luôn thay null bằng rỗng | Chỉ khi hợp đồng nghiệp vụ cho phép |

**Bài 1.** Tạo `int[] a = new int[0]` và `int[] b = null`. Dự đoán `a == null`, `b == null`, `a.length` và `b.length`.

**Bài 2.** So sánh `new int[0]`, `new int[1]`, `new String[2]` về `length` và các giá trị mặc định.

**Bài 3.** Viết hàm trả `"NULL"`, `"EMPTY"` hoặc `"NON_EMPTY"` để phân biệt ba trạng thái mà không gây NPE.

**Bài 4.** Chọn hợp đồng cho hàm tính tổng: từ chối null hay coi null như không có phần tử? Viết cả hai, giải thích vì sao kết quả rỗng là 0.

**Bài 5.** Gán tham chiếu mảng rỗng vào biến `alias`, rồi gán biến ban đầu sang `new int[] {1, 2, 3}`; giải thích vì sao `alias.length` vẫn bằng 0.

### Ghi nhớ

**Mảng rỗng là một đối tượng hợp lệ với `length == 0`; tham chiếu `null` không trỏ tới đối tượng mảng nào.** Vòng `for-each` trên mảng rỗng thực hiện 0 lượt, còn trên null gây NPE. Mảng rỗng không có chỉ số 0. Trong API, hãy quyết định rõ lúc nào null được phép, thay vì vô tình đánh đồng “không có dữ liệu” với “dữ liệu đã có nhưng rỗng”.
