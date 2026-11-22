# Lặp lồng nhau và theo dõi từng biến đếm — Java 17+

## 1. Mục tiêu: hiểu rõ vòng ngoài và vòng trong

**Vòng lặp lồng nhau** (*nested loops*) là một vòng lặp nằm trong thân vòng lặp khác. Mỗi lần vòng ngoài đi qua một lượt, vòng trong được bắt đầu lại từ phần khởi tạo của nó.

~~~java
for (int i = 0; i < 2; i++) {
    for (int j = 0; j < 3; j++) {
        System.out.println("i=" + i + ",j=" + j);
    }
}
~~~

**Exact expected stdout:**

~~~text
i=0,j=0
i=0,j=1
i=0,j=2
i=1,j=0
i=1,j=1
i=1,j=2
~~~

Ở đây:

- `i` là **biến đếm vòng ngoài**: chạy qua 0 và 1.
- `j` là **biến đếm vòng trong**: chạy qua 0, 1, 2 **ở từng giá trị i**.
- Tổng lượt của thân trong là **2 × 3 = 6**, vì hai số lượt là độc lập.
- Sau khi vòng trong hoàn thành, vòng ngoài mới cập nhật `i`.

Mục tiêu bài học: theo dõi `i` và `j` từng bước, biết khi nào vòng trong khởi tạo lại, phân biệt các dạng lặp hình chữ nhật/tam giác, duyệt mảng hai chiều và kiểm soát `break`/`continue`.

## 2. Thứ tự thực thi từng bước

Với `for` cơ bản, thứ tự là **khởi tạo → kiểm tra điều kiện → thân → cập nhật → kiểm tra lại**.

Khi có hai vòng:

~~~text
Khởi tạo i = 0
  Kiểm tra i < 2
    Khởi tạo j = 0
      Kiểm tra j < 3 → thân(i,j) → j++
      Kiểm tra j < 3 → thân(i,j) → j++
      Kiểm tra j < 3 → thân(i,j) → j++
      Kiểm tra j < 3 → false: ra vòng trong
    Tiếp tục phần thân vòng ngoài nếu còn câu lệnh
  Cập nhật i++
  Kiểm tra i < 2 → khởi tạo j = 0 cho lượt ngoài kế tiếp
  ...
~~~

~~~mermaid
flowchart TD
    A["Khởi tạo i"] --> B{"Điều kiện vòng ngoài?"}
    B -- "Sai" --> H["Kết thúc"]
    B -- "Đúng" --> C["Khởi tạo j lại từ đầu"]
    C --> D{"Điều kiện vòng trong?"}
    D -- "Đúng" --> E["Xử lý cặp i,j"]
    E --> F["Cập nhật j"]
    F --> D
    D -- "Sai" --> G["Cập nhật i"]
    G --> B
~~~

**Chú ý:** vòng trong không chỉ “tiếp tục `j` từ lượt vòng ngoài trước”. Nếu `j` khai báo trong `for` trong, `int j = 0` chạy **lại mỗi lần** vòng ngoài tiến tới câu lệnh `for` đó.

## 3. Bảng truy vết `i` và `j`

Với `i = 0..1`, `j = 0..2`:

| Lượt thân trong | `i` | `j` | Diễn giải |
|---:|---:|---:|---|
| 1 | 0 | 0 | Lượt đầu của vòng ngoài đầu |
| 2 | 0 | 1 | Vòng trong cập nhật j |
| 3 | 0 | 2 | Lượt cuối của vòng trong |
| — | 0 | 3 | Điều kiện `j < 3` sai, không chạy body |
| 4 | 1 | 0 | Vòng ngoài tăng i, **j được khởi tạo lại** |
| 5 | 1 | 1 | Vòng trong tiếp tục |
| 6 | 1 | 2 | Lượt cuối |
| — | 1 | 3 | Vòng trong dừng; sau đó i tăng lên 2 |
| — | 2 | — | Điều kiện `i < 2` sai, vòng ngoài dừng |

Các hàng dấu **—** là bước kiểm tra, **không phải lượt thực thi body**.

Một phương pháp tự truy vết hữu ích: lập bảng gồm `i`, `j`, điều kiện vòng ngoài, điều kiện vòng trong và hành động, rồi **ghi riêng các lần kiểm tra trả false**. Cách này giúp phát hiện lỗi thiếu một lượt (*off-by-one*) hoặc hiểu nhầm lúc cập nhật.

## 4. Hình chữ nhật và tam giác: số lượt không phải lúc nào cũng nhân đơn giản

**Hình chữ nhật:** cận vòng trong độc lập với `i`.

~~~java
int count = 0;
for (int i = 0; i < 2; i++) {
    for (int j = 0; j < 3; j++) {
        count++;
    }
}
System.out.println(count); // 6
~~~

**Tam giác:** cận vòng trong **phụ thuộc `i`**.

~~~java
int count = 0;
for (int i = 1; i <= 3; i++) {
    for (int j = 1; j <= i; j++) {
        System.out.println(i + "," + j);
        count++;
    }
}
System.out.println("count=" + count);
~~~

**Exact expected stdout:**

~~~text
1,1
2,1
2,2
3,1
3,2
3,3
count=6
~~~

| `i` | Các `j` thực thi | Lượt vòng trong |
|---:|---|---:|
| 1 | 1 | 1 |
| 2 | 1, 2 | 2 |
| 3 | 1, 2, 3 | 3 |
| **Tổng** | | **1 + 2 + 3 = 6** |

Nếu `i` chạy từ 1 đến `n` và vòng trong `j = 1..i`, số lượt là \(\frac{n(n+1)}2\), không phải `n * n`. Khi `n` đủ lớn, vẫn thuộc bậc `O(n²)`.

## 5. Biến đếm vòng ngoài có giữ nguyên khi vòng trong chạy không?

Với cách viết thông thường, **chính thân trong không tăng `i`**, nên `i` giữ nguyên suốt một lần hoàn chỉnh của vòng trong:

~~~java
for (int i = 0; i < 2; i++) {
    System.out.println("start i=" + i);
    for (int j = 0; j < 2; j++) {
        System.out.println("  j=" + j);
    }
    System.out.println("end i=" + i);
}
~~~

**Exact expected stdout:**

~~~text
start i=0
  j=0
  j=1
end i=0
start i=1
  j=0
  j=1
end i=1
~~~

Tuy nhiên, Java **không tự cấm** thân trong sửa `i`. Nếu viết `i++` trong vòng trong, hoặc một hàm làm đổi trạng thái liên quan, số lượt vòng ngoài có thể thay đổi và code khó theo dõi. Quy tắc thực hành: để `i` do **vòng ngoài** quản lý, `j` do **vòng trong** quản lý, trừ khi thuật toán thật sự cần cách khác.

## 6. Phạm vi biến và cách đặt tên

~~~java
for (int i = 0; i < 2; i++) {
    for (int j = 0; j < 3; j++) {
        System.out.println(i + j); // i và j đều thuộc phạm vi.
    }
    // j không còn trong phạm vi ở đây.
}
// i cũng không còn trong phạm vi ở đây.
~~~

Biến khai báo ở phần khởi tạo của `for` chỉ tồn tại trong phạm vi phù hợp với `for` đó. **Vòng trong thấy `i`**, nhưng mã ở ngoài vòng trong không thấy `j` nếu `j` khai báo ngay trong initializer của vòng trong.

Đừng khai báo thêm một biến cục bộ cùng tên `i` ở vòng trong khi `i` của vòng ngoài vẫn trong phạm vi:

~~~java
// Không biên dịch do trùng tên biến cục bộ trong phạm vi lồng nhau:
// for (int i = 0; i < 2; i++) {
//     for (int i = 0; i < 3; i++) { }
// }
~~~

Tên `row`/`column`, `outer`/`inner` hoặc `studentIndex`/`subjectIndex` thường rõ hơn `i`/`j` trong code nghiệp vụ.

## 7. Duyệt mảng hai chiều: dùng đúng độ dài từng hàng

Mảng 2 chiều trong Java là **mảng các mảng**, nên mỗi hàng có thể có độ dài khác nhau (*jagged array*):

~~~java
int[][] matrix = {
    {1, 2},
    {3, 4, 5}
};

int sum = 0;
for (int row = 0; row < matrix.length; row++) {
    for (int col = 0; col < matrix[row].length; col++) {
        System.out.println(row + "," + col + "=" + matrix[row][col]);
        sum += matrix[row][col];
    }
}
System.out.println("sum=" + sum);
~~~

**Exact expected stdout:**

~~~text
0,0=1
0,1=2
1,0=3
1,1=4
1,2=5
sum=15
~~~

**Không dùng** `matrix[0].length` làm cận cột chung khi các hàng có thể không đều:

~~~java
// Dễ sai với mảng không chữ nhật:
// for (int col = 0; col < matrix[0].length; col++) { ... }
~~~

Hãy kiểm tra `row < matrix.length` và `col < matrix[row].length`. Nếu một hàng có thể là `null` trong dữ liệu thực tế, phải kiểm tra null trước khi gọi `.length`.

## 8. `break` và `continue` không nhãn trong vòng lặp lồng nhau

Không có nhãn, `break;` kết thúc **vòng lặp gần nhất**; `continue;` bỏ phần body còn lại của **vòng lặp gần nhất** và chuyển sang bước cập nhật/điều kiện lượt tiếp theo.

**Continue vòng trong:**

~~~java
for (int i = 0; i < 2; i++) {
    for (int j = 0; j < 3; j++) {
        if (j == 1) continue;
        System.out.println(i + "," + j);
    }
}
~~~

**Exact expected stdout:**

~~~text
0,0
0,2
1,0
1,2
~~~

Nhánh `j == 1` bị bỏ qua, nhưng **vòng trong vẫn cập nhật `j++`**, nên `j == 2` vẫn được xét.

**Break vòng trong:**

~~~java
for (int i = 1; i <= 2; i++) {
    for (int j = 1; j <= 3; j++) {
        if (j == 2) break;
        System.out.println("inner " + i + "," + j);
    }
    System.out.println("after inner " + i);
}
~~~

**Exact expected stdout:**

~~~text
inner 1,1
after inner 1
inner 2,1
after inner 2
~~~

`break` ở `j == 2` **không kết thúc vòng ngoài**; do đó vẫn có lượt `i == 2`. Đặt `break` sai mức có thể khiến chương trình chạy nhiều lượt hơn dự kiến.

## 9. `break label` và `continue label` để tác động lên vòng ngoài

Java cho phép đặt **nhãn** ngay trước vòng lặp:

~~~java
outer:
for (int i = 1; i <= 3; i++) {
    for (int j = 1; j <= 3; j++) {
        if (i == 2 && j == 2) {
            break outer; // Kết thúc cả vòng ngoài.
        }
        System.out.println("seen " + i + "," + j);
    }
}
~~~

**Exact expected stdout:**

~~~text
seen 1,1
seen 1,2
seen 1,3
seen 2,1
~~~

`break outer;` thoát cấu trúc mang nhãn `outer`, không tiếp tục các lượt `i` sau đó.

Ngược lại, `continue outer;` bỏ phần còn lại của lượt vòng **ngoài** hiện tại rồi chuyển sang bước cập nhật `i++`:

~~~java
outer:
for (int i = 1; i <= 3; i++) {
    for (int j = 1; j <= 3; j++) {
        if (j == 2) {
            System.out.println("skip row " + i);
            continue outer;
        }
        System.out.println("check " + i + "," + j);
    }
}
~~~

**Exact expected stdout:**

~~~text
check 1,1
skip row 1
check 2,1
skip row 2
check 3,1
skip row 3
~~~

**Phân biệt:**

| Lệnh ở thân vòng trong | Ảnh hưởng |
|---|---|
| `break;` | Thoát vòng trong, quay lại thân vòng ngoài sau vòng trong |
| `continue;` | Bỏ phần còn lại của lượt vòng trong, chuyển sang cập nhật `j` |
| `break outer;` | Thoát hẳn vòng ngoài có nhãn |
| `continue outer;` | Bỏ phần còn lại của lượt vòng ngoài, chuyển sang cập nhật `i` |

Sử dụng nhãn vừa đủ; với logic nhiều tầng phức tạp, tách thành method trả `boolean` hoặc kết quả rõ ràng có thể dễ bảo trì hơn.

## 10. Lỗi thường gặp khi theo dõi hai biến đếm

| Lỗi | Hệ quả | Cách sửa |
|---|---|---|
| Nghĩ `j` chỉ khởi tạo một lần cho toàn chương trình | Sai số lượt và kết quả | Nhớ `for (int j = ...)` được tới lại ở mỗi lượt ngoài |
| Dùng `j < matrix.length` thay vì độ dài hàng | Bỏ sót hoặc vượt cột | `j < matrix[i].length` |
| Dùng `i <= length` khi truy cập mảng | Off-by-one, có thể lỗi chỉ số | `i < length` |
| Tăng `i` trong update của vòng trong khi định tăng `j` | Sai tiến trình, có thể lặp vô hạn | Dùng `j++` trong vòng trong |
| Viết `j <= i` nhưng bắt đầu `j = 0` khi chỉ muốn 1..i | Có thêm một lượt `j == 0` | Đồng bộ cận và giá trị khởi tạo |
| Cho rằng `break;` bên trong thoát cả hai vòng | Vòng ngoài vẫn chạy | Dùng `break outer;` hoặc thiết kế lại |
| Cho rằng `continue;` ở vòng trong bỏ cả hàng | Chỉ bỏ một lượt `j` | `continue outer;` nếu muốn bỏ cả lượt ngoài |
| Dùng cùng tên biến cục bộ ở phạm vi lồng nhau | Lỗi compile | Chọn tên riêng `i`/`j` hoặc `row`/`col` |
| Chỉ in kết quả cuối mà không log `i,j` khi debug | Khó tìm chỗ sai | Tạm in từng cặp và bước cập nhật |
| Luôn cho rằng số lượt = `n*m` | Sai khi cận `j` phụ thuộc `i` | Tính tổng lượt theo từng `i` |
| Bỏ sót hàng mảng rỗng hoặc null | Lỗi logic hoặc NPE | Xét `matrix[row].length == 0`, kiểm tra null nếu dữ liệu cho phép |
| Dùng vòng lồng `O(n²)` khi dữ liệu rất lớn | Có thể tốn thời gian | Xem lại thuật toán/độ phức tạp thực tế |

## 11. Độ phức tạp: tính theo tổng số lượt của vòng trong

Nếu vòng ngoài có `n` lượt, vòng trong có đúng `m` lượt **ở mỗi lượt ngoài**, tổng body là `n × m`, chi phí `O(nm)` nếu mỗi body mất thời gian hằng số.

Nếu vòng ngoài `i = 1..n`, vòng trong `j = 1..i`, tổng body là:

\[
1 + 2 + \cdots + n = \frac{n(n+1)}{2}
\]

Vì vậy chi phí tăng theo `O(n²)`. Nếu vòng trong kết thúc sớm do `break`, số lượt thực tế có thể thấp hơn. Nếu thân trong gọi một thao tác tốn `O(k)` thì cần nhân thêm chi phí đó khi phân tích.

Đừng chỉ đếm **số câu lệnh `for` xuất hiện** để kết luận độ phức tạp; cận thực tế và điều kiện dừng mới là yếu tố quyết định.

## 12. Chương trình Java 17 hoàn chỉnh, chạy bằng CLI

Lưu đúng tên **`NestedLoopCountersDemo.java`**:

~~~java
public final class NestedLoopCountersDemo {
    private NestedLoopCountersDemo() {}

    static void rectangle() {
        int pairs = 0;
        for (int i = 0; i < 2; i++) {
            for (int j = 0; j < 3; j++) {
                System.out.println("pair " + i + "," + j);
                pairs++;
            }
            System.out.println("after outer " + i);
        }
        System.out.println("pairs=" + pairs);
    }

    static void triangle() {
        int count = 0;
        for (int i = 1; i <= 3; i++) {
            for (int j = 1; j <= i; j++) {
                System.out.println("triangle " + i + "," + j);
                count++;
            }
        }
        System.out.println("triangleCount=" + count);
    }

    static void jaggedArray() {
        int[][] matrix = {{1, 2}, {3, 4, 5}};
        int sum = 0;
        for (int row = 0; row < matrix.length; row++) {
            for (int col = 0; col < matrix[row].length; col++) {
                int value = matrix[row][col];
                System.out.println("cell " + row + "," + col + "=" + value);
                sum += value;
            }
        }
        System.out.println("sum=" + sum);
    }

    static void innerContinueAndBreak() {
        for (int i = 0; i < 2; i++) {
            for (int j = 0; j < 3; j++) {
                if (j == 1) continue;
                System.out.println("visit " + i + "," + j);
            }
        }
        System.out.println("finish after continue");
        for (int i = 1; i <= 2; i++) {
            for (int j = 1; j <= 3; j++) {
                if (j == 2) break;
                System.out.println("inner " + i + "," + j);
            }
            System.out.println("after inner " + i);
        }
    }

    static void labeledBreak() {
        outer:
        for (int i = 1; i <= 3; i++) {
            for (int j = 1; j <= 3; j++) {
                if (i == 2 && j == 2) {
                    System.out.println("stop at 2,2");
                    break outer;
                }
                System.out.println("seen " + i + "," + j);
            }
        }
        System.out.println("after labeled break");
    }

    static void labeledContinue() {
        outer:
        for (int i = 1; i <= 3; i++) {
            for (int j = 1; j <= 3; j++) {
                if (j == 2) {
                    System.out.println("skip row " + i);
                    continue outer;
                }
                System.out.println("check " + i + "," + j);
            }
        }
        System.out.println("after labeled continue");
    }

    public static void main(String[] args) {
        System.out.println("== rectangle ==");
        rectangle();
        System.out.println("== triangle ==");
        triangle();
        System.out.println("== jagged ==");
        jaggedArray();
        System.out.println("== continue and break ==");
        innerContinueAndBreak();
        System.out.println("== labels ==");
        labeledBreak();
        labeledContinue();
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên, terminal tại thư mục chứa file. Không dùng Maven, Gradle, preview feature hay thư viện ngoài JDK.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 NestedLoopCountersDemo.java
java -cp . NestedLoopCountersDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\NestedLoopCountersDemo.java
java -cp . NestedLoopCountersDemo
~~~

### Exact expected stdout

~~~text
== rectangle ==
pair 0,0
pair 0,1
pair 0,2
after outer 0
pair 1,0
pair 1,1
pair 1,2
after outer 1
pairs=6
== triangle ==
triangle 1,1
triangle 2,1
triangle 2,2
triangle 3,1
triangle 3,2
triangle 3,3
triangleCount=6
== jagged ==
cell 0,0=1
cell 0,1=2
cell 1,0=3
cell 1,1=4
cell 1,2=5
sum=15
== continue and break ==
visit 0,0
visit 0,2
visit 1,0
visit 1,2
finish after continue
inner 1,1
after inner 1
inner 2,1
after inner 2
== labels ==
seen 1,1
seen 1,2
seen 1,3
seen 2,1
stop at 2,2
after labeled break
check 1,1
skip row 1
check 2,1
skip row 2
check 3,1
skip row 3
after labeled continue
~~~

**Đối chiếu:**

1. `rectangle()` tạo 6 cặp `i,j`; `j` trở về 0 khi `i` chuyển từ 0 sang 1.
2. `triangle()` có số lượt 1 + 2 + 3, không đều giữa các lượt `i`.
3. `jaggedArray()` đi qua hai hàng khác độ dài, tổng 1+2+3+4+5 = 15.
4. `continue` bỏ lượt `j == 1`; `break` chỉ thoát vòng trong khi `j == 2`.
5. `break outer` làm toàn bộ vòng ngoài kết thúc ở `i=2,j=2`.
6. `continue outer` chuyển ngay sang lượt ngoài mới khi `j == 2`; `j == 3` không được xét.

## 13. Bài tập có đáp án

### Bài A — đếm số lần in

~~~java
for (int i = 0; i < 3; i++) {
    for (int j = 0; j < 2; j++) {
        System.out.println(i + ":" + j);
    }
}
~~~

**Đáp án:** 6 dòng, theo thứ tự:

~~~text
0:0
0:1
1:0
1:1
2:0
2:1
~~~

### Bài B — cận vòng trong phụ thuộc vòng ngoài

~~~java
int count = 0;
for (int i = 1; i <= 4; i++) {
    for (int j = 1; j <= i; j++) count++;
}
System.out.println(count);
~~~

**Đáp án:** `10`, do 1+2+3+4 = 10.

### Bài C — sửa duyệt mảng lệch biên

~~~java
int[][] matrix = {{5}, {6, 7}};
// Sai: dùng matrix[0].length cho tất cả các hàng.
~~~

**Đáp án:**

~~~java
for (int i = 0; i < matrix.length; i++) {
    for (int j = 0; j < matrix[i].length; j++) {
        System.out.println(matrix[i][j]);
    }
}
~~~

**Exact stdout:** ba dòng `5`, `6`, `7`.

### Bài D — `break` thoát vòng nào?

~~~java
for (int i = 0; i < 2; i++) {
    for (int j = 0; j < 3; j++) {
        if (j == 1) break;
        System.out.println(i + "," + j);
    }
}
~~~

**Đáp án:**

~~~text
0,0
1,0
~~~

`break` thoát vòng trong tại `j == 1`, nhưng vòng ngoài vẫn chuyển từ 0 sang 1.

### Bài E — dừng cả hai vòng

Muốn thoát cả hai vòng khi thấy `matrix[i][j] == target`, có thể đặt nhãn:

~~~java
search:
for (int i = 0; i < matrix.length; i++) {
    for (int j = 0; j < matrix[i].length; j++) {
        if (matrix[i][j] == target) {
            break search;
        }
    }
}
~~~

**Đáp án:** `break search` thoát vòng ngoài có nhãn và cả các vòng nằm trong nó. Trong phương thức tìm kiếm, một cách khác là `return` ngay vị trí tìm thấy.

## 14. Checklist và kết luận

- [ ] Phân biệt biến đếm vòng ngoài `i` và vòng trong `j`.
- [ ] Biết initializer của vòng trong chạy lại **mỗi lượt vòng ngoài**.
- [ ] Lập được bảng từng cặp `i,j` và bước điều kiện false.
- [ ] Phân biệt hình chữ nhật `n×m` với vòng tam giác `1+...+n`.
- [ ] Giữ việc cập nhật `i` ở vòng ngoài, `j` ở vòng trong nếu không có yêu cầu đặc biệt.
- [ ] Hiểu phạm vi biến `i`/`j` và tránh khai báo trùng tên.
- [ ] Duyệt mảng 2D bằng `matrix.length` và `matrix[row].length`.
- [ ] Hiểu `break;`/`continue;` không nhãn chỉ tác động lên vòng gần nhất.
- [ ] Phân biệt `break outer;` và `continue outer;`.
- [ ] Biết tính số lượt/độ phức tạp dựa trên cận thực tế của vòng trong.
- [ ] Kiểm tra giá trị tại biên, hàng rỗng và điều kiện dừng.
- [ ] Chạy `NestedLoopCountersDemo.java` với JDK 17+, so sánh exact stdout.

**Kết luận:** Để hiểu vòng lặp lồng nhau, hãy luôn truy vết theo **từng cặp giá trị `i,j`**: giữ `i` ở một lượt ngoài, cho `j` chạy tới khi dừng, rồi cập nhật `i` và khởi tạo lại `j`. Khi cận vòng trong phụ thuộc `i`, số lượt là một **tổng theo từng vòng ngoài**, không còn đơn thuần là tích. Biết rõ mức tác động của `break`/`continue` sẽ giúp tránh lỗi luồng điều khiển.