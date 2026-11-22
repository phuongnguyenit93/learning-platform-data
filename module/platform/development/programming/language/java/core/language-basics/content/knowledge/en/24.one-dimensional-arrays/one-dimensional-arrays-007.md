# Đọc, cập nhật và duyệt phần tử của mảng một chiều trong Java

## 1. Chỉ số, độ dài và giá trị phần tử

Mảng một chiều (`T[]`) chứa một số lượng phần tử **cố định** sau khi được tạo. Các phần tử có cùng kiểu `T`, được truy cập bằng **chỉ số** (`index`) bắt đầu từ **0**. Với mảng `a` dài `n`, các chỉ số hợp lệ là `0` đến `n - 1`.

```java
int[] a = {10, 20, 30};
int first = a[0];          // Đọc: 10
int second = a[1];         // Đọc: 20
a[1] = 25;                 // Cập nhật phần tử thứ hai
int last = a[a.length - 1];// Đọc: 30
int count = a.length;      // 3
```

- `a[i]` **đọc** giá trị tại chỉ số `i` trong một biểu thức; `a[i] = value` **ghi đè** giá trị ở chỉ số đó. Phép gán phải tương thích với kiểu phần tử.
- `a.length` là **trường** của mảng, không phải phương thức `length()` như `String`, và không tự thay đổi khi gán phần tử.
- Phần tử đầu là `a[0]`; phần tử cuối là `a[a.length - 1]` **chỉ khi mảng không rỗng**.
- Với `new int[3]`, ba phần tử mặc định đều là `0`; `new boolean[3]` là `false`; phần tử kiểu tham chiếu như `String[]` mặc định là `null`. Biến cục bộ chưa được gán giá trị không có quyền đọc, dù phần tử trong mảng vừa cấp phát đã có giá trị mặc định.

Đọc hoặc cập nhật một phần tử theo chỉ số hợp lệ có độ phức tạp thời gian **O(1)**. Mảng không tự tăng/giảm số phần tử; để có kích thước mới cần tạo mảng mới (chẳng hạn `Arrays.copyOf`).

## 2. Các cách duyệt mảng

| Cách duyệt | Dùng khi nào? | Có thể cập nhật phần tử ngay trong vòng lặp? |
| --- | --- | --- |
| `for (int i = 0; i < a.length; i++)` | Cần chỉ số, duyệt xuôi, thay giá trị, lọc theo vị trí | Có: `a[i] = ...` |
| `for (int i = a.length - 1; i >= 0; i--)` | Duyệt ngược từ cuối về đầu | Có: `a[i] = ...` |
| `while (i < a.length)` | Điều kiện lặp/phạm vi bước nhảy linh hoạt | Có, nếu dùng chỉ số hợp lệ |
| `for (int value : a)` (*enhanced for*, *for-each*) | Chỉ cần **đọc** từng giá trị theo thứ tự | Gán vào biến `value` không làm đổi phần tử mảng |

Các vòng duyệt đầy đủ thường tốn **O(n)** thời gian với `n = a.length`. Khi chỉ đọc/tổng hợp, `for-each` dễ đọc và ít mắc lỗi chỉ số; khi sửa các phần tử kiểu nguyên thủy, ưu tiên vòng lặp có chỉ số.

Cần chú ý: `for (int value : a) { value *= 2; }` chỉ thay đổi **biến cục bộ** `value`. Mảng `a` giữ nguyên. Tương tự, với mảng đối tượng, gán lại biến tham chiếu trong `for-each` không thay tham chiếu tại vị trí mảng; tuy vậy gọi phương thức làm đổi trạng thái của chính đối tượng được tham chiếu vẫn có thể ảnh hưởng đến đối tượng.

## 3. Ví dụ Java 17+ chạy độc lập

Lưu vào tệp **`DemoMang.java`**:

```java
import java.util.Arrays;

public class DemoMang {
    public static void main(String[] args) {
        int[] diem = {4, 7, 9};
        System.out.println("Ban dau: " + Arrays.toString(diem));

        // Đọc rồi cập nhật một phần tử bằng chỉ số.
        int giaTriCu = diem[1];
        diem[1] = 8;
        System.out.println("Gia tri cu: " + giaTriCu);
        System.out.println("Sau cap nhat: " + Arrays.toString(diem));

        // Duyệt xuôi bằng chỉ số.
        System.out.print("For:");
        for (int i = 0; i < diem.length; i++) {
            System.out.print(" " + diem[i]);
        }
        System.out.println();

        // Duyệt chỉ để đọc: for-each.
        System.out.print("For-each:");
        for (int value : diem) {
            System.out.print(" " + value);
        }
        System.out.println();

        // Cập nhật tất cả phần tử, bắt buộc gán về diem[i].
        for (int i = 0; i < diem.length; i++) {
            diem[i] += 1;
        }
        System.out.println("Tang moi phan tu: " + Arrays.toString(diem));

        // Tổng hợp dữ liệu bằng for-each.
        int tong = 0;
        for (int value : diem) {
            tong += value;
        }
        System.out.println("Tong: " + tong);

        // Duyệt ngược theo chỉ số.
        System.out.print("Nguoc:");
        for (int i = diem.length - 1; i >= 0; i--) {
            System.out.print(" " + diem[i]);
        }
        System.out.println();
    }
}
```

Mở terminal tại thư mục chứa tệp, dùng **JDK 17 trở lên** (PowerShell, CMD, bash đều dùng được):

```bash
javac -encoding UTF-8 DemoMang.java
java DemoMang
```

Kết quả trên stdout (**lệnh `javac` biên dịch thành công không in gì**):

```text
Ban dau: [4, 7, 9]
Gia tri cu: 7
Sau cap nhat: [4, 8, 9]
For: 4 8 9
For-each: 4 8 9
Tang moi phan tu: [5, 9, 10]
Tong: 24
Nguoc: 10 9 5
```

Trong chương trình: giá trị `7` đọc vào `giaTriCu` không tự đổi khi `diem[1]` được gán `8`; sau vòng tăng mỗi phần tử, mảng trở thành `[5, 9, 10]`. Lệnh `Arrays.toString(diem)` giúp in nội dung mảng một chiều thay vì kết quả mặc định của `diem.toString()`.

## 4. Kiểm tra giới hạn và mảng rỗng

Java kiểm tra chỉ số tại thời điểm truy cập. `a[-1]` và `a[a.length]` gây **`ArrayIndexOutOfBoundsException`**; gọi `a.length` hoặc `a[i]` khi `a == null` gây **`NullPointerException`**. Không nên dựa vào ngoại lệ để điều khiển luồng xử lý thông thường.

```java
int[] a = {};
if (a != null && a.length > 0) {
    System.out.println(a[a.length - 1]);
} else {
    System.out.println("Mang rong");
}

int index = 2;
if (a != null && index >= 0 && index < a.length) {
    System.out.println(a[index]);
}
```

Mảng rỗng (`new int[0]` hoặc `{}`) có `length == 0`; các vòng `for` và `for-each` duyệt từ đầu không chạy lần nào, nên an toàn. Tuy nhiên truy cập `a[0]` hoặc phần tử cuối là không hợp lệ. Đối với chỉ số nhập từ người dùng, kiểm tra **`0 <= index && index < a.length`** trước cả khi đọc và ghi.

## 5. Một số thao tác thường gặp

**Tìm phần tử đầu tiên thỏa điều kiện**: vòng `for` có chỉ số trả về vị trí, hoặc `-1` khi không tìm thấy:

```java
int[] a = {4, 8, 9};
int foundIndex = -1;
for (int i = 0; i < a.length; i++) {
    if (a[i] == 8) {
        foundIndex = i;
        break;
    }
}
// foundIndex == 1
```

**Cập nhật có điều kiện**: duyệt bằng chỉ số rồi ghi lại phần tử mong muốn:

```java
for (int i = 0; i < a.length; i++) {
    if (a[i] % 2 == 0) {
        a[i] *= 2;
    }
}
// a = [8, 16, 9]
```

**Tránh ảnh hưởng ngoài ý muốn khi dùng chung tham chiếu**:

```java
int[] original = {1, 2};
int[] alias = original;
alias[0] = 99;               // original[0] cũng thành 99
int[] copy = original.clone(); // Mảng int[] riêng
copy[0] = 5;                  // original[0] vẫn là 99
```

Với mảng chứa đối tượng, `clone()` chỉ sao chép cấu trúc mảng và **các tham chiếu**, không sao chép sâu từng đối tượng. Nếu cần đặt cùng một giá trị cho nhiều phần tử, có thể dùng `Arrays.fill(a, value)`; để tính giá trị mới từ chỉ số, có thể dùng `Arrays.setAll(a, i -> ...)` đúng với kiểu mảng tương ứng.

## 6. Lỗi phổ biến và nguyên tắc lựa chọn

- **Lệch một chỉ số**: `for (int i = 0; i <= a.length; i++)` sẽ cố truy cập `a[a.length]`. Khi đi xuôi toàn mảng dùng điều kiện `i < a.length`.
- **Nhầm thứ tự**: phần tử thứ `k` (đếm từ 1) có chỉ số `k - 1`; phần tử cuối là `length - 1`.
- **Nhầm `length` với `length()`**: `array.length` khác `string.length()`.
- **Gán biến `for-each` rồi tưởng mảng đổi**: dùng `a[i] = newValue` nếu thực sự cần thay phần tử.
- **Quên mảng rỗng hoặc `null`**: kiểm tra trước khi lấy phần tử đầu/cuối và khi xử lý đầu vào không bảo đảm.
- **Nhầm thay giá trị với thêm phần tử**: `a[i] = ...` chỉ thay thế tại vị trí hiện có; số lượng phần tử không tăng.
- **Nhầm giá trị và tham chiếu**: `int x = a[i]` sao chép giá trị `int`; khi phần tử là đối tượng, phép đọc sao chép tham chiếu tới đối tượng đó.

**Ghi nhớ:** dùng `a[i]` để đọc/ghi đúng vị trí, `a.length` để khống chế biên, `for` có chỉ số để thay đổi phần tử và `for-each` cho duyệt chỉ đọc.