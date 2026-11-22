# Giới thiệu `Arrays.toString()`, `Arrays.equals()` và `Arrays.copyOf()`

> **Java core — language-basics / Mảng một chiều**  
> **Môi trường:** Java 17+, chỉ dùng JDK.  
> **Mục tiêu:** Biết cách **in nội dung**, **so sánh nội dung** và **tạo bản sao mảng với độ dài mong muốn**; tránh nhầm tham chiếu `==` với nội dung, mảng rỗng với `null` và sao chép nông với sao chép sâu.

## 1. Ba công cụ trong `java.util.Arrays`

~~~java
import java.util.Arrays;

int[] data = {2, 4, 6};

System.out.println(Arrays.toString(data));          // [2, 4, 6]
System.out.println(Arrays.equals(data, new int[] {2, 4, 6})); // true
int[] copy = Arrays.copyOf(data, 5);                 // [2, 4, 6, 0, 0]
~~~

| Phương thức | Vai trò | Giá trị trả về |
| --- | --- | --- |
| `Arrays.toString(array)` | Biểu diễn phần tử của mảng một chiều thành chuỗi | `String` |
| `Arrays.equals(a, b)` | So sánh nội dung của hai mảng theo thứ tự | `boolean` |
| `Arrays.copyOf(original, newLength)` | Tạo **mảng mới**, sao chép phần đầu và cắt/bổ sung nếu cần | Mảng mới |

Các phương thức đều là `static`, gọi qua lớp `Arrays`. Chúng không tự thay đổi đối tượng mảng nguồn. Dùng `import java.util.Arrays;` hoặc gọi đầy đủ `java.util.Arrays.toString(...)`.

## 2. `Arrays.toString()`: nhìn thấy các phần tử

~~~java
int[] values = {3, -1, 0};
String[] names = {"An", null, "Binh"};

System.out.println(Arrays.toString(values)); // [3, -1, 0]
System.out.println(Arrays.toString(names));  // [An, null, Binh]
System.out.println(Arrays.toString(new int[0])); // []
~~~

`System.out.println(values)` gọi biểu diễn đối tượng mặc định của mảng (thường giống `[I@...`), **không** tự in các số dưới dạng danh sách. `Arrays.toString(values)` thuận tiện khi debug và viết output có thể kiểm chứng.

- Với mảng primitive, phần tử được định dạng theo kiểu tương ứng.
- Với mảng tham chiếu, nội dung hiển thị phụ thuộc vào `toString()` của đối tượng phần tử; phần tử null hiện `null`.
- Với **mảng nhiều chiều**, `Arrays.toString(outer)` không in sâu các mảng con; dùng `Arrays.deepToString(outer)` khi muốn xem cấu trúc lồng nhau.

`Arrays.toString((int[]) null)` trả **chuỗi `"null"`**, không ném `NullPointerException`. Đây chỉ là cách định dạng tham chiếu null, không có nghĩa mảng được tạo ra.

## 3. `Arrays.equals()` khác toán tử `==`

~~~java
int[] a = {1, 2};
int[] b = {1, 2};
int[] alias = a;

System.out.println(a == b);            // false: hai đối tượng khác nhau.
System.out.println(a == alias);        // true: cùng đối tượng.
System.out.println(Arrays.equals(a, b)); // true: hai phần tử bằng nhau.
~~~

`Arrays.equals(a, b)` với mảng primitive so sánh các phần tử tương ứng cùng thứ tự; chiều dài khác nhau thì false. Với mảng tham chiếu, phương thức dùng quy tắc bằng nhau của **phần tử**, bao gồm `equals`, không nhất thiết so bằng tham chiếu.

~~~java
String[] x = {new String("Java")};
String[] y = {"Java"};
System.out.println(Arrays.equals(x, y)); // true: String.equals xét nội dung.
~~~

Ngược lại, các đối tượng chỉ giữ `Object.equals` mặc định thường so theo danh tính:

~~~java
StringBuilder[] x = {new StringBuilder("A")};
StringBuilder[] y = {new StringBuilder("A")};
// Arrays.equals(x, y) là false: StringBuilder không override equals theo nội dung.
~~~

Điều này khác với **so sánh mảng lồng nhau**: `Arrays.equals(int[][], int[][])` chỉ so sánh các tham chiếu mảng con theo `equals` của từng mảng; muốn so từng số trong mảng con, dùng `Arrays.deepEquals(...)`.

## 4. `Arrays.copyOf()`: mảng mới, dài hơn hoặc ngắn hơn

~~~java
int[] original = {5, 7, 9};

int[] sameLength = Arrays.copyOf(original, original.length);
int[] longer = Arrays.copyOf(original, 5);   // [5, 7, 9, 0, 0]
int[] shorter = Arrays.copyOf(original, 2);  // [5, 7]
~~~

Quy tắc:

1. Java tạo **mảng mới** với độ dài bằng `newLength`.
2. Sao chép `min(original.length, newLength)` phần tử đầu, giữ thứ tự.
3. Nếu cần thêm vị trí, mỗi vị trí được điền **giá trị mặc định của kiểu thành phần**: số là 0, boolean là false, tham chiếu là null.
4. Nếu độ dài mới nhỏ hơn, những phần tử ở cuối mảng nguồn không có trong mảng mới.

~~~java
String[] colors = {"red", "blue"};
String[] padded = Arrays.copyOf(colors, 4);
// padded = [red, blue, null, null].
~~~

`Arrays.copyOf` không thay đổi `original.length`. Nếu viết `original = Arrays.copyOf(original, 5)`, biến `original` sẽ **trỏ sang đối tượng mảng mới**; mọi alias trỏ tới mảng cũ vẫn nhìn thấy độ dài cũ.

Độ dài mới âm gây `NegativeArraySizeException`. Mảng nguồn null gây `NullPointerException` khi gọi `copyOf`; cần kiểm tra đầu vào nếu API cho phép null.

## 5. Bản sao độc lập ở cấp mảng, nhưng có thể chia sẻ đối tượng phần tử

Với mảng `int[]`, sao chép tạo các vị trí số độc lập:

~~~java
int[] a = {2, 4};
int[] copy = Arrays.copyOf(a, a.length);
copy[0] = 99;
// a = [2, 4]; copy = [99, 4]; a == copy là false.
~~~

Với mảng các đối tượng mutable, `copyOf` chỉ **sao chép giá trị tham chiếu** (*shallow copy*):

~~~java
StringBuilder[] source = {new StringBuilder("A")};
StringBuilder[] copy = Arrays.copyOf(source, source.length);

copy[0].append("!");
// source[0].toString() cũng là "A!".
copy[0] = new StringBuilder("B");
// source[0] vẫn trỏ đối tượng ban đầu "A!".
~~~

Mảng nhiều chiều trong Java là **mảng chứa các tham chiếu tới mảng con**. Vì vậy khi copy mảng ngoài, các mảng con vẫn được chia sẻ:

~~~java
int[][] rows = {{1, 2}, {3}};
int[][] outerCopy = Arrays.copyOf(rows, rows.length);

outerCopy[0][0] = 99;
// rows[0][0] cũng bằng 99.
~~~

Muốn sao chép sâu dữ liệu hai chiều, phải tạo bản sao cho từng mảng con hoặc dùng cách sao chép đối tượng thích hợp. `Arrays.deepEquals` và `Arrays.deepToString` dùng để **so sánh/hiển thị sâu**, không tự tạo bản sao sâu.

## 6. Mảng rỗng, `null` và độ phức tạp

| Lệnh | Kết quả |
| --- | --- |
| `Arrays.toString(new int[0])` | `"[]"` |
| `Arrays.toString((int[]) null)` | `"null"` |
| `Arrays.equals(new int[0], new int[0])` | `true` |
| `Arrays.equals((int[]) null, (int[]) null)` | `true` |
| `Arrays.equals((int[]) null, new int[0])` | `false` |
| `Arrays.copyOf(new int[0], 3)` | Mảng mới `[0, 0, 0]` |
| `Arrays.copyOf((int[]) null, 3)` | `NullPointerException` |

`Arrays.equals(null, null)` chỉ có nghĩa hai tham chiếu cùng null theo quy ước của API; **không** có hai đối tượng mảng được tạo. Khi tự viết hàm nghiệp vụ, vẫn phải quyết định null có hợp lệ không.

Với mảng dài `n`, `toString` đọc các phần tử để tạo chuỗi và `equals` có thể đọc tới `n` phần tử (hoặc dừng sớm khi khác). `copyOf` dùng bộ nhớ cho **mảng mới dài `newLength`** và sao chép phần phù hợp. Đây là các thao tác hữu ích nhưng không miễn phí nếu dữ liệu rất lớn.

## 7. Ví dụ Java 17+ chạy độc lập

Tạo file **ArraysBasicsDemo.java**:

~~~java
import java.util.Arrays;

public final class ArraysBasicsDemo {
    public static void main(String[] args) {
        int[] numbers = {2, 4, 6};
        int[] sameValues = {2, 4, 6};
        System.out.println("initial=" + Arrays.toString(numbers));
        System.out.println("sameReference=" + (numbers == sameValues));
        System.out.println("sameContent=" + Arrays.equals(numbers, sameValues));

        int[] alias = numbers;
        alias[0] = 9;
        System.out.println("afterAlias=" + Arrays.toString(numbers));
        System.out.println("equalAfterAlias=" + Arrays.equals(numbers, sameValues));

        int[] copy = Arrays.copyOf(numbers, numbers.length);
        copy[1] = 40;
        System.out.println("originalAfterCopy=" + Arrays.toString(numbers));
        System.out.println("changedCopy=" + Arrays.toString(copy));
        System.out.println("copySameReference=" + (numbers == copy));

        System.out.println("longer="
                + Arrays.toString(Arrays.copyOf(numbers, 5)));
        System.out.println("shorter="
                + Arrays.toString(Arrays.copyOf(numbers, 2)));
        String[] words = {"red", "blue"};
        System.out.println("paddedReferences="
                + Arrays.toString(Arrays.copyOf(words, 4)));

        String[] firstWords = {new String("Java")};
        String[] secondWords = {"Java"};
        System.out.println("stringContentEqual="
                + Arrays.equals(firstWords, secondWords));

        StringBuilder[] buildersA = {new StringBuilder("A")};
        StringBuilder[] buildersB = {new StringBuilder("A")};
        System.out.println("builderContentEqual="
                + Arrays.equals(buildersA, buildersB));

        int[][] nestedA = {{1, 2}, {3}};
        int[][] nestedB = {{1, 2}, {3}};
        System.out.println("nestedShallowEqual="
                + Arrays.equals(nestedA, nestedB));
        System.out.println("nestedDeepEqual="
                + Arrays.deepEquals(nestedA, nestedB));
        System.out.println("nestedDeepText="
                + Arrays.deepToString(nestedA));

        int[][] outerCopy = Arrays.copyOf(nestedA, nestedA.length);
        outerCopy[0][0] = 99;
        System.out.println("nestedAfterCopy="
                + Arrays.deepToString(nestedA));
        System.out.println("outerSame=" + (nestedA == outerCopy));
        System.out.println("innerSame=" + (nestedA[0] == outerCopy[0]));

        String[] missing = null;
        System.out.println("nullText=" + Arrays.toString(missing));
        System.out.println("nullEqualsNull="
                + Arrays.equals(missing, (String[]) null));
        System.out.println("nullEqualsEmpty="
                + Arrays.equals(missing, new String[0]));
        System.out.println("emptyToThree="
                + Arrays.toString(Arrays.copyOf(new int[0], 3)));

        try {
            Arrays.copyOf(missing, 2);
        } catch (NullPointerException ex) {
            System.out.println("copyNull=NullPointerException");
        }
        try {
            Arrays.copyOf(numbers, -1);
        } catch (NegativeArraySizeException ex) {
            System.out.println("copyNegative=NegativeArraySizeException");
        }
    }
}
~~~

Biên dịch/chạy trong thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 ArraysBasicsDemo.java
java ArraysBasicsDemo
~~~

**Expected stdout chính xác:**

~~~text
initial=[2, 4, 6]
sameReference=false
sameContent=true
afterAlias=[9, 4, 6]
equalAfterAlias=false
originalAfterCopy=[9, 4, 6]
changedCopy=[9, 40, 6]
copySameReference=false
longer=[9, 4, 6, 0, 0]
shorter=[9, 4]
paddedReferences=[red, blue, null, null]
stringContentEqual=true
builderContentEqual=false
nestedShallowEqual=false
nestedDeepEqual=true
nestedDeepText=[[1, 2], [3]]
nestedAfterCopy=[[99, 2], [3]]
outerSame=false
innerSame=true
nullText=null
nullEqualsNull=true
nullEqualsEmpty=false
emptyToThree=[0, 0, 0]
copyNull=NullPointerException
copyNegative=NegativeArraySizeException
~~~

Dòng `sameReference=false` nhưng `sameContent=true` chứng minh `==` khác `Arrays.equals`. Hai dòng `nestedDeepEqual` và `nestedAfterCopy` cho thấy cách so sánh sâu **khác** việc sao chép nông. Các dòng `copyNull` và `copyNegative` minh họa lỗi cần xử lý.

## 8. Lỗi thường gặp và bài tập

| Lỗi / hiểu lầm | Cách xử lý |
| --- | --- |
| In mảng trực tiếp rồi nghĩ đã in phần tử | Dùng `Arrays.toString(array)` |
| So hai mảng với `==` để so nội dung | Dùng `Arrays.equals(a, b)` |
| Dùng `Arrays.equals` cho mảng nhiều chiều và mong so mọi số | Dùng `Arrays.deepEquals` |
| Dùng `Arrays.toString` để in sâu mảng lồng nhau | Dùng `Arrays.deepToString` |
| Cho rằng `copyOf` đổi `length` của mảng gốc | Nó tạo **mảng mới** |
| Cho rằng `copyOf` sao chép sâu mọi đối tượng | Nó chỉ sao chép phần tử/tham chiếu |
| Gọi `copyOf(null, n)` | Kiểm tra null trước nếu có khả năng này |
| Dùng `newLength` âm | Kiểm tra độ dài, vì runtime ném `NegativeArraySizeException` |

**Bài 1.** Tạo hai mảng `int[] {1, 2, 3}` độc lập. So sánh bằng `==` và `Arrays.equals`, rồi sửa một phần tử.

**Bài 2.** Từ `int[] {4, 5}`, tạo một bản copy dài 4 và một bản dài 1. Dự đoán giá trị mặc định được thêm và phần tử bị cắt.

**Bài 3.** Dùng `String[] {"A", "B"}`, gọi `Arrays.copyOf` với độ dài 4 và giải thích vì sao hai vị trí mới là null chứ không phải chuỗi rỗng.

**Bài 4.** Viết mảng hai chiều có các mảng con độc lập nhưng nội dung bằng nhau; so sánh kết quả `Arrays.equals` và `Arrays.deepEquals`.

**Bài 5.** Sao chép mảng `StringBuilder[]` bằng `copyOf`, sau đó gọi `append` trên phần tử của bản sao. Vì sao nguồn cũng thấy nội dung thay đổi?

### Ghi nhớ

**`Arrays.toString` để xem nội dung; `Arrays.equals` để so nội dung; `Arrays.copyOf` để tạo mảng mới.** `==` trên hai biến mảng chỉ hỏi có cùng đối tượng không. `copyOf` có thể cắt hoặc bổ sung các giá trị mặc định, nhưng là **shallow copy** với tham chiếu đối tượng. Với mảng lồng nhau, dùng `deepToString`/`deepEquals` nếu cần xem hoặc so sánh phần tử sâu.
