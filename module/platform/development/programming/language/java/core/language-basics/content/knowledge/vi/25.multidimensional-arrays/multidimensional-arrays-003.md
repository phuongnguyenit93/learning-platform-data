# Khởi tạo từng mảng con và hàng chưa được tạo trong Java

> **Java core — language-basics / Mảng nhiều chiều**  
> **Môi trường:** JDK 17+, không dùng preview hoặc thư viện ngoài.  
> **Mục tiêu:** Phân biệt việc tạo **mảng ngoài** với việc tạo **mỗi hàng**, xử lý hàng còn `null`, cấp phát các hàng có độ dài khác nhau, và duyệt an toàn một mảng hai chiều không đều.

## 1. Mảng hai chiều là mảng chứa các tham chiếu tới mảng con

Trong Java, `int[][]` không phải một khối hình chữ nhật bắt buộc. Nó là **mảng ngoài có kiểu thành phần `int[]`**: mỗi phần tử ở mảng ngoài lưu một tham chiếu tới một mảng `int[]`, hoặc `null`.

~~~java
int[][] rows = new int[3][];
System.out.println(rows.length); // 3: mảng ngoài có ba vị trí.
System.out.println(java.util.Arrays.deepToString(rows));
// [null, null, null]
~~~

`new int[3][]` chỉ tạo **mảng ngoài** có ba vị trí. Vì kiểu thành phần của nó là `int[]` (kiểu tham chiếu), cả ba vị trí mặc định đều `null`: **chưa có hàng nào được tạo**.

Điều này khác với `new int[3][2]`: khi có kích thước chiều thứ hai, Java tạo luôn ba mảng con `int[2]` và khởi tạo các phần tử số của mỗi hàng bằng 0.

| Biểu thức tạo mảng | Mảng ngoài | Trạng thái hàng ngay sau tạo |
| --- | --- | --- |
| `new int[3][]` | 3 vị trí | `null`, `null`, `null` |
| `new int[3][2]` | 3 vị trí | Mỗi hàng là `int[2]`, chứa `[0, 0]` |
| `new int[0][]` | 0 vị trí | Không có hàng nào để truy cập |
| `new int[][] {{1, 2}, null, {}}` | 3 vị trí | Hàng dài 2, hàng null, hàng rỗng |

Vì hàng là mảng riêng, Java cho phép **các hàng dài khác nhau** (*ragged/jagged array*).

## 2. Cấp phát từng mảng con sau khi tạo mảng ngoài

~~~java
int[][] data = new int[4][];

data[0] = new int[2];           // [0, 0]
data[1] = new int[] {3, 4, 5};  // [3, 4, 5]
data[2] = new int[0];           // []
data[3] = new int[1];           // [0]

System.out.println(java.util.Arrays.deepToString(data));
// [[0, 0], [3, 4, 5], [], [0]]
~~~

Ở trên, `data[0]` và `data[3]` mới được cấp phát với `new int[n]` nên có giá trị mặc định 0. `data[1]` dùng danh sách phần tử cụ thể. `data[2]` là **một đối tượng mảng rỗng hợp lệ**, không phải `null`.

Có thể gán hàng bằng cú pháp ngắn `{...}` **khi khởi tạo trực tiếp biến mảng**, nhưng **không** viết `data[1] = {3,4,5};`: đây là phép gán cho vị trí của mảng đã tồn tại, nên cần `new int[] {3,4,5}`.

Số hàng của mảng ngoài được cố định lúc tạo (`data.length == 4`), nhưng có thể **gán lại các tham chiếu hàng** trong từng vị trí, hoặc dùng mảng ngoài mới nếu cần số hàng khác.

## 3. Hàng `null` khác hàng rỗng `new int[0]`

~~~java
int[][] sample = new int[2][];
sample[1] = new int[0];

System.out.println(sample[0] == null); // true: chưa tạo hàng.
System.out.println(sample[1] == null); // false: có hàng rỗng.
System.out.println(sample[1].length);  // 0.
~~~

| Biểu thức | Hàng chưa tạo `sample[0]` | Hàng rỗng `sample[1]` |
| --- | --- | --- |
| Kiểm tra `row == null` | true | false |
| `row.length` | `NullPointerException` | 0 |
| `row[0]` | `NullPointerException` | `ArrayIndexOutOfBoundsException` |
| Duyệt `for (int x : row)` | `NullPointerException` | 0 lượt |
| `Arrays.toString(row)` | `"null"` | `"[]"` |

`sample.length` vẫn là 2 vì mảng ngoài có hai vị trí; **không phản ánh số hàng đã cấp phát**. Chỉ số của mảng ngoài phải hợp lệ trước khi kiểm tra trạng thái của hàng: `sample[2]` vẫn vượt chỉ số.

Nếu cần phân biệt “chưa tải dữ liệu hàng” và “đã tải nhưng không có phần tử”, hãy giữ khác biệt `null`/rỗng. Nếu quy ước nghiệp vụ không cho phép hàng null, hãy **khởi tạo đủ hàng** hoặc kiểm tra rõ ràng tại ranh giới đầu vào.

## 4. Cấp phát trong vòng lặp và mảng không đều

Có thể tạo các hàng theo quy tắc:

~~~java
int[][] triangle = new int[4][];

for (int row = 0; row < triangle.length; row++) {
    triangle[row] = new int[row + 1];
    for (int col = 0; col < triangle[row].length; col++) {
        triangle[row][col] = row + col;
    }
}
// [[0], [1, 2], [2, 3, 4], [3, 4, 5, 6]]
~~~

Mỗi lần gán `triangle[row] = new int[row + 1]` tạo **một mảng con riêng**. Vòng trong dùng `triangle[row].length` thay vì lấy độ dài của một hàng cố định: với mảng không đều, số cột hợp lệ có thể khác nhau theo hàng.

Mảng hai chiều thông thường vẫn có thể tạo gọn:

~~~java
int[][] rectangular = new int[2][3];
// [[0, 0, 0], [0, 0, 0]]
~~~

Với kiểu mảng nhiều chiều hơn, Java cũng có thể chỉ cấp phát một số chiều đầu; các chiều chưa cấp phát ở cấp sâu hơn chứa null. Chỉ định kích thước sau một chiều đã bỏ trống là không hợp lệ: `new int[][3]` **không biên dịch**.

## 5. Duyệt an toàn khi có hàng chưa tạo

Một vòng lặp nested `for-each` đơn giản có thể ném NPE nếu gặp hàng null:

~~~java
// Không an toàn nếu data có hàng null:
// for (int[] row : data) {
//     for (int number : row) {
//         System.out.println(number);
//     }
// }
~~~

Hãy kiểm tra trước khi duyệt mảng con:

~~~java
static long sumNonNullRows(int[][] values) {
    if (values == null) {
        return 0; // Chỉ khi hợp đồng cho phép coi outer null như rỗng.
    }

    long sum = 0;
    for (int[] row : values) {
        if (row == null) {
            continue; // Hàng chưa tạo.
        }
        for (int number : row) {
            sum += number;
        }
    }
    return sum;
}
~~~

Nếu cần **đếm số phần tử**, chỉ tăng bộ đếm khi thực sự duyệt một giá trị `int`, không dùng `values.length` như số phần tử. Với một mảng không đều, số phần tử là **tổng `row.length` của các hàng khác null**, không phải “số hàng × số cột”.

Một chính sách khác là ném `IllegalArgumentException` khi gặp hàng null, nhằm bảo đảm dữ liệu phải đầy đủ. Chọn và ghi rõ **một hợp đồng**; đừng âm thầm bỏ qua hàng thiếu nếu bài toán coi đó là lỗi.

## 6. Phân biệt sửa ô với gán lại tham chiếu hàng

Sau khi đã cấp phát một hàng, `data[0][1] = 9` cập nhật phần tử của hàng đang tồn tại; `data[0] = new int[]{9}` thay cả tham chiếu ở mảng ngoài. Nếu biến khác đang giữ hàng cũ, biến ấy vẫn thấy đối tượng cũ. Tương tự, `data.clone()` chỉ sao chép **mảng ngoài**, nên hai bản vẫn có thể dùng chung các hàng. Bài **Sao chép nông và chia sẻ các mảng con** đi sâu vào các cách tạo bản sao độc lập; phần demo dưới đây cũng cung cấp một hàm sao chép từng hàng có kiểm tra `null` để người đọc tự chạy thử.

## 7. Chương trình Java 17+ chạy độc lập

Tạo file **PartialRowsDemo.java**:

~~~java
import java.util.Arrays;

public final class PartialRowsDemo {
    private static long sumNonNullRows(int[][] values) {
        if (values == null) {
            return 0;
        }
        long sum = 0;
        for (int[] row : values) {
            if (row == null) {
                continue;
            }
            for (int number : row) {
                sum += number;
            }
        }
        return sum;
    }

    private static int countElements(int[][] values) {
        if (values == null) {
            return 0;
        }
        int count = 0;
        for (int[] row : values) {
            if (row != null) {
                count += row.length;
            }
        }
        return count;
    }

    private static int[][] deepCopy(int[][] source) {
        if (source == null) {
            return null;
        }
        int[][] copy = new int[source.length][];
        for (int i = 0; i < source.length; i++) {
            copy[i] = source[i] == null ? null : source[i].clone();
        }
        return copy;
    }

    public static void main(String[] args) {
        int[][] data = new int[4][];
        System.out.println("outerLength=" + data.length);
        System.out.println("initial=" + Arrays.deepToString(data));
        System.out.println("row1Null=" + (data[1] == null));

        data[0] = new int[2];
        data[1] = new int[] {3, 4, 5};
        data[2] = new int[0];
        data[3] = new int[1];
        System.out.println("allocated=" + Arrays.deepToString(data));
        System.out.println("row0Length=" + data[0].length);
        System.out.println("emptyRowLength=" + data[2].length);
        System.out.println("emptyRowIsNull=" + (data[2] == null));

        data[0][1] = 9;
        data[3][0] = 7;
        System.out.println("edited=" + Arrays.deepToString(data));

        int[] savedRow = data[1];
        data[1][0] = 8;
        System.out.println("savedAfterMutation=" + Arrays.toString(savedRow));

        data[1] = new int[] {6};
        System.out.println("afterReplace=" + Arrays.deepToString(data));
        System.out.println("oldSavedRow=" + Arrays.toString(savedRow));
        System.out.println("sum=" + sumNonNullRows(data));
        System.out.println("elementCount=" + countElements(data));

        int[][] copy = deepCopy(data);
        copy[0][0] = 99;
        System.out.println("afterCopySource=" + Arrays.deepToString(data));
        System.out.println("afterCopyNew=" + Arrays.deepToString(copy));

        int[][] rectangular = new int[2][3];
        System.out.println("rectangular=" + Arrays.deepToString(rectangular));

        int[][] incomplete = new int[1][];
        try {
            System.out.println(incomplete[0].length);
        } catch (NullPointerException ex) {
            System.out.println("uncreatedRow=NullPointerException");
        }
        try {
            System.out.println(data[2][0]);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("emptyRow=ArrayIndexOutOfBoundsException");
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 PartialRowsDemo.java
java PartialRowsDemo
~~~

**Expected stdout chính xác:**

~~~text
outerLength=4
initial=[null, null, null, null]
row1Null=true
allocated=[[0, 0], [3, 4, 5], [], [0]]
row0Length=2
emptyRowLength=0
emptyRowIsNull=false
edited=[[0, 9], [3, 4, 5], [], [7]]
savedAfterMutation=[8, 4, 5]
afterReplace=[[0, 9], [6], [], [7]]
oldSavedRow=[8, 4, 5]
sum=22
elementCount=4
afterCopySource=[[0, 9], [6], [], [7]]
afterCopyNew=[[99, 9], [6], [], [7]]
rectangular=[[0, 0, 0], [0, 0, 0]]
uncreatedRow=NullPointerException
emptyRow=ArrayIndexOutOfBoundsException
~~~

`initial` thể hiện chỉ tạo mảng ngoài; `allocated` thể hiện cấp phát từng hàng và độ dài không đều. `uncreatedRow` khác `emptyRow`: một bên là null, bên kia là đối tượng dài 0. `afterCopySource` và `afterCopyNew` cho thấy sao chép từng hàng tạo dữ liệu số độc lập.

## 8. Lỗi thường gặp và bài tập

| Lỗi / hiểu lầm | Cách xử lý |
| --- | --- |
| `new int[3][]` tạo sẵn ba hàng `int[]` | Sai: ban đầu cả ba tham chiếu hàng đều null |
| `matrix[i].length` khi `matrix[i] == null` | Guard hoặc khởi tạo hàng trước; nếu không sẽ NPE |
| Cho rằng `new int[0]` là null | Sai: đó là một đối tượng mảng rỗng |
| Lấy độ dài một hàng dùng cho mọi hàng | Dùng `matrix[i].length`, vì mỗi hàng có thể dài khác nhau |
| `matrix[i] = {1, 2};` sau khi tạo outer | Dùng `matrix[i] = new int[]{1, 2};` |
| `new int[][2]` | Sai: không được bỏ kích thước chiều trước rồi khai báo kích thước chiều sau |
| `matrix.clone()` sao chép luôn từng hàng | Chỉ sao chép outer; muốn độc lập thì clone từng hàng |
| Duyệt tất cả hàng mà không kiểm tra null | Có thể NPE; xử lý theo hợp đồng dữ liệu |

**Bài 1.** Tạo `int[][] rows = new int[3][];`, in `Arrays.deepToString(rows)`, sau đó cấp phát lần lượt các hàng có độ dài 2, 0 và 4.

**Bài 2.** Phân biệt đầu ra khi truy cập `rows[1].length` lúc hàng chưa cấp phát và sau khi gán `rows[1] = new int[0]`.

**Bài 3.** Dùng hai vòng `for` để tạo mảng tam giác bốn hàng, trong đó hàng `i` có độ dài `i + 1` và phần tử `[i][j] = i + j`.

**Bài 4.** Viết hàm đếm số phần tử thật của mảng không đều có thể chứa hàng null; thử với `{{1, 2}, null, {}, {3}}`.

**Bài 5.** So sánh `Arrays.copyOf(matrix, matrix.length)` với việc sao chép từng hàng `matrix[i].clone()`. Khi sửa một ô số ở bản sao, bản gốc có đổi không?

### Ghi nhớ

**`new int[rows][]` chỉ tạo mảng ngoài; các hàng ban đầu là `null` cho tới khi được gán mảng con.** Mỗi hàng có thể có độ dài riêng, kể cả 0. **Hàng null không phải hàng rỗng**: phải cấp phát hoặc guard trước khi dùng `length`, truy cập chỉ số hay duyệt. Sao chép mảng ngoài không tự sao chép các hàng; muốn dữ liệu độc lập, sao chép từng mảng con.
