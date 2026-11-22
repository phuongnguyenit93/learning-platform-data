# Duyệt bằng chỉ số hoặc enhanced `for` lồng nhau — Java 17+

## 1. Hiểu mảng hai chiều trước khi duyệt

Trong Java, mảng hai chiều như `int[][] matrix` là **mảng các tham chiếu tới mảng `int[]`**. Có thể hình dung mỗi mảng con là một hàng:

~~~java
int[][] matrix = {
    {3, 1, 4},
    {1, 5},
    {},
    {9}
};
~~~

~~~text
Hàng 0: [3, 1, 4]  -> length = 3
Hàng 1: [1, 5]     -> length = 2
Hàng 2: []         -> length = 0
Hàng 3: [9]        -> length = 1
~~~

- `matrix.length` là số **hàng**: ở đây là `4`.
- `matrix[i]` là một **mảng một chiều** `int[]`.
- `matrix[i].length` là số phần tử của **hàng i**, không nhất thiết bằng số phần tử hàng khác.
- `matrix[i][j]` là phần tử ở hàng `i`, cột/chỉ số trong hàng `j`.
- Chỉ số bắt đầu từ `0`; hàng `i` có chỉ số phần tử hợp lệ từ `0` đến `matrix[i].length - 1`.

Ví dụ trên là mảng **có các hàng dài khác nhau** (*jagged/ragged array*), một cấu trúc Java hoàn toàn hợp lệ. Vì vậy, khi duyệt phải xét `matrix[i].length`, không tự giả định mọi hàng dài bằng `matrix[0].length`.

## 2. Duyệt bằng hai vòng `for` có chỉ số

Dạng chuẩn khi cần biết vị trí phần tử:

~~~java
for (int i = 0; i < matrix.length; i++) {
    for (int j = 0; j < matrix[i].length; j++) {
        System.out.println("[" + i + "][" + j + "]="
                + matrix[i][j]);
    }
}
~~~

Vòng ngoài chọn **hàng i**. Vòng trong duyệt các phần tử **j của chính hàng i**. Với `matrix` ở mục 1, stdout là:

~~~text
[0][0]=3
[0][1]=1
[0][2]=4
[1][0]=1
[1][1]=5
[3][0]=9
~~~

Hàng 2 rỗng nên vòng trong không chạy; không có phần tử `matrix[2][0]` để in. Thứ tự lặp trên đây là **theo hàng** (*row-major traversal*): xử lý hết hàng hiện tại trước khi sang hàng kế.

Có thể đặt tên biến rõ nghĩa hơn:

~~~java
for (int rowIndex = 0; rowIndex < matrix.length; rowIndex++) {
    for (int colIndex = 0;
         colIndex < matrix[rowIndex].length;
         colIndex++) {
        int value = matrix[rowIndex][colIndex];
        // Sử dụng value và cả hai chỉ số khi cần.
    }
}
~~~

**Ưu điểm:** biết được tọa độ, có thể gán `matrix[i][j] = ...`, truy cập hàng xóm hoặc chỉ duyệt một khoảng chỉ số. **Nhược điểm:** cú pháp dài hơn và phải viết điều kiện biên cẩn thận.

## 3. Duyệt bằng enhanced `for` lồng nhau

Enhanced `for` (hay *for-each*) đưa ra lần lượt **giá trị phần tử**, không yêu cầu người viết chỉ số:

~~~java
for (int[] row : matrix) {
    for (int value : row) {
        System.out.println(value);
    }
}
~~~

**Exact stdout:**

~~~text
3
1
4
1
5
9
~~~

Cách đọc cú pháp:

- `for (int[] row : matrix)`: vì `matrix` có kiểu `int[][]`, mỗi phần tử `row` có kiểu **`int[]`**.
- `for (int value : row)`: vì `row` có kiểu `int[]`, mỗi `value` là một **`int`**.
- Hàng rỗng không sinh ra lượt lặp bên trong.
- Thứ tự vẫn là duyệt lần lượt từng hàng, rồi từng giá trị trong hàng.

Điểm mạnh là code ngắn, ít rủi ro viết sai điều kiện `i < length`/`j < length`, phù hợp cho **đọc, tính tổng, đếm, tìm kiếm tuyến tính** khi không cần tọa độ.

Đừng viết `for (int value : matrix)`: phần tử của `int[][]` là `int[]`, không phải `int`; đoạn này không biên dịch.

## 4. Chọn kiểu duyệt theo mục đích

| Nhu cầu | Nên dùng | Lý do |
|---|---|---|
| In, cộng hoặc đếm mọi giá trị | Enhanced `for` lồng nhau | Ngắn và rõ |
| In `(row, column)` của phần tử | Hai `for` có chỉ số | Có tọa độ trực tiếp |
| Gán lại phần tử kiểu nguyên thủy | `matrix[i][j] = ...` | Ghi vào đúng ô trong mảng |
| Thay cả mảng con ở hàng `i` | `matrix[i] = new int[]{...}` | Cần chỉ số hàng |
| Tính tổng từng hàng, trả `int[]` | Kết hợp vòng ngoài có chỉ số, vòng trong enhanced `for` | Cần vị trí kết quả, không cần chỉ số từng giá trị |
| So sánh hàng xóm `[i][j-1]`, `[i][j+1]` | `for` có chỉ số và kiểm tra biên | Cần truy cập có vị trí |
| Có hàng dài khác nhau | Cả hai dạng đều được | Luôn dùng độ dài của từng hàng |

Không có kiểu vòng lặp “tốt nhất” trong mọi trường hợp. Chọn cách diễn đạt đúng điều cần làm; hai dạng thường cho cùng thứ tự đọc nếu cùng duyệt từ đầu đến cuối.

## 5. Sửa giá trị: bẫy của biến lặp enhanced `for`

Xét mảng:

~~~java
int[][] data = {{1, 2}, {3}};
for (int[] row : data) {
    for (int value : row) {
        value = value * 10;
    }
}
System.out.println(java.util.Arrays.deepToString(data));
~~~

**Exact stdout:**

~~~text
[[1, 2], [3]]
~~~

`value` chỉ là **biến cục bộ** nhận bản sao giá trị `int` của từng phần tử. Gán lại `value` **không ghi ngược** vào `row[j]`.

Muốn thay các số nguyên trong mảng, hãy dùng chỉ số:

~~~java
for (int i = 0; i < data.length; i++) {
    for (int j = 0; j < data[i].length; j++) {
        data[i][j] *= 10;
    }
}
System.out.println(java.util.Arrays.deepToString(data));
~~~

**Exact stdout (tiếp theo ví dụ):**

~~~text
[[10, 20], [30]]
~~~

Nhưng biến `row` trong `for (int[] row : data)` **chứa tham chiếu tới mảng con đang được duyệt**, nên thao tác **sửa phần tử qua row** vẫn tác động mảng:

~~~java
for (int[] row : data) {
    if (row.length > 0) {
        row[0] = 0;
    }
}
System.out.println(java.util.Arrays.deepToString(data));
~~~

**Exact stdout (tiếp theo ví dụ):**

~~~text
[[0, 20], [0]]
~~~

Phân biệt:

- `value = 99;`: chỉ gán lại biến `int` cục bộ.
- `row[0] = 99;`: gán vào phần tử trong **mảng con hiện có**.
- `row = new int[]{99};`: chỉ gán lại biến tham chiếu `row` của vòng lặp; **không thay** `data[i]`.
- `data[i] = new int[]{99};`: thay tham chiếu mảng con thực tế ở hàng `i`.

## 6. Kết hợp hai cách duyệt: tổng, số phần tử và tổng mỗi hàng

Tính tổng/số phần tử bằng enhanced `for`:

~~~java
int sum = 0;
int count = 0;
for (int[] row : matrix) {
    for (int value : row) {
        sum += value;
        count++;
    }
}
System.out.println(sum);
System.out.println(count);
~~~

Với `matrix = {{3,1,4},{1,5},{},{9}}`, **exact stdout**:

~~~text
23
6
~~~

Hàng rỗng góp **0 giá trị** vào tổng và số lượng. Số phần tử của mảng có hàng khác độ dài phải tính `count` (hoặc tổng `row.length`), **không** lấy `matrix.length * matrix[0].length`.

Khi cần tổng **theo từng hàng** cùng thứ tự với hàng gốc, kết hợp vòng ngoài có chỉ số và vòng trong enhanced `for`:

~~~java
int[] rowSums = new int[matrix.length];
for (int i = 0; i < matrix.length; i++) {
    for (int value : matrix[i]) {
        rowSums[i] += value;
    }
}
System.out.println(java.util.Arrays.toString(rowSums));
~~~

**Exact stdout:**

~~~text
[8, 6, 0, 9]
~~~

Cả hai cách đều không sửa `matrix` khi chỉ đọc các phần tử.

## 7. Hàng rỗng, hàng `null` và mảng ngoài `null`

Java có thể tạo mảng hai chiều với một số mảng con **chưa được tạo**:

~~~java
int[][] partial = new int[3][];
partial[0] = new int[]{2, 3};
partial[1] = null;
partial[2] = new int[0];
~~~

`partial.length == 3`, nhưng:

| Hàng | Giá trị | Có thể duyệt phần tử ngay? |
|---|---|---|
| `partial[0]` | `[2,3]` | Có, 2 phần tử |
| `partial[1]` | `null` | **Không**; `.length` hoặc enhanced `for` trên hàng này ném `NullPointerException` |
| `partial[2]` | Mảng rỗng | Có, vòng trong chạy 0 lượt |

Cách duyệt phòng vệ khi dữ liệu có thể chứa hàng `null`:

~~~java
int total = 0;
if (partial != null) {
    for (int[] row : partial) {
        if (row == null) {
            continue;
        }
        for (int value : row) {
            total += value;
        }
    }
}
System.out.println(total);
~~~

**Exact stdout:**

~~~text
5
~~~

Kiểm tra `row == null` cần làm **trước** khi truy cập `row.length` hoặc duyệt `for (int value : row)`. Nếu ngay cả mảng ngoài có thể null, cũng phải kiểm tra `matrix != null` trước khi đọc `matrix.length` hoặc lặp qua nó.

Không phải chương trình nào cũng nên **bỏ qua null**: đôi khi null là lỗi dữ liệu và cần ném `IllegalArgumentException`. Chính sách xử lý do bài toán quyết định; điều quan trọng là **không nhầm null với mảng rỗng**.

## 8. In mảng nhiều chiều và lỗi thường gặp

~~~java
int[][] matrix = {{1, 2}, {3}};
System.out.println(java.util.Arrays.deepToString(matrix));
~~~

**Exact stdout:**

~~~text
[[1, 2], [3]]
~~~

`Arrays.deepToString(matrix)` hiển thị **các mảng con lồng nhau**. `Arrays.toString(matrix)` chỉ áp dụng trực tiếp lên **mảng ngoài**, nên có thể in dạng tham chiếu của các mảng con thay vì toàn bộ giá trị số; không dùng đầu ra ấy để so sánh dữ liệu.

Các bẫy cần tránh:

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| `j < matrix.length` ở vòng trong | Số hàng không nhất thiết là số phần tử hàng `i` | `j < matrix[i].length` |
| `j < matrix[0].length` cho mọi hàng | Có thể vượt biên hoặc bỏ sót phần tử | Dùng độ dài của từng hàng |
| `j <= matrix[i].length` | Đụng chỉ số ngoài mảng | Dùng `<`, không dùng `<=` |
| Duyệt `for (int v : matrix)` | Sai kiểu: mỗi phần tử mảng ngoài là `int[]` | `for (int[] row : matrix)` |
| Gán `v = ...` và mong mảng đổi | Chỉ đổi biến vòng lặp | Dùng `matrix[i][j] = ...` |
| Không kiểm tra hàng `null` khi dữ liệu cho phép | `NullPointerException` | Kiểm tra hàng trước vòng trong |
| Dùng `matrix.length * matrix[0].length` để đếm mọi phần tử | Sai với hàng khác độ dài, lỗi nếu không có hàng | Cộng `row.length` hoặc đếm trong vòng lặp |
| In `Arrays.toString(matrix)` | Không cho dạng giá trị lồng nhau dễ đọc | `Arrays.deepToString(matrix)` |

## 9. Chương trình Java 17+ hoàn chỉnh

Tạo file đúng tên **`NestedArrayIterationDemo.java`**:

~~~java
import java.util.Arrays;

public final class NestedArrayIterationDemo {
    private NestedArrayIterationDemo() {}

    static void showIndexed(int[][] matrix) {
        for (int rowIndex = 0; rowIndex < matrix.length; rowIndex++) {
            int[] row = matrix[rowIndex];
            System.out.println("row " + rowIndex
                    + " length=" + row.length);

            for (int colIndex = 0; colIndex < row.length; colIndex++) {
                System.out.println("cell[" + rowIndex + "]["
                        + colIndex + "]=" + row[colIndex]);
            }
        }
    }

    static int[] sumAndCount(int[][] matrix) {
        int sum = 0;
        int count = 0;
        for (int[] row : matrix) {
            for (int value : row) {
                sum += value;
                count++;
            }
        }
        return new int[]{sum, count};
    }

    static int[] rowSums(int[][] matrix) {
        int[] sums = new int[matrix.length];
        for (int i = 0; i < matrix.length; i++) {
            for (int value : matrix[i]) {
                sums[i] += value;
            }
        }
        return sums;
    }

    static int[][] doubledCopy(int[][] matrix) {
        int[][] result = new int[matrix.length][];
        for (int i = 0; i < matrix.length; i++) {
            result[i] = Arrays.copyOf(matrix[i], matrix[i].length);
            for (int j = 0; j < result[i].length; j++) {
                result[i][j] *= 2;
            }
        }
        return result;
    }

    static int sumSkippingNullRows(int[][] matrix) {
        if (matrix == null) return 0;
        int sum = 0;
        for (int[] row : matrix) {
            if (row == null) continue;
            for (int value : row) {
                sum += value;
            }
        }
        return sum;
    }

    public static void main(String[] args) {
        int[][] grid = {{3, 1, 4}, {1, 5}, {}, {9}};

        System.out.println("matrix=" + Arrays.deepToString(grid));
        System.out.println("rows=" + grid.length);
        showIndexed(grid);

        int[] stats = sumAndCount(grid);
        System.out.println("enhanced sum=" + stats[0]);
        System.out.println("enhanced count=" + stats[1]);
        System.out.println("row sums=" + Arrays.toString(rowSums(grid)));

        int[][] doubled = doubledCopy(grid);
        System.out.println("doubled=" + Arrays.deepToString(doubled));
        System.out.println("original=" + Arrays.deepToString(grid));

        for (int[] row : grid) {
            for (int value : row) {
                value += 100; // Không ghi vào phần tử int gốc.
            }
        }
        System.out.println("after local value change="
                + Arrays.deepToString(grid));

        grid[0][1] = 7; // Cần tọa độ thì dùng chỉ số.
        System.out.println("after indexed change="
                + Arrays.deepToString(grid));

        for (int[] row : grid) {
            if (row.length > 0) {
                row[0] *= 10; // Sửa qua tham chiếu mảng con.
            }
        }
        System.out.println("after row reference change="
                + Arrays.deepToString(grid));

        int[][] withNullRow = {{2, 3}, null, {}, {5}};
        System.out.println("nullable sum="
                + sumSkippingNullRows(withNullRow));
    }
}
~~~

**Yêu cầu:** JDK 17 hoặc mới hơn, không cần thư viện ngoài hay preview features. Chạy terminal trong thư mục chứa file.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 NestedArrayIterationDemo.java
java -cp . NestedArrayIterationDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\NestedArrayIterationDemo.java
java -cp . NestedArrayIterationDemo
~~~

### Exact expected stdout

~~~text
matrix=[[3, 1, 4], [1, 5], [], [9]]
rows=4
row 0 length=3
cell[0][0]=3
cell[0][1]=1
cell[0][2]=4
row 1 length=2
cell[1][0]=1
cell[1][1]=5
row 2 length=0
row 3 length=1
cell[3][0]=9
enhanced sum=23
enhanced count=6
row sums=[8, 6, 0, 9]
doubled=[[6, 2, 8], [2, 10], [], [18]]
original=[[3, 1, 4], [1, 5], [], [9]]
after local value change=[[3, 1, 4], [1, 5], [], [9]]
after indexed change=[[3, 7, 4], [1, 5], [], [9]]
after row reference change=[[30, 7, 4], [10, 5], [], [90]]
nullable sum=10
~~~

**Giải thích đầu ra:** có 4 hàng nhưng tổng cộng chỉ 6 phần tử; tổng `3+1+4+1+5+9=23`. Dùng enhanced `for` để gán lại biến `value` không sửa các số trong `grid`. Ghi `grid[0][1] = 7` đổi một vị trí; sửa `row[0]` thông qua biến hàng kiểu `int[]` cũng đổi dữ liệu của mảng. `withNullRow` được xử lý bằng cách bỏ qua hàng null, do đó `2+3+5=10`.

## 10. Luyện tập và đáp án

**A.** Với `int[][] a = {{2, 4}, {}, {6}}`, có bao nhiêu hàng và phần tử?  
**Đáp án:** `a.length == 3`; tổng số phần tử là `2+0+1=3`, không phải `3*2`.

**B.** Thay vòng trong có chỉ số bằng enhanced `for` khi chỉ cần in giá trị:

~~~java
for (int i = 0; i < a.length; i++) {
    for (int j = 0; j < a[i].length; j++) {
        System.out.println(a[i][j]);
    }
}
~~~

**Đáp án:**

~~~java
for (int[] row : a) {
    for (int value : row) {
        System.out.println(value);
    }
}
~~~

**C.** Vì sao `for (int value : a)` lỗi khi `a` có kiểu `int[][]`?  
**Đáp án:** phần tử của `a` có kiểu `int[]`; vòng ngoài phải khai báo `int[] row`.

**D.** Với `int[][] a = {{1}, {2,3}}`, đoạn `for(int[] row:a) for(int v:row) v=0;` có đưa mảng về 0 không?  
**Đáp án:** **không**; chỉ gán lại biến `v`, không sửa mảng. Cần `a[i][j]=0`.

**E.** Khi nào dùng `matrix[i][j]` thay vì enhanced `for`?  
**Đáp án:** khi cần **chỉ số**, cần sửa trực tiếp ô có tọa độ, hoặc cần truy cập hàng xóm và giới hạn một khoảng vị trí.

**F.** Nếu `matrix[1] == null`, có được viết `matrix[1].length` không?  
**Đáp án:** không; sẽ ném `NullPointerException` nếu thực thi. Phải kiểm tra `matrix[1] != null` hoặc xác định chính sách từ chối null.

## 11. Checklist và kết luận

- [ ] Hiểu `int[][]` là mảng chứa các mảng `int[]`.
- [ ] Biết số hàng là `matrix.length`, độ dài hàng i là `matrix[i].length`.
- [ ] Duyệt bằng chỉ số với `i < matrix.length`, `j < matrix[i].length`.
- [ ] Duyệt bằng enhanced `for` với `int[] row` ngoài, `int value` trong.
- [ ] Không giả định mọi hàng có cùng độ dài hoặc đều khác `null`.
- [ ] Phân biệt gán lại biến enhanced `for` với sửa phần tử qua chỉ số/tham chiếu hàng.
- [ ] Biết kết hợp outer index với inner enhanced `for` khi cần tổng mỗi hàng.
- [ ] Dùng `Arrays.deepToString` để in nội dung mảng lồng.
- [ ] Chạy `NestedArrayIterationDemo.java` trên JDK 17+ và so sánh stdout.

**Kết luận:** Hai vòng `for` có chỉ số phù hợp khi cần **tọa độ hoặc chỉnh sửa phần tử**, còn enhanced `for` lồng nhau phù hợp khi chỉ cần **duyệt giá trị**. Cả hai đều phải tôn trọng độ dài của **từng hàng** trong mảng Java nhiều chiều; kiểm tra `null` khi mảng con có thể chưa được tạo.