# Vòng lặp lồng nhau và kiểm soát luồng bằng break, continue

## 1. Mỗi vòng lặp quản lý một tầng duyệt

Vòng lặp for-each có thể nằm trong thân một vòng lặp khác. Tình huống quen thuộc là duyệt nhiều hàng, mỗi hàng chứa nhiều giá trị:

```java
int[][] rows = {
    {1, 0, 2},
    {3, -1, 4},
    {5, 6}
};

for (int[] row : rows) {
    for (int value : row) {
        System.out.println(value);
    }
}
```

Đây là đoạn câu lệnh đặt trong một phương thức. Vòng ngoài lấy từng mảng hàng; vòng trong lấy từng số của hàng hiện tại. Khi vòng trong kết thúc bình thường, chương trình chạy phần còn lại của thân vòng ngoài, rồi mới chuyển sang hàng kế tiếp.

Java cho phép các hàng có độ dài khác nhau. Ở dữ liệu trên có ba hàng nhưng tám giá trị, nên nếu duyệt đầy đủ sẽ thực hiện thân vòng trong tám lần, không phải chín lần.

Bài này dùng các quy tắc vẫn áp dụng trong Java hiện hành. Chương trình đầy đủ chạy với Java 17 trở lên và không cần thư viện ngoài.

## 2. Bốn cách chuyển luồng cần phân biệt

Trong bối cảnh hai vòng lặp lồng nhau trực tiếp, không có `switch` chen giữa:

| Câu lệnh nằm trong vòng trong | Tác dụng |
| --- | --- |
| `continue;` | Bỏ phần còn lại của lượt vòng trong hiện tại, chuyển sang phần tử tiếp theo của chính vòng trong |
| `break;` | Kết thúc vòng trong, rồi chạy phần sau vòng trong trong thân vòng ngoài |
| `continue outer;` | Bỏ phần còn lại của lượt vòng ngoài hiện tại, chuyển sang lượt vòng ngoài kế tiếp |
| `break outer;` | Kết thúc toàn bộ vòng ngoài được gắn nhãn `outer`, rồi chạy câu lệnh sau vòng ngoài |

Nhãn được khai báo bằng một tên và dấu hai chấm đặt trước vòng lặp:

Chẳng hạn, viết `search:` ngay trước câu lệnh `for` muốn dùng làm đích của `break search`. Các ví dụ dưới đây dùng nhãn với vòng for-each cụ thể. Nhãn không phải annotation và cũng không tạo một hàm riêng.

## 3. continue không có nhãn: bỏ một phần tử của vòng gần nhất

Giả sử giá trị `0` chỉ là dữ liệu cần bỏ qua, còn các giá trị khác trong cùng hàng vẫn được xử lý:

```java
int total = 0;
for (int[] row : rows) {
    for (int value : row) {
        if (value == 0) {
            continue;
        }
        total += value;
    }
}
```

Ở hàng `{1, 0, 2}`, sau khi gặp `0`, câu lệnh `total += value` bị bỏ qua cho đúng lượt đó. Vòng trong vẫn lấy `2`; vòng ngoài không chuyển ngay sang hàng kế tiếp.

`continue` không có nghĩa là làm lại phần tử hiện tại. Trong for-each trên mảng, vòng lặp chuyển tới vị trí kế tiếp; với `Iterable`, cơ chế duyệt tiếp tục lấy phần tử tiếp theo qua iterator.

Cần đặt `continue` trước công việc muốn bỏ qua. Các tác động đã xảy ra trước câu lệnh, chẳng hạn cộng vào tổng hoặc ghi log, không được tự hoàn tác.

## 4. break không có nhãn: dừng vòng trong, không dừng toàn bộ việc duyệt

Giả sử mỗi hàng chỉ được xử lý đến trước số âm đầu tiên:

```java
int total = 0;
int completedRows = 0;
for (int[] row : rows) {
    for (int value : row) {
        if (value < 0) {
            break;
        }
        total += value;
    }
    completedRows++;
}
```

Ở hàng `{3, -1, 4}`, `3` được cộng, gặp `-1` thì thoát vòng trong và không đọc `4` trong lần duyệt hàng ấy. Sau đó `completedRows++` vẫn chạy, rồi vòng ngoài tiếp tục hàng `{5, 6}`.

`break` trong đoạn này chỉ kết thúc vòng gần nhất bao quanh nó. Nó không ngầm mang nghĩa “thoát tất cả vòng lặp” hoặc “hủy toàn bộ dữ liệu hàng”.

Tên `completedRows` trong ví dụ đếm số lượt đã đi tới phần cuối thân vòng ngoài, không có nghĩa mọi giá trị trong các hàng đều đã được xử lý đầy đủ. Khi đặt tên biến và thiết kế thống kê, cần phân biệt hai ý nghĩa ấy.

## 5. break có nhãn: dừng tìm kiếm trên toàn bộ cấu trúc

Khi đã tìm thấy một giá trị và không cần duyệt thêm hàng nào, dùng nhãn cho vòng ngoài:

```java
boolean found = false;
search:
for (int[] row : rows) {
    for (int value : row) {
        if (value == 4) {
            found = true;
            break search;
        }
    }
}
System.out.println(found);
```

`break search` kết thúc câu lệnh vòng ngoài mang nhãn `search`. Mọi phần còn lại của hai vòng bị bỏ qua và chương trình chạy `System.out.println(found)` sau vòng ngoài.

Nếu thay bằng `break;`, chỉ vòng trong kết thúc. Vòng ngoài vẫn có thể tiếp tục các hàng sau, làm công việc thừa hoặc thay đổi kết quả nếu các câu lệnh khác còn cập nhật trạng thái.

Nhãn phải chỉ tới một câu lệnh bao quanh vị trí `break`, nằm trong phạm vi hợp lệ. Nó không phải điểm đến tùy ý ở nơi khác trong chương trình. Đặt tên như `search`, `rowsLoop` hoặc `batches` giúp mô tả phần công việc bị dừng rõ hơn tên chung chung như `label1`.

## 6. continue có nhãn: loại cả lượt vòng ngoài

Giả sử quy tắc nghiệp vụ là **hễ có số âm thì không chấp nhận cả hàng**. Khi ấy cần bỏ không chỉ các phần tử còn lại mà còn phần ghi nhận kết quả của hàng:

```java
int acceptedRows = 0;
int acceptedTotal = 0;
rowsLoop:
for (int[] row : rows) {
    int rowTotal = 0;
    for (int value : row) {
        if (value < 0) {
            continue rowsLoop;
        }
        rowTotal += value;
    }
    acceptedRows++;
    acceptedTotal += rowTotal;
}
```

Ở hàng `{3, -1, 4}`, `3` mới được cộng vào biến tạm `rowTotal`. Gặp `-1`, `continue rowsLoop` chuyển thẳng sang hàng kế tiếp. Cả `acceptedRows++` lẫn `acceptedTotal += rowTotal` bị bỏ qua.

Nhờ chỉ cập nhật tổng chung sau khi kiểm tra xong một hàng, hàng bị loại không để lại tổng một phần. Nếu cộng trực tiếp `acceptedTotal += value` ngay trong vòng trong, giá trị `3` đã cộng trước khi gặp số âm sẽ **không tự bị trừ lại**. `continue` không phải một giao dịch có cơ chế hoàn tác.

`rowTotal` được khởi tạo lại bằng `0` ở mỗi lượt vòng ngoài. Nếu đưa biến này ra ngoài và quên đặt lại, dữ liệu của các hàng sẽ lẫn nhau dù câu lệnh nhãn đúng cú pháp.

## 7. Chương trình chạy đầy đủ để so sánh

Lưu thành **`NestedLoopControlDemo.java`**:

```java
public class NestedLoopControlDemo {
    public static void main(String[] args) {
        int[][] rows = {
            {1, 0, 2},
            {3, -1, 4},
            {5, 6}
        };

        int ordinaryCount = 0;
        int ordinaryTotal = 0;
        for (int[] row : rows) {
            for (int value : row) {
                if (value == 0) {
                    continue;
                }
                if (value < 0) {
                    break;
                }
                ordinaryCount++;
                ordinaryTotal += value;
            }
        }
        System.out.println("ordinary count=" + ordinaryCount
                + ", total=" + ordinaryTotal);

        boolean found = false;
        int visited = 0;
        search:
        for (int[] row : rows) {
            for (int value : row) {
                visited++;
                if (value == 4) {
                    found = true;
                    break search;
                }
            }
        }
        System.out.println("found=" + found + ", visited=" + visited);

        int acceptedRows = 0;
        int acceptedTotal = 0;
        rowsLoop:
        for (int[] row : rows) {
            int rowTotal = 0;
            for (int value : row) {
                if (value < 0) {
                    continue rowsLoop;
                }
                rowTotal += value;
            }
            acceptedRows++;
            acceptedTotal += rowTotal;
        }
        System.out.println("accepted rows=" + acceptedRows
                + ", total=" + acceptedTotal);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all NestedLoopControlDemo.java
java NestedLoopControlDemo
```

Stdout chính xác:

```text
ordinary count=5, total=17
found=true, visited=6
accepted rows=2, total=14
```

Ba kết quả ứng với ba hợp đồng khác nhau:

| Phần chương trình | Các giá trị được dùng | Kết quả |
| --- | --- | --- |
| Bỏ `0`, dừng mỗi hàng trước số âm | `1, 2, 3, 5, 6` | Có 5 giá trị, tổng 17 |
| Tìm `4`, dừng toàn bộ khi thấy | Đã thăm `1, 0, 2, 3, -1, 4` | Thăm 6 giá trị, chưa duyệt hàng cuối |
| Chỉ ghi nhận các hàng không có số âm | Hàng `{1, 0, 2}` và `{5, 6}` | Chấp nhận 2 hàng, tổng 14 |

Các bộ đếm được đặt trước hoặc sau câu lệnh chuyển luồng theo đúng ý nghĩa cần đo. Chẳng hạn, `visited++` đứng trước kiểm tra để tính cả phần tử mục tiêu vừa được tìm thấy.

## 8. Các quy tắc phạm vi của nhãn

### continue có nhãn phải nhắm tới vòng lặp

Nhãn cho `continue` phải thuộc một vòng lặp bao quanh, như `for`, `while` hoặc `do`. Không thể gắn nhãn vào một block thường rồi dùng `continue` tới block ấy.

Ngược lại, `break` có nhãn có thể kết thúc một câu lệnh được gắn nhãn bao quanh, bao gồm block. Trong bài này các nhãn đều gắn với vòng lặp để mục tiêu chuyển luồng rõ ràng.

### break và continue không vượt qua ranh giới phương thức hoặc lambda

Một vòng for-each có thể trực tiếp dùng `break` và `continue` theo các quy tắc trên. Nhưng lời gọi `collection.forEach(item -> ...)` là một phương thức nhận lambda, không phải câu lệnh enhanced `for`.

Không viết `break outer` bên trong lambda để thoát một vòng `outer` bên ngoài lambda. `return` trong lambda cũng chỉ kết thúc lần gọi thân lambda đó, không đồng nghĩa với `break` vòng for-each bên ngoài.

Nếu bài toán cần dừng hoặc bỏ lượt bằng các câu lệnh này, một vòng `for (Element element : collection)` trực tiếp thường thể hiện ý định dễ hơn việc chuyển sang `forEach` rồi cố mô phỏng chuyển luồng.

### Có switch bên trong thì phải xác định đúng mục tiêu

`break` không nhãn kết thúc vòng lặp hoặc câu lệnh `switch` gần nhất phù hợp. Nếu đặt nó trong một `switch` nằm trong vòng trong, nó có thể chỉ thoát `switch`. `continue` nhắm tới vòng lặp, không nhắm tới `switch`.

Khi đọc mã thực tế, xác định các cấu trúc bao quanh câu lệnh thay vì chỉ đếm dấu ngoặc nhọn.

## 9. Giới hạn dữ liệu và tác động đã xảy ra

### Hàng rỗng, hàng null và phạm vi biến

Một hàng rỗng không có lượt vòng trong nào. Phần sau vòng trong vẫn chạy khi không có chuyển luồng khác. Trong thuật toán chấp nhận hàng không có số âm, điều này nghĩa là một hàng rỗng được chấp nhận với tổng `0`; nếu nghiệp vụ không cho hàng rỗng, cần kiểm tra riêng.

Một phần tử hàng `null` khác với hàng rỗng. `for (int value : row)` với `row == null` gây `NullPointerException`. Hãy chọn rõ việc từ chối hay bỏ qua hàng null; không tự coi nó là hàng không có giá trị.

Biến `row` và `value` chỉ tồn tại trong phạm vi vòng tương ứng. Nếu cần trả ra tọa độ tìm thấy, phải lưu thông tin trước khi `break` hoặc dùng một cách duyệt có chỉ số phù hợp. For-each không tự cung cấp chỉ số hàng/cột.

### Không nhầm bỏ lượt với xóa dữ liệu

`continue` chỉ bỏ một phần xử lý; nó không xóa phần tử khỏi mảng hoặc collection. `break` chỉ dừng duyệt; nó không hủy đối tượng dữ liệu.

Khi duyệt collection bằng for-each, các câu lệnh này không tự tạo cơ chế sửa cấu trúc an toàn. Nếu cần xóa phần tử, dùng API hoặc iterator phù hợp với yêu cầu, thay vì cho rằng thêm `continue` sau một lệnh sửa trực tiếp sẽ bảo vệ vòng duyệt.

### Khối finally vẫn cần được tính vào luồng

Nếu đường đi của `break` hoặc `continue` thoát khỏi một khối `try` có `finally`, phần `finally` tương ứng vẫn được thực hiện trước khi đến đích của lệnh chuyển luồng, nếu chính `finally` không ném ngoại lệ hoặc tạo chuyển luồng khác. Vì vậy, “bỏ phần còn lại” không có nghĩa bỏ qua mọi mã dọn dẹp.

Không đặt các lệnh chuyển luồng tùy tiện trong `finally` để che lấp một chuyển luồng hoặc ngoại lệ trước đó. Với ví dụ không có `try/finally` trong bài, có thể đọc luồng theo bảng đơn giản ở đầu bài.

## 10. Khi nào nên tách phương thức thay cho nhiều nhãn?

Một nhãn có ý nghĩa rõ có thể giúp dừng tìm kiếm qua hai tầng. Nếu nhiều nhãn và cờ trạng thái xuất hiện đan xen, tách một thao tác nhỏ thành phương thức thường dễ kiểm tra hơn.

Ví dụ, khi câu hỏi duy nhất là “cấu trúc có chứa giá trị này không?”, có thể dùng `return` trong một phương thức riêng:

```java
static boolean contains(int[][] rows, int target) {
    for (int[] row : rows) {
        for (int value : row) {
            if (value == target) {
                return true;
            }
        }
    }
    return false;
}
```

Đây là phương thức minh họa đặt trong một lớp và giả định cấu trúc cùng các hàng khác `null`. `return true` kết thúc toàn bộ phương thức, còn `break search` chỉ kết thúc vòng được gắn nhãn và vẫn cho chạy mã phía sau nó trong cùng phương thức. Chọn cách nào tùy phần công việc còn cần thực hiện.

Về khối lượng duyệt, cấu trúc nhiều hàng có số lượt tối đa bằng tổng độ dài các hàng nếu duyệt hết. Một vòng trong duyệt toàn bộ một tập độc lập cho mỗi phần tử vòng ngoài lại có thể tạo số lượt bằng tích hai kích thước. `break` có thể dừng sớm, nhưng không mặc nhiên làm trường hợp xấu nhất của mọi vòng lồng nhau trở nên tuyến tính.

## 11. Tự thực hành

1. Đổi mục tiêu tìm kiếm trong chương trình thành `99`. Kết quả cần là `found=false`, `visited=8` vì không có chuyển luồng dừng sớm.
2. Đổi `break search` thành `break`. Theo dõi việc vòng ngoài vẫn tiếp tục và số phần tử được thăm thay đổi như thế nào.
3. Thêm một hàng rỗng và quyết định nó có được tính là hàng chấp nhận hay không. Cập nhật thuật toán theo quy tắc đã chọn.
4. Cố ý cộng vào tổng chung trước khi kiểm tra xong cả hàng trong phần `rowsLoop`. Chỉ ra vì sao hàng có `-1` có thể để lại tổng một phần, rồi khôi phục cách dùng biến tạm.
5. Thêm câu lệnh sau vòng trong trong thân vòng ngoài và kiểm tra trường hợp nào câu lệnh ấy chạy: `break`, `continue`, `break outer` hay `continue outer`.

Khi gặp một lệnh chuyển luồng trong vòng lồng nhau, hãy xác định mục tiêu của nó trước, rồi đánh dấu phần mã nào bị bỏ qua và phần nào vẫn chạy. Kết hợp cách đọc đó với vị trí cập nhật trạng thái sẽ giúp dự đoán chính xác kết quả và tránh ghi nhận dữ liệu dở dang.

## Tài liệu đối chiếu

- [JLS §14.14.2 — The enhanced for statement](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.14.2): cơ chế duyệt for-each.
- [JLS §14.15 — The break Statement](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.15): mục tiêu và tác dụng của break.
- [JLS §14.16 — The continue Statement](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.16): bỏ lượt theo vòng lặp mục tiêu.
- [JLS §14.7 — Labeled Statements](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.7): phạm vi và cách dùng nhãn.
