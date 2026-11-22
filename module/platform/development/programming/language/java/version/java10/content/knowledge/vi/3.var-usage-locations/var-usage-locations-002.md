# `var` trong phần khởi tạo của vòng lặp `for` (Java 10+)

## 1. Vấn đề và mục đích

Từ **Java 10**, Java cho phép khai báo biến cục bộ bằng `var` khi trình biên dịch có thể **suy luận kiểu tĩnh của biến từ biểu thức khởi tạo**. Quy tắc này áp dụng cả cho phần **khởi tạo (`ForInit`)** của vòng lặp `for` thông thường (*basic for loop*).

Hai đoạn mã dưới đây cho cùng hành vi:

```java
for (int index = 0; index < 3; index++) {
    System.out.println(index);
}
```

```java
for (var index = 0; index < 3; index++) {
    System.out.println(index);
}
```

Trong đoạn thứ hai, `0` là literal kiểu `int`, nên `index` **được suy ra là `int` ngay lúc biên dịch**. Trình biên dịch vẫn kiểm tra kiểu như bình thường: `var` không tạo kiểu động, không cho phép `index` tự đổi sang `String` hoặc kiểu khác sau đó, và không tạo thêm chi phí suy luận kiểu tại thời gian chạy.

**Mục đích** của `var` trong `for` là giảm phần khai báo kiểu lặp lại khi kiểu của biến đếm hoặc biến điều khiển đã rõ ở phép khởi tạo. Đây là lựa chọn nhằm làm mã ngắn, dễ đọc; không phải yêu cầu phải thay mọi `int`, `long` hoặc kiểu tường minh bằng `var`.

## 2. Cú pháp: `var` chỉ nằm trong phần khởi tạo

Một vòng lặp `for` thông thường có dạng:

```java
for (khoiTao; dieuKien; capNhat) {
    // Thân vòng lặp
}
```

- **`khoiTao` (ForInit):** thực hiện **một lần** trước lần kiểm tra điều kiện đầu tiên. Có thể là khai báo biến cục bộ với `var`.
- **`dieuKien`:** đánh giá trước mỗi lượt; nếu kết quả là `false` thì dừng, còn `true` thì chạy thân vòng lặp. Trong Java, biểu thức điều kiện phải có kiểu `boolean` hoặc `Boolean` (được unboxing khi cần).
- **Thân vòng lặp:** thực hiện khi điều kiện đúng.
- **`capNhat` (ForUpdate):** thực hiện sau thân vòng lặp của một lượt bình thường, rồi quay lại đánh giá điều kiện. `continue` hướng tới vòng `for` này cũng đi qua phần cập nhật; `break` hoặc `return` thì kết thúc/thoát luồng tương ứng.

Ví dụ với `var`:

```java
for (var index = 0; index < 5; index++) {
    System.out.println("index = " + index);
}
```

Diễn tiến:

```text
index = 0 được khởi tạo một lần (kiểu int)
    ↓
Kiểm tra index < 5
    ├─ false → kết thúc vòng lặp
    └─ true  → chạy thân vòng lặp
                   ↓
               index++
                   ↓
            quay lại kiểm tra
```

`index` là **một biến cục bộ của vòng lặp**, không phải biến mới được khai báo lại mỗi lần lặp. `var` chỉ xuất hiện trong phần khởi tạo của ví dụ; điều kiện và cập nhật là **biểu thức**, không phải nơi khai báo kiểu của biến.

## 3. Trình biên dịch suy luận kiểu như thế nào?

Kiểu của biến được xác định từ **kiểu tĩnh của biểu thức nằm bên phải dấu `=`**, tại chính thời điểm khai báo. Tên biến, cách dùng trong phần điều kiện, và những phép gán/cập nhật về sau **không được dùng để đoán lại kiểu**.

| Khai báo ở phần khởi tạo | Kiểu suy ra | Giải thích |
| --- | --- | --- |
| `for (var i = 0; ...; ...)` | `int` | Literal số nguyên `0` có kiểu `int`. |
| `for (var i = 0L; ...; ...)` | `long` | Hậu tố `L` tạo literal `long`. |
| `for (var step = 0.5; ...; ...)` | `double` | Literal thập phân mặc định là `double`. |
| `for (var i = Integer.valueOf(0); ...; ...)` | `Integer` | Biểu thức khởi tạo trả về `Integer`; phép `i++` nếu dùng cần unboxing/boxing. |
| `for (var index = names.size() - 1; ...; ...)` | `int` | `List.size()` trả về `int` (giả sử `names` là `List`). |

Những hàng có dấu `...` là **cú pháp minh họa**, không phải vòng lặp đầy đủ có thể chạy nguyên văn.

Ví dụ sử dụng chỉ số nguyên dài:

```java
for (var step = 2L; step <= 6L; step += 2L) {
    System.out.println("step=" + step);
}
```

Ở đây, `step` có kiểu `long` suốt vòng lặp. Output là:

```text
step=2
step=4
step=6
```

Nếu muốn `long`, ghi `0L` hoặc khai báo `long` tường minh; `var step = 0` sẽ tạo `int`, không tự nâng lên `long` chỉ vì điều kiện hoặc phần cập nhật sử dụng số lớn hơn.

### `var` vẫn được kiểm tra kiểu tĩnh

```java
for (var i = 0; i < 3; i++) {
    // i = "hai"; // Lỗi biên dịch: i có kiểu int
}
```

Trình biên dịch chỉ thay phần kiểu tường minh bằng kiểu suy ra; các quy tắc gán, so sánh và toán tử không thay đổi.

## 4. Phạm vi sống và phạm vi sử dụng của biến

Biến khai báo bằng `var` trong `ForInit` có phạm vi bao gồm **phần khởi tạo, điều kiện, cập nhật và thân vòng lặp**. Khi thoát câu lệnh `for`, tên biến ấy không còn nằm trong phạm vi truy cập.

```java
for (var index = 0; index < 2; index++) {
    System.out.println(index); // Hợp lệ: dùng trong thân vòng lặp
}
// System.out.println(index);  // Lỗi biên dịch: index ngoài phạm vi
```

Bạn cũng có thể khai báo lại cùng một tên ở **vòng lặp độc lập sau đó**, vì phạm vi của vòng trước đã kết thúc:

```java
for (var i = 0; i < 2; i++) {
    System.out.println("A" + i);
}
for (var i = 0; i < 2; i++) {
    System.out.println("B" + i);
}
```

Output:

```text
A0
A1
B0
B1
```

Ngược lại, không thể khai báo một biến cục bộ mới **cùng tên `i` ngay trong thân vòng lặp** khi `i` của phần khởi tạo còn đang trong phạm vi:

```java
// Ví dụ cố ý sai:
// for (var i = 0; i < 2; i++) {
//     var i = 10; // Lỗi: khai báo trùng tên biến cục bộ còn trong phạm vi
// }
```

Cần phân biệt **phạm vi của tên biến** với **mỗi lượt lặp**: giá trị `i` được cập nhật qua các lượt; khai báo ở `ForInit` không tự chạy lại từng lượt.

## 5. Các quy tắc quan trọng và lỗi biên dịch thường gặp

### 5.1. Bắt buộc có biểu thức khởi tạo

`var` cần biểu thức cung cấp được kiểu. Vì vậy, ví dụ này sai:

```java
// for (var i; i < 3; i++) { } // Sai: thiếu initializer
```

Cách sửa:

```java
for (var i = 0; i < 3; i++) {
    System.out.println(i);
}
```

Nếu thật sự muốn khai báo trước rồi mới khởi tạo sau, phải dùng kiểu tường minh và tuân thủ quy tắc biến được gán trước khi đọc. Tuy nhiên với biến đếm của `for`, đặt phép khởi tạo ngay trong `ForInit` thường rõ ràng nhất.

### 5.2. Không thể suy luận kiểu từ `null`

```java
// for (var value = null; value != null; ) { } // Sai: null không cung cấp kiểu
```

Nếu cần một tham chiếu có thể bắt đầu bằng `null`, hãy khai báo kiểu tường minh:

```java
for (String value = null; value != null; ) {
    // Ví dụ minh họa về cú pháp: vòng này không chạy vì điều kiện false
}
```

Đoạn trên hợp lệ về cú pháp, nhưng không hữu ích cho việc lặp; trong mã thực tế hãy chọn giá trị khởi tạo, điều kiện và cập nhật phù hợp.

### 5.3. Một khai báo `var` chỉ được có **một biến**

Không được dùng dấu phẩy để khai báo nhiều biến cục bộ cùng lúc với `var`:

```java
// for (var left = 0, right = 4; left < right; left++, right--) {
//     // Sai: khai báo var có nhiều variable declarators
// }
```

Có ba hướng hợp lệ, tùy mục đích:

**Cách 1 — Viết kiểu tường minh cho nhiều biến cùng kiểu:**

```java
for (int left = 0, right = 4; left < right; left++, right--) {
    System.out.println(left + ":" + right);
}
```

Kết quả:

```text
0:4
1:3
```

**Cách 2 — Đặt hai khai báo riêng trước vòng lặp** (nếu cần `var` cho cả hai, chấp nhận phạm vi biến rộng hơn):

```java
var left = 0;
var right = 4;
for (; left < right; left++, right--) {
    System.out.println(left + ":" + right);
}
```

**Cách 3 — Nếu chỉ cần một biến đếm, giữ đúng một khai báo `var` trong `ForInit`:**

```java
for (var index = 0; index < 4; index++) {
    System.out.println(index);
}
```

Lưu ý: Java cho phép **nhiều biểu thức cập nhật** như `left++, right--` ở `ForUpdate`. Giới hạn “một biến” ở đây áp dụng cho **một khai báo cục bộ dùng `var`**, không có nghĩa phần cập nhật chỉ được có một biểu thức.

### 5.4. Không khai báo mảng bằng array initializer trần

```java
// for (var values = {1, 2, 3}; ...; ...) { } // Sai: thiếu kiểu đích cho { ... }
```

Hãy viết biểu thức tạo mảng tường minh:

```java
for (var values = new int[] {1, 2, 3}; values.length > 0; ) {
    System.out.println(values[0]);
    break; // Dừng chủ động: ví dụ chỉ minh họa cách suy ra int[]
}
```

Kiểu suy ra cho `values` là `int[]`. Đoạn này chủ yếu minh họa cú pháp khởi tạo hợp lệ; khi chỉ muốn duyệt phần tử mảng, vòng `for-each` hoặc vòng chỉ số thường tự nhiên hơn.

### 5.5. `final var` và toán tử cập nhật

`final var` là khai báo hợp lệ về mặt kiểu, nhưng biến `final` **không thể được gán lại**. Vì vậy, một vòng lặp dùng `i++` trên biến `final` sẽ sai:

```java
// for (final var i = 0; i < 3; i++) { } // Sai: i++ thay đổi biến final
```

Chỉ dùng `final` khi vòng lặp không cần thay đổi biến đó; với biến đếm thông thường, hãy dùng `var i = 0`.

### 5.6. Đừng nhầm với `for-each`

Hai dạng này đều có thể dùng `var` nhưng **khác cơ chế**:

```java
var names = java.util.List.of("An", "Binh");

// Basic for: var index ở ForInit; điều kiện và cập nhật dùng index.
for (var index = 0; index < names.size(); index++) {
    System.out.println(names.get(index));
}

// Enhanced for (for-each): var name là biến phần tử, không có ForInit/ForUpdate.
for (var name : names) {
    System.out.println(name);
}
```

Ở `basic for`, `index` được suy ra là `int` từ `0`. Ở `for-each`, `name` được suy ra là `String` từ kiểu phần tử của `List<String>`. Chủ đề bài này là **`var` trong phần khởi tạo của `basic for`**.

## 6. Chương trình Java 17+ hoàn chỉnh

Lưu chương trình dưới đây vào file **`ForVarDemo.java`**.

```java
public class ForVarDemo {
    public static void main(String[] args) {
        int sum = 0;

        // index có kiểu int, khai báo một lần trước vòng lặp.
        for (var index = 0; index < 4; index++) {
            sum += index;
            System.out.println("index=" + index);
        }
        System.out.println("sum=" + sum);

        var names = java.util.List.of("An", "Binh");

        // Biến index của vòng trước đã hết phạm vi: có thể dùng lại tên.
        for (var index = 0; index < names.size(); index++) {
            System.out.println(index + ": " + names.get(index));
        }

        // Có thể dùng kiểu khác; 2L khiến step được suy ra là long.
        for (var step = 2L; step <= 6L; step += 2L) {
            System.out.println("step=" + step);
        }
    }
}
```

Biên dịch và chạy trên JDK 17 hoặc mới hơn:

```bash
javac -encoding UTF-8 ForVarDemo.java
java ForVarDemo
```

Kết quả chuẩn:

```text
index=0
index=1
index=2
index=3
sum=6
0: An
1: Binh
step=2
step=4
step=6
```

Tại sao có kết quả đó?

1. `index` đầu tiên chạy từ `0` đến `3`; khi đạt `4` thì `index < 4` là `false`. Tổng `0 + 1 + 2 + 3` bằng `6`.
2. `names` là `List<String>`; vòng thứ hai dùng một biến đếm mới cùng tên `index` để truy cập hai phần tử.
3. `step` là `long` vì khởi tạo bằng `2L`; sau mỗi lượt tăng `2`, dừng khi vượt `6L`.

Không cần bật tùy chọn preview: cú pháp khai báo biến cục bộ bằng `var` đã là tính năng chính thức từ Java 10 và tiếp tục được hỗ trợ trong các bản Java hiện hành.

## 7. Khi nào nên chọn `var` cho biến điều khiển vòng lặp?

**Nên dùng** khi kiểu suy ra hiển nhiên, chẳng hạn `for (var i = 0; i < n; i++)` hoặc `for (var step = 0L; step < limit; step++)`. Cả hai đều giúp câu lệnh gọn và tên biến/điều kiện nổi bật. Tuy nhiên, dùng `var` không phải cách duy nhất viết mã tốt: `for (int i = 0; ...)` vẫn hoàn toàn hợp lệ và thường dễ đọc.

**Nên cân nhắc ghi kiểu tường minh** khi biểu thức khởi tạo phức tạp, khi kiểu là thông tin quan trọng để hiểu vòng lặp, hoặc khi việc suy luận tạo ra kiểu khác dự định. Ví dụ, `for (var cursor = openCursor(); ...; ...)` chỉ dễ hiểu nếu người đọc biết `openCursor()` trả về kiểu nào. Nếu kiểu giữ vai trò giải thích API, viết `Cursor cursor = openCursor()` có thể rõ hơn (đây là mã minh họa, giả định tồn tại kiểu `Cursor` và hàm `openCursor`).

Đặc biệt với biểu thức số, hãy nhớ `var i = 0` là `int` và `var i = 0L` là `long`. `var` không đọc ý định từ tên `i`, không nhận kiểu từ điều kiện, và không tự điều chỉnh kiểu qua các phép cập nhật.

## 8. Câu hỏi tự kiểm tra

**Câu 1.** Trong `for (var i = 1; i <= 3; i++)`, `i` có kiểu gì, phần khởi tạo chạy mấy lần?  
**Đáp án:** `int`, và phần khởi tạo chạy **một lần** trước vòng lặp.

**Câu 2.** Vì sao `for (var i = 0, j = 2; i < j; i++, j--)` không biên dịch?  
**Đáp án:** Một khai báo cục bộ với `var` không cho phép nhiều variable declarators. Nếu hai biến cùng kiểu, dùng `for (int i = 0, j = 2; ...; ...)`.

**Câu 3.** Sau khi thoát `for (var i = 0; i < 2; i++)`, có thể gọi `System.out.println(i)` ở lệnh kế tiếp không?  
**Đáp án:** Không. `i` chỉ nằm trong phạm vi câu lệnh `for` đó.

**Câu 4.** `for (var i = 0L; i < 3; i++)` có phải tạo biến `int` vì điều kiện so sánh với số `3` không?  
**Đáp án:** Không. `i` có kiểu `long` từ `0L`; biểu thức so sánh thực hiện chuyển đổi số phù hợp.

## 9. Ghi nhớ

- `var` ở `ForInit` cho phép **suy luận kiểu biến cục bộ từ biểu thức khởi tạo**, được hỗ trợ từ Java 10 trở đi.
- Phần khởi tạo chạy một lần; kiểu đã suy ra **cố định tại lúc biên dịch**.
- Biến được truy cập trong phần điều kiện, phần cập nhật và thân `for`; **không truy cập được ngoài vòng lặp**.
- Mỗi khai báo cục bộ bằng `var` chỉ được khai báo **một biến**, và biến **phải có initializer hợp lệ** (không phải literal `null` đứng một mình).
- Chọn `var` khi kiểu suy ra rõ ràng; dùng kiểu tường minh nếu làm ý đồ của vòng lặp dễ hiểu hơn.

## Tài liệu chính thức

- OpenJDK JEP 286 — Local-Variable Type Inference: https://openjdk.org/jeps/286
- Dev.java — Using the Var Type Identifier: https://dev.java/learn/language-basics/using-var/
- Java Language Specification (Java SE 26), `14.4 — Local Variable Declarations: https://docs.oracle.com/javase/specs/jls/se26/html/jls-14.html#jls-14.4
- Java Language Specification (Java SE 26), `14.14.1 — The Basic `for` Statement: https://docs.oracle.com/javase/specs/jls/se26/html/jls-14.html#jls-14.14.1
