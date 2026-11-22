# Mảng là đối tượng chứa số phần tử cố định cùng kiểu thành phần trong Java

> **Java core — language-basics / Mảng một chiều**  
> **Phiên bản:** Java 17+, chương trình một file, không cần thư viện ngoài JDK.  
> **Mục tiêu:** Hiểu vì sao mảng là **đối tượng** có độ dài cố định và **kiểu thành phần runtime** xác định; phân biệt mảng nguyên thủy với mảng tham chiếu, quan sát cơ chế covariance và `ArrayStoreException`.

## 1. Mảng một chiều là một đối tượng

Trong Java, mảng (`array`) là đối tượng dùng để lưu **một số lượng vị trí cố định**, mỗi vị trí có cùng **kiểu thành phần** (*component type*).

~~~java
int[] scores = new int[3]; // Đối tượng mảng int gồm 3 vị trí.
scores[0] = 7;
scores[1] = 8;
scores[2] = 9;
~~~

- `int[]` là **kiểu mảng**, `int` là **kiểu thành phần**. `String[]` tương tự nhưng các phần tử giữ tham chiếu `String`.
- `new int[3]` tạo **một đối tượng mảng** có `length == 3`. Các vị trí được đánh số **0, 1, 2**.
- Biến `scores` giữ **tham chiếu** tới đối tượng mảng. Có thể gán tham chiếu đó cho biến khác, truyền vào phương thức hoặc đặt bằng `null`.
- Mảng là đối tượng nên có thể gán cho biến kiểu `Object`. Mảng cũng thực hiện `Cloneable` và `java.io.Serializable`.
- Số vị trí của **chính đối tượng mảng** không thay đổi sau khi tạo; nhưng giá trị lưu trong các vị trí có thể thay đổi.

Một `int[]` chỉ giữ các giá trị `int`, còn `String[]` giữ `null` hoặc tham chiếu tới các đối tượng thích hợp với kiểu thành phần `String`. Một mảng tham chiếu có kiểu thành phần là lớp/interface cha có thể chứa đối tượng thuộc các lớp con khác nhau; không bắt buộc mọi phần tử có **cùng lớp runtime**.

Phần tiếp theo tập trung vào **kiểu thành phần và ràng buộc kiểu lúc chạy**. Việc khai báo bằng `new`, duyệt chỉ số, giá trị mặc định, mảng rỗng và sao chép sẽ được thực hành ở các bài tương ứng trong chương.

## 2. Kiểu thành phần và kiểm tra kiểu tại runtime

Mảng có kiểu runtime thực, ngay cả khi được tham chiếu qua `Object`:

~~~java
int[] values = {1, 2};
Object obj = values;

System.out.println(obj instanceof int[]);     // true
System.out.println(obj instanceof Object);    // true
System.out.println(obj instanceof Object[]);  // false
System.out.println(values.getClass().getComponentType().getTypeName()); // int
~~~

`int[]` là một đối tượng nhưng **không phải `Object[]`**, vì phần tử của mảng là giá trị primitive `int`, không phải tham chiếu đối tượng.

Mảng tham chiếu có quy tắc **covariance**: `String[]` có thể dùng ở nơi cần `Object[]`, nhưng Java vẫn bảo vệ kiểu thành phần **thật** của đối tượng mảng:

~~~java
String[] words = {"a", "b"};
Object[] objects = words; // Hợp lệ: covariance.
objects[0] = "X";         // Hợp lệ: String.
try {
    objects[1] = Integer.valueOf(42); // Không phải String!
} catch (ArrayStoreException ex) {
    System.out.println("ArrayStoreException");
}
~~~

`objects` có kiểu tĩnh `Object[]` nhưng mảng runtime vẫn là `String[]`. Gán `Integer` vào vị trí này ném `ArrayStoreException` — đây là lỗi khác với `ArrayIndexOutOfBoundsException`.

**Cùng kiểu thành phần** nghĩa là các vị trí tuân theo **kiểu thành phần của đối tượng mảng**, không phải mọi phần tử đều có cùng kiểu runtime. Ví dụ `Number[]` có thể giữ `Integer` và `Double`, vì cả hai đều là subtype của `Number`.

## 3. Chương trình Java 17+ chạy độc lập

Tạo file **OneDimensionalArrayDemo.java**:

~~~java
import java.util.Arrays;

public final class OneDimensionalArrayDemo {
    public static void main(String[] args) {
        int[] numbers = new int[3];
        String[] names = new String[2];

        System.out.println("intDefaults=" + Arrays.toString(numbers));
        System.out.println("referenceDefaults=" + Arrays.toString(names));
        System.out.println("initialLength=" + numbers.length);

        numbers[0] = 7;
        numbers[2] = 9;
        System.out.println("changed=" + Arrays.toString(numbers));

        int[] empty = new int[0];
        System.out.println("emptyLength=" + empty.length);

        Object asObject = numbers;
        System.out.println("isObject=" + (asObject instanceof Object));
        System.out.println("componentType="
                + numbers.getClass().getComponentType().getTypeName());

        int[] alias = numbers;
        alias[1] = 5;
        System.out.println("aliasShares=" + (alias == numbers));
        System.out.println("afterAlias=" + Arrays.toString(numbers));

        int[] copied = numbers.clone();
        copied[0] = 100;
        System.out.println("afterCopyOriginal=" + Arrays.toString(numbers));
        System.out.println("afterCopyNew=" + Arrays.toString(copied));

        numbers = Arrays.copyOf(numbers, 5);
        System.out.println("resizedNewLength=" + numbers.length);
        System.out.println("resizedValues=" + Arrays.toString(numbers));
        System.out.println("oldAliasLength=" + alias.length);

        String[] words = {"a", "b"};
        Object[] refArray = words;
        refArray[0] = "X";
        System.out.println("referenceChanged=" + Arrays.toString(words));
        try {
            refArray[1] = Integer.valueOf(42);
        } catch (ArrayStoreException ex) {
            System.out.println("covariantStore=ArrayStoreException");
        }

        Object primitiveArray = new int[] {1, 2};
        System.out.println("primitiveObjectArray="
                + (primitiveArray instanceof Object[]));

        try {
            int invalid = numbers[5];
            System.out.println(invalid);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("badIndex=ArrayIndexOutOfBoundsException");
        }

        try {
            int[] negative = new int[-1];
            System.out.println(negative.length);
        } catch (NegativeArraySizeException ex) {
            System.out.println("negativeLength=NegativeArraySizeException");
        }

        int[] missing = null;
        try {
            System.out.println(missing.length);
        } catch (NullPointerException ex) {
            System.out.println("nullArray=NullPointerException");
        }
    }
}
~~~

Trong thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 OneDimensionalArrayDemo.java
java OneDimensionalArrayDemo
~~~

**Expected stdout chính xác:**

~~~text
intDefaults=[0, 0, 0]
referenceDefaults=[null, null]
initialLength=3
changed=[7, 0, 9]
emptyLength=0
isObject=true
componentType=int
aliasShares=true
afterAlias=[7, 5, 9]
afterCopyOriginal=[7, 5, 9]
afterCopyNew=[100, 5, 9]
resizedNewLength=5
resizedValues=[7, 5, 9, 0, 0]
oldAliasLength=3
referenceChanged=[X, b]
covariantStore=ArrayStoreException
primitiveObjectArray=false
badIndex=ArrayIndexOutOfBoundsException
negativeLength=NegativeArraySizeException
nullArray=NullPointerException
~~~

Những dòng `oldAliasLength=3` và `resizedNewLength=5` chứng minh tạo mảng mới chứ không đổi chiều dài mảng cũ. `covariantStore` thể hiện ràng buộc kiểu thành phần được kiểm tra tại runtime; `badIndex` và `negativeLength` là lỗi khác nhau.

## 4. Lỗi phổ biến và bài tập

| Hiểu lầm / lỗi | Cách hiểu hoặc xử lý đúng |
| --- | --- |
| Gọi `array.length()` | Dùng trường `array.length` |
| Cho rằng chỉ số bắt đầu từ 1 | Mảng bắt đầu từ chỉ số 0 |
| Gán `array.length = n` | Không hợp lệ; tạo mảng mới nếu cần số vị trí khác |
| Dùng `array[array.length]` | Vượt phạm vi; chỉ số cuối là `array.length - 1` khi không rỗng |
| Đồng nhất mảng rỗng và `null` | Rỗng có `length == 0`; null không có đối tượng |
| Gán mảng cho biến khác rồi nghĩ đã sao chép | Đó chỉ là alias; dùng `clone()` hoặc `Arrays.copyOf` khi cần mảng mới |
| Cho rằng `int[]` là `Object[]` | `int[]` là Object nhưng các phần tử là primitive |
| Gán sai kiểu qua alias `Object[]` trỏ tới `String[]` | Runtime ném `ArrayStoreException` |

**Bài 1.** Tạo mảng `boolean[3]` và `String[2]`, dự đoán giá trị mặc định, sau đó in bằng `Arrays.toString`.

**Bài 2.** Với `int[] a = {2, 4}; int[] b = a;`, thay `b[0]` và giải thích vì sao `a[0]` cũng đổi. Sau đó dùng `clone()` để tạo mảng độc lập.

**Bài 3.** Dùng `Arrays.copyOf` mở rộng mảng từ 2 lên 4 phần tử, giải thích các giá trị thêm vào và trạng thái tham chiếu cũ.

**Bài 4.** Thử `Number[] values = {Integer.valueOf(1), Double.valueOf(2.5)};`; vì sao hai đối tượng có lớp runtime khác nhau vẫn có thể nằm trong cùng mảng?

**Bài 5.** Tạo `String[]`, gán vào `Object[]` rồi thử lưu `Integer`; dự đoán lỗi. Nêu khác biệt với lỗi chỉ số và kích thước âm.

### Ghi nhớ

**Mảng là đối tượng có kiểu thành phần và `length` được ấn định khi tạo.** Ta có thể sửa phần tử nhưng không sửa số vị trí của đối tượng mảng. Mảng primitive giữ giá trị primitive; mảng tham chiếu giữ `null` hoặc đối tượng tương thích với kiểu thành phần runtime. Khi cần mở rộng, tạo mảng mới; khi chia sẻ tham chiếu, thay đổi phần tử có thể được nhìn thấy qua mọi alias.
