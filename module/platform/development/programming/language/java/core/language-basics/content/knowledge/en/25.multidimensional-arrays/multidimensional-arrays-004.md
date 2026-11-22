# Lấy số hàng và độ dài của từng hàng trong mảng nhiều chiều Java

## 1. Mảng hai chiều thực chất là mảng chứa các mảng

Trong Java, `int[][]` là **mảng của các mảng `int[]`**. Mảng ngoài lưu tham chiếu đến từng mảng con (từng hàng). Vì vậy, các hàng **không bắt buộc có cùng số phần tử**.

```java
int[][] data = {
    {10, 20, 30}, // hàng 0: 3 phần tử
    {40},         // hàng 1: 1 phần tử
    {},           // hàng 2: 0 phần tử
    {50, 60}      // hàng 3: 2 phần tử
};
```

Có hai phép lấy độ dài khác nhau:

- **`data.length`** là số phần tử của mảng ngoài, tức **số hàng**: ở ví dụ trên là `4`.
- **`data[i].length`** là số phần tử của mảng con ở hàng `i`: lần lượt là `3`, `1`, `0`, `2`.
- Chỉ số hàng hợp lệ: `0 <= i && i < data.length`. Chỉ số cột của hàng `i` hợp lệ: `0 <= j && j < data[i].length`, nếu `data[i] != null`.

`length` là **trường** của mảng, không viết `length()`. Không có thuộc tính `data.columns` hay một “số cột” cố định áp dụng cho tất cả mảng hai chiều Java.

## 2. Phân biệt mảng chữ nhật và mảng răng cưa

| Cách tạo | `length` của mảng ngoài | Độ dài từng hàng |
| --- | ---: | --- |
| `new int[2][3]` | `2` | `3, 3` |
| `new int[3][0]` | `3` | `0, 0, 0` |
| `new int[0][3]` | `0` | Không có hàng để truy cập |
| `new int[][] {{1, 2}, {3}, {}}` | `3` | `2, 1, 0` |
| `new int[3][]` | `3` | Ba hàng ban đầu đều `null`; chưa thể gọi `.length` trên từng hàng |

**Mảng chữ nhật** có tất cả hàng khác `null` và cùng độ dài, ví dụ `new int[2][3]`. **Mảng răng cưa** (jagged/ragged array) chứa các hàng có độ dài khác nhau. Trong Java, ngay cả những hàng ban đầu cùng kích thước cũng có thể được gán lại bằng các mảng con khác độ dài:

```java
int[][] grid = new int[2][3];
grid[1] = new int[5];
// grid.length == 2
// grid[0].length == 3
// grid[1].length == 5
```

Phép gán trên **thay mảng con ở hàng 1**, không làm thay đổi `length` của mảng con ban đầu. Độ dài mỗi đối tượng mảng là cố định sau khi cấp phát; số hàng cũng cố định nếu vẫn dùng cùng mảng ngoài.

## 3. Ví dụ Java 17+ có thể biên dịch và chạy

Tạo tệp **`RowLengthsDemo.java`**:

```java
public class RowLengthsDemo {
    public static void main(String[] args) {
        int[][] data = {
            {10, 20, 30},
            {40},
            {},
            {50, 60}
        };

        System.out.println("So hang: " + data.length);

        int total = 0;
        for (int i = 0; i < data.length; i++) {
            int count = data[i].length;
            System.out.println("Hang " + i + ": " + count + " phan tu");
            total += count;
        }
        System.out.println("Tong so phan tu: " + total);

        // Mảng chữ nhật: mỗi hàng có độ dài 3.
        int[][] rectangle = new int[2][3];
        System.out.println("So hang chu nhat: " + rectangle.length);
        for (int i = 0; i < rectangle.length; i++) {
            System.out.println("Chu nhat hang " + i + ": " + rectangle[i].length);
        }

        // Mảng ngoài đã tạo, nhưng từng hàng có thể chưa được tạo.
        int[][] pending = new int[3][];
        pending[0] = new int[2];
        pending[1] = new int[0];
        for (int i = 0; i < pending.length; i++) {
            if (pending[i] == null) {
                System.out.println("Chua tao hang " + i + ": null");
            } else {
                System.out.println("Chua tao hang " + i + ": " + pending[i].length);
            }
        }
    }
}
```

Mở terminal trong thư mục chứa tệp với JDK 17 trở lên. Chạy trên Windows (CMD/PowerShell) hoặc Linux/macOS:

```bash
javac -encoding UTF-8 RowLengthsDemo.java
java RowLengthsDemo
```

Kết quả stdout (lệnh `javac` thành công không in kết quả):

```text
So hang: 4
Hang 0: 3 phan tu
Hang 1: 1 phan tu
Hang 2: 0 phan tu
Hang 3: 2 phan tu
Tong so phan tu: 6
So hang chu nhat: 2
Chu nhat hang 0: 3
Chu nhat hang 1: 3
Chua tao hang 0: 2
Chua tao hang 1: 0
Chua tao hang 2: null
```

Vòng `for` đầu duyệt số hàng bằng `data.length`, sau đó lấy số phần tử tại **từng hàng** bằng `data[i].length`. Tổng số phần tử thực tế bằng tổng các độ dài hàng đã được cấp phát. `new int[0]` là hàng **rỗng nhưng tồn tại**, khác với hàng `null` là **chưa tham chiếu đến mảng con**.

## 4. Duyệt an toàn và tính toán dựa trên độ dài từng hàng

Không dùng `data[0].length` để duyệt tất cả hàng nếu chưa biết chắc đây là mảng chữ nhật, có hàng đầu tiên và hàng đó khác `null`. Với mảng răng cưa, cần lấy `data[i].length` ngay tại hàng `i`:

```java
int[][] values = {{1, 2, 3}, {}, {4, 5}};
for (int row = 0; row < values.length; row++) {
    for (int col = 0; col < values[row].length; col++) {
        System.out.println(values[row][col]);
    }
}
// In lần lượt: 1, 2, 3, 4, 5 (mỗi số trên một dòng)
```

Với dữ liệu có thể chứa hàng `null`, kiểm tra trước khi lấy độ dài:

```java
int total = 0;
int[][] values = {new int[2], null, new int[3]};
for (int[] row : values) {
    if (row != null) {
        total += row.length;
    }
}
// total == 5
```

Nếu chính mảng ngoài cũng có thể `null`, kiểm tra `values != null` trước khi đọc `values.length`. Việc chọn coi hàng `null` là “không có phần tử” chỉ là quy ước để tính tổng; về mặt dữ liệu, hàng `null` khác hàng rỗng.

Để kiểm tra các hàng có cùng kích thước (mảng chữ nhật), cần so sánh **tất cả hàng** với độ dài kỳ vọng, đồng thời loại trường hợp `null`:

```java
int[][] values = {{1, 2}, {3, 4}, {5, 6}};
boolean rectangular = true;
int width = values.length == 0 ? 0 : (
        values[0] == null ? -1 : values[0].length);

for (int[] row : values) {
    if (row == null || row.length != width) {
        rectangular = false;
        break;
    }
}
// rectangular == true; width == 2
```

Đối với mảng ngoài rỗng, ở đây quy ước `width = 0` và `rectangular = true` vì không có hàng nào vi phạm. Tùy yêu cầu nghiệp vụ, có thể chọn cách khác để xử lý trường hợp không có hàng.

## 5. Các lỗi dễ gặp

1. **Nhầm `a.length` với `a[0].length`:** biểu thức thứ nhất đếm số hàng; biểu thức thứ hai chỉ đếm phần tử của hàng 0, không phải số hàng.
2. **Giả định mọi hàng có cùng độ dài:** vòng `for (int j = 0; j < a[0].length; j++)` có thể bỏ sót phần tử ở hàng dài hoặc gây lỗi ở hàng ngắn. Dùng `a[i].length` khi duyệt hàng `i`.
3. **Không kiểm tra mảng ngoài rỗng:** với `new int[0][3]`, `a.length == 0`, nhưng `a[0]` gây `ArrayIndexOutOfBoundsException`.
4. **Không kiểm tra hàng `null`:** với `new int[3][]`, `a[0].length` gây `NullPointerException`; cần cấp phát hàng hoặc kiểm tra `null`.
5. **Lấy `length()` thay `length`:** trên mảng dùng thuộc tính `length`; `String` mới dùng phương thức `length()`.
6. **Nhầm độ dài với chỉ số cuối:** nếu hàng `i` có `k` phần tử và `k > 0` thì phần tử cuối là `a[i][k - 1]`, không phải `a[i][k]`.

**Ghi nhớ:** `a.length` là số hàng; `a[i].length` là độ dài riêng của hàng `i` (chỉ khi hàng tồn tại). Mọi thao tác duyệt và truy cập cần tôn trọng ranh giới của từng hàng.