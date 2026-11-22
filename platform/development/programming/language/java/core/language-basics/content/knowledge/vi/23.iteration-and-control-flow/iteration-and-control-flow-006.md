# `break` và `continue` có nhãn trong vòng lặp lồng — Java 17+

## 1. Mục tiêu và quy tắc chính

Khi có nhiều vòng lặp lồng nhau, `break;` và `continue;` **không nhãn** mặc định tác động lên **vòng lặp gần nhất** bao quanh câu lệnh:

- `break;`: kết thúc vòng lặp gần nhất, rồi tiếp tục sau vòng đó.
- `continue;`: bỏ các câu lệnh còn lại trong **lượt hiện tại** của vòng lặp gần nhất, chuyển sang bước cập nhật/kiểm tra để đi tới lượt tiếp theo.

Java cho phép đặt **nhãn** cho một vòng lặp, rồi chỉ định đích:

~~~java
outer:
for (int i = 0; i < 3; i++) {
    for (int j = 0; j < 3; j++) {
        if (i == 1 && j == 1) {
            break outer; // Kết thúc toàn bộ vòng for mang nhãn outer.
        }
        System.out.println(i + "," + j);
    }
}
System.out.println("done");
~~~

**Exact expected stdout:**

~~~text
0,0
0,1
0,2
1,0
done
~~~

Nhãn `outer` là tên do lập trình viên đặt, **không phải** một biến, không phải `goto`, và không tạo một vòng lặp mới. Trong bài, ta sẽ phân biệt rõ `break outer;` với `continue outer;` và theo dõi trạng thái các biến đếm khi chuyển luồng.

## 2. Cú pháp nhãn và hai lệnh chuyển luồng

~~~java
myLoop:
for (int i = 0; i < 10; i++) {
    // ...
}
~~~

Dạng đầy đủ:

- `labelName:` đứng **ngay trước câu lệnh** được gắn nhãn.
- `break labelName;` chuyển điều khiển ra **sau câu lệnh có nhãn**.
- `continue labelName;` chuyển tới **lượt tiếp theo của vòng lặp có nhãn**, nếu nhãn đó chỉ một vòng lặp đang bao quanh vị trí `continue`.

Tên nhãn phải là định danh Java hợp lệ (ví dụ `outer`, `search`, `nextRow`). Nhãn có phạm vi trong câu lệnh mà nó gắn vào; không thể nhảy sang một vòng lặp nằm trong phương thức khác.

**Điểm khác biệt của Java:** `break label;` có thể thoát một **câu lệnh có nhãn** phù hợp, kể cả block, nhưng `continue label;` **bắt buộc** nhãn phải thuộc một **vòng lặp** (`for`, `while`, `do-while`). Bài này sử dụng nhãn gắn với vòng lặp.

## 3. Không nhãn: chỉ tác động vòng trong

~~~java
for (int i = 1; i <= 2; i++) {
    for (int j = 1; j <= 3; j++) {
        if (j == 2) break;
        System.out.println("pair " + i + "," + j);
    }
    System.out.println("after inner " + i);
}
~~~

**Exact expected stdout:**

~~~text
pair 1,1
after inner 1
pair 2,1
after inner 2
~~~

Khi `j == 2`, `break;` thoát **vòng `j`**. Vòng `i` vẫn chạy câu lệnh `after inner` và tiếp tục lượt `i` tiếp theo.

Thử thay `break;` bằng `continue;`:

~~~java
for (int i = 1; i <= 2; i++) {
    for (int j = 1; j <= 3; j++) {
        if (j == 2) continue;
        System.out.println("keep " + i + "," + j);
    }
}
~~~

**Exact expected stdout:**

~~~text
keep 1,1
keep 1,3
keep 2,1
keep 2,3
~~~

`continue;` chỉ bỏ lượt `j == 2`, sau đó vòng `j` vẫn thực hiện **`j++`** rồi kiểm tra `j <= 3`. Vì vậy `j == 3` vẫn được duyệt ở cả hai lượt vòng ngoài.

## 4. `break outer`: rời tất cả vòng bên trong đích

~~~java
outer:
for (int i = 0; i < 3; i++) {
    for (int j = 0; j < 4; j++) {
        if (i == 1 && j == 2) {
            System.out.println("found " + i + "," + j);
            break outer;
        }
        System.out.println("scan " + i + "," + j);
    }
}
System.out.println("after search");
~~~

**Exact expected stdout:**

~~~text
scan 0,0
scan 0,1
scan 0,2
scan 0,3
scan 1,0
scan 1,1
found 1,2
after search
~~~

- Chương trình gặp đích tại `i=1, j=2` thì thoát **vòng ngoài có nhãn `outer`**.
- Các câu lệnh và lượt còn lại của hai vòng đều bị bỏ.
- Phần **update `j++` và `i++` ở lượt bị ngắt không tự chạy**.
- Thực thi tiếp tục sau toàn bộ vòng ngoài, tại `after search`.

Nhãn không cần trùng tên biến đếm; nên chọn tên diễn đạt ý nghĩa như `search` hoặc `outer`.

## 5. `continue outer`: bỏ phần còn lại của lượt vòng ngoài

~~~java
nextRow:
for (int row = 0; row < 3; row++) {
    System.out.println("row " + row);

    for (int col = 0; col < 3; col++) {
        if (col == 1) {
            System.out.println("skip rest " + row);
            continue nextRow;
        }
        System.out.println("cell " + row + "," + col);
    }

    System.out.println("row done " + row);
}
System.out.println("after rows");
~~~

**Exact expected stdout:**

~~~text
row 0
cell 0,0
skip rest 0
row 1
cell 1,0
skip rest 1
row 2
cell 2,0
skip rest 2
after rows
~~~

`continue nextRow;` nghĩa là **bỏ phần còn lại của lượt `row` hiện tại**:

1. Không tiếp tục chạy những cột sau `col == 1`.
2. Không chạy câu lệnh `row done` ở cuối body vòng ngoài trong lượt đó.
3. **Vẫn thực hiện phần cập nhật của vòng `for (row)`: `row++`**, rồi xét điều kiện `row < 3`.
4. Nếu điều kiện còn true, tạo **vòng trong mới** cho giá trị `row` kế tiếp.

Do đó `continue outer` **không giống `break outer`**: nó không dừng toàn bộ vòng ngoài; nó chuyển sang lượt tiếp theo của vòng ngoài.

## 6. Bảng đối chiếu theo cấp độ chuyển luồng

Giả sử đang ở trong vòng `j` nằm trong vòng `i` mang nhãn `outer`:

| Câu lệnh | Đích | Cập nhật `j` hiện tại? | Cập nhật `i` hiện tại? | Tiếp tục ở đâu? |
|---|---|---|---|---|
| `break;` | Thoát vòng `j` | Không | Chưa; thân vòng `i` tiếp tục, cập nhật khi hết lượt | Sau vòng `j` |
| `continue;` | Lượt kế vòng `j` | **Có** (basic for) | Không tại thời điểm đó | Phần update/điều kiện vòng `j` |
| `break outer;` | Thoát vòng `i` | Không | **Không** | Sau vòng `i` |
| `continue outer;` | Lượt kế vòng `i` | Không | **Có** (basic for) | Phần update/điều kiện vòng `i` |

Các mô tả cập nhật trong bảng áp dụng cho **basic `for`** có update riêng. Với `while` hoặc `do-while`, `continue` chuyển theo quy tắc xét điều kiện của loại vòng đó; không có biểu thức update tự động như basic `for`.

~~~mermaid
flowchart TD
    A["Đang chạy body vòng trong j"] --> B{"Lệnh gặp phải"}
    B -- "break" --> C["Ra khỏi vòng j, tiếp tục body ngoài"]
    B -- "continue" --> D["Update và kiểm tra vòng j"]
    B -- "break outer" --> E["Ra khỏi vòng i mang nhãn outer"]
    B -- "continue outer" --> F["Update và kiểm tra vòng i"]
~~~

## 7. Truy vết tác động của `continue outer` lên phần update

Để nhìn rõ rằng update của vòng ngoài vẫn chạy:

~~~java
int updates = 0;

outer:
for (int i = 0; i < 3; i++, updates++) {
    for (int j = 0; j < 2; j++) {
        if (j == 0) continue outer;
    }
}

System.out.println("updates=" + updates);
~~~

**Exact expected stdout:**

~~~text
updates=3
~~~

Ở mỗi lượt ngoài, vòng trong gặp `j == 0` và `continue outer;`. Dù bỏ phần còn lại của body, cả `i++` và `updates++` trong update vòng ngoài **vẫn được chạy**. Sau ba lượt ngoài, `updates == 3`.

Trong một danh sách update có dấu phẩy, các biểu thức được thực thi từ trái sang phải. Khi chuyển luồng có thể xảy ra giữa chừng, đọc lại mã update để tránh hiểu nhầm biến nào được đổi.

## 8. Ba cấp vòng lặp: nhãn có thể thoát nhiều cấp

~~~java
stopAll:
for (int a = 0; a < 2; a++) {
    for (int b = 0; b < 2; b++) {
        for (int c = 0; c < 2; c++) {
            if (a == 1 && b == 0 && c == 1) {
                System.out.println("stop " + a + "," + b + "," + c);
                break stopAll;
            }
            System.out.println("triple " + a + "," + b + "," + c);
        }
    }
}
System.out.println("after all");
~~~

**Exact expected stdout:**

~~~text
triple 0,0,0
triple 0,0,1
triple 0,1,0
triple 0,1,1
triple 1,0,0
stop 1,0,1
after all
~~~

`break stopAll` rời cả ba cấp vì vòng ngoài nhất `a` là câu lệnh có nhãn. Nhưng không phải lúc nào dùng nhãn cũng là giải pháp dễ bảo trì: nếu nhiều vòng lặp và nhiều trường hợp dừng phức tạp, hãy cân nhắc **tách thành phương thức** để dùng `return` rõ ràng.

## 9. Nhãn và `switch` lồng trong vòng lặp

Khi trong vòng lặp có thêm một `switch`, `break;` không nhãn thoát **switch gần nhất**, còn `break outer;` có thể thoát vòng lặp mang nhãn ở bên ngoài. `continue outer;` có thể chuyển sang lượt vòng lặp kế tiếp từ bên trong switch:

~~~java
outer:
for (int i = 0; i < 3; i++) {
    switch (i) {
        case 0 -> {
            System.out.println("switch:continue");
            continue outer;
        }
        case 1 -> {
            System.out.println("switch:break");
            break outer;
        }
        default -> System.out.println("switch:other");
    }
    System.out.println("switch:post=" + i);
}
System.out.println("switch:done");
~~~

**Exact expected stdout:**

~~~text
switch:continue
switch:break
switch:done
~~~

Vì `i == 0` chuyển ngay sang cập nhật của vòng ngoài, `switch:post=0` không được in. Với `i == 1`, `break outer` dừng vòng ngoài; `switch:post=1` cũng không được in.

**Không nhầm:** `continue;` không nhãn **không** nhắm vào switch độc lập; nó cần một vòng lặp đang bao quanh. Ngược lại, `break;` trong switch statement thường kết thúc switch.

## 10. Điều kiện hợp lệ, phạm vi nhãn và những lỗi biên dịch

**Ví dụ đúng:** nhãn gắn trực tiếp với vòng lặp:

~~~java
retry:
while (true) {
    break retry;
}
~~~

**Ví dụ sai:** nhãn gắn với block không phải vòng lặp; `continue` không được nhắm tới nhãn đó:

~~~java
// outer: {
//     continue outer; // Lỗi biên dịch: nhãn không chỉ một vòng lặp.
// }
~~~

**Ví dụ đúng với block:** `break` có nhãn có thể rời một block có nhãn:

~~~java
scope: {
    System.out.println("before");
    break scope;
}
System.out.println("after");
~~~

**Exact expected stdout:**

~~~text
before
after
~~~

Các lỗi khác cần tránh:

- Viết `break nonexistent;` hoặc `continue nonexistent;` khi không có nhãn bao quanh đúng tên → lỗi biên dịch.
- Dùng nhãn ở vòng lặp **không bao quanh vị trí đang chuyển luồng** → không hợp lệ.
- Dùng `continue` nhắm vào một `switch` hoặc một block → không hợp lệ; đích phải là vòng lặp.
- Dùng lại một tên nhãn trong vùng lồng nhau gây trùng nhãn → lỗi biên dịch.
- Nghĩ nhãn là biến hay object có thể gán hoặc truyền qua method → sai; tên nhãn chỉ có ý nghĩa cú pháp điều khiển luồng.

`break`/`continue` có nhãn **không thể nhảy xuyên qua ranh giới một phương thức/lambda sang vòng lặp ở bên ngoài**. Nếu luồng phức tạp, truyền kết quả qua `return` thay vì cố “nhảy” giữa các phương thức.

## 11. So sánh `break outer`, `continue outer` và `return`

| Lệnh | Kết thúc cái gì? | Chương trình còn tiếp tục sau vòng ngoài? |
|---|---|---|
| `break outer;` | Câu lệnh vòng lặp mang nhãn | Có, sau vòng ngoài |
| `continue outer;` | **Lượt hiện tại** của vòng mang nhãn | Có thể sau các lượt tiếp theo khi vòng thật sự kết thúc |
| `return;`/`return value;` | Toàn bộ phương thức hiện tại | Không, caller tiếp tục sau lời gọi |
| `throw exception;` | Chuyển luồng bằng ngoại lệ | Phụ thuộc nơi bắt ngoại lệ |

Ví dụ cần tìm phần tử trong ma trận:

~~~java
static int[] find(int[][] matrix, int target) {
    for (int row = 0; row < matrix.length; row++) {
        for (int col = 0; col < matrix[row].length; col++) {
            if (matrix[row][col] == target) {
                return new int[]{row, col}; // Rời phương thức.
            }
        }
    }
    return new int[]{-1, -1};
}
~~~

Đây là tình huống `return` thường **dễ đọc hơn `break label`** nếu mục đích tìm thấy là kết thúc toàn bộ phương thức tìm kiếm. `break outer` phù hợp khi cần rời các vòng nhưng vẫn có xử lý chung sau vòng.

**Cẩn trọng với `finally`:** Nếu chuyển luồng ra khỏi khối `try` có `finally`, Java vẫn thực thi `finally` theo luật của ngôn ngữ trước khi hoàn tất chuyển luồng; đừng đặt side effect hoặc `return` bất ngờ trong `finally` làm khó suy luận.

## 12. Chương trình Java 17 hoàn chỉnh, chạy độc lập

Tạo file đúng tên **`LabeledLoopControlDemo.java`**:

~~~java
public final class LabeledLoopControlDemo {
    private LabeledLoopControlDemo() {}

    static void plainBreak() {
        for (int i = 1; i <= 2; i++) {
            for (int j = 1; j <= 3; j++) {
                if (j == 2) break;
                System.out.println("pair " + i + "," + j);
            }
            System.out.println("after inner " + i);
        }
    }

    static void plainContinue() {
        for (int i = 1; i <= 2; i++) {
            for (int j = 1; j <= 3; j++) {
                if (j == 2) continue;
                System.out.println("keep " + i + "," + j);
            }
        }
    }

    static void labeledBreak() {
        search:
        for (int i = 0; i < 3; i++) {
            for (int j = 0; j < 4; j++) {
                if (i == 1 && j == 2) {
                    System.out.println("found " + i + "," + j);
                    break search;
                }
                System.out.println("scan " + i + "," + j);
            }
        }
        System.out.println("after search");
    }

    static void labeledContinue() {
        nextRow:
        for (int row = 0; row < 3; row++) {
            System.out.println("row " + row);
            for (int col = 0; col < 3; col++) {
                if (col == 1) {
                    System.out.println("skip rest " + row);
                    continue nextRow;
                }
                System.out.println("cell " + row + "," + col);
            }
            System.out.println("row done " + row);
        }
        System.out.println("after rows");
    }

    static void updateAfterContinue() {
        int updates = 0;
        outer:
        for (int i = 0; i < 3; i++, updates++) {
            for (int j = 0; j < 2; j++) {
                if (j == 0) continue outer;
            }
        }
        System.out.println("updates=" + updates);
    }

    static void threeLevels() {
        stopAll:
        for (int a = 0; a < 2; a++) {
            for (int b = 0; b < 2; b++) {
                for (int c = 0; c < 2; c++) {
                    if (a == 1 && b == 0 && c == 1) {
                        System.out.println("stop " + a + "," + b + "," + c);
                        break stopAll;
                    }
                    System.out.println("triple " + a + "," + b + "," + c);
                }
            }
        }
        System.out.println("after all");
    }

    static void insideSwitch() {
        outer:
        for (int i = 0; i < 3; i++) {
            switch (i) {
                case 0 -> {
                    System.out.println("switch:continue");
                    continue outer;
                }
                case 1 -> {
                    System.out.println("switch:break");
                    break outer;
                }
                default -> System.out.println("switch:other");
            }
            System.out.println("switch:post=" + i);
        }
        System.out.println("switch:done");
    }

    public static void main(String[] args) {
        System.out.println("== break ==");
        plainBreak();
        System.out.println("== continue ==");
        plainContinue();
        System.out.println("== break label ==");
        labeledBreak();
        System.out.println("== continue label ==");
        labeledContinue();
        System.out.println("== update ==");
        updateAfterContinue();
        System.out.println("== 3 levels ==");
        threeLevels();
        System.out.println("== switch ==");
        insideSwitch();
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên; mở terminal tại thư mục chứa file. Không dùng thư viện ngoài JDK, Maven/Gradle hoặc tính năng preview.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 LabeledLoopControlDemo.java
java -cp . LabeledLoopControlDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\LabeledLoopControlDemo.java
java -cp . LabeledLoopControlDemo
~~~

### Exact expected stdout

~~~text
== break ==
pair 1,1
after inner 1
pair 2,1
after inner 2
== continue ==
keep 1,1
keep 1,3
keep 2,1
keep 2,3
== break label ==
scan 0,0
scan 0,1
scan 0,2
scan 0,3
scan 1,0
scan 1,1
found 1,2
after search
== continue label ==
row 0
cell 0,0
skip rest 0
row 1
cell 1,0
skip rest 1
row 2
cell 2,0
skip rest 2
after rows
== update ==
updates=3
== 3 levels ==
triple 0,0,0
triple 0,0,1
triple 0,1,0
triple 0,1,1
triple 1,0,0
stop 1,0,1
after all
== switch ==
switch:continue
switch:break
switch:done
~~~

**Đối chiếu:** `plainBreak` vẫn cho vòng ngoài chạy tiếp; `plainContinue` bỏ một `j`; `labeledBreak` dừng tìm kiếm sau `1,2`; `labeledContinue` bỏ phần còn lại của từng hàng; `updates=3` xác nhận update vòng ngoài vẫn chạy; `threeLevels` thoát đủ ba tầng; nhãn trong `insideSwitch` nhắm vào vòng ngoài.

## 13. Bài tập có đáp án

### A — `break` không nhãn dừng ở đâu?

~~~java
for (int i = 0; i < 2; i++) {
    for (int j = 0; j < 3; j++) {
        if (j == 1) break;
        System.out.println(i + ":" + j);
    }
}
~~~

**Đáp án:**

~~~text
0:0
1:0
~~~

Vòng `j` dừng tại `j==1` nhưng vòng `i` vẫn có lượt thứ hai.

### B — muốn thoát cả hai vòng

~~~java
outer:
for (int i = 0; i < 2; i++) {
    for (int j = 0; j < 3; j++) {
        if (i == 0 && j == 1) break outer;
        System.out.println(i + "," + j);
    }
}
~~~

**Expected stdout:**

~~~text
0,0
~~~

Dừng toàn bộ vòng `outer` khi tới cặp `0,1`.

### C — muốn bỏ phần còn lại của một hàng

~~~java
nextRow:
for (int i = 0; i < 2; i++) {
    for (int j = 0; j < 3; j++) {
        if (j == 1) continue nextRow;
        System.out.println(i + "," + j);
    }
}
~~~

**Expected stdout:**

~~~text
0,0
1,0
~~~

`continue nextRow` bỏ các cột còn lại của hàng hiện tại, sau đó đi sang hàng sau.

### D — nhãn block có được dùng với `continue`?

~~~java
// block: {
//     continue block;
// }
~~~

**Đáp án:** không; `continue` có nhãn chỉ nhắm tới một vòng lặp. Với block có nhãn, có thể dùng `break block;` để rời block phù hợp.

### E — sau `continue outer`, `i++` có chạy không?

Với `outer: for (int i=0; i<3; i++)`, gọi `continue outer;` từ vòng trong khi `i=1`.

**Đáp án:** có. Lệnh chuyển tới **bước update của vòng for có nhãn**, `i++` đổi 1 thành 2, rồi điều kiện `i<3` được kiểm tra.

## 14. Lỗi thường gặp và kết luận

| Sai lầm | Hậu quả | Sửa |
|---|---|---|
| Dùng `break;` trong vòng trong để thoát cả hai | Vòng ngoài vẫn chạy | `break outer;` |
| Dùng `continue;` trong vòng trong để bỏ cả hàng | Chỉ bỏ một lượt vòng trong | `continue outer;` |
| Nhầm `continue outer` với kết thúc vòng ngoài | Vòng ngoài tiếp tục ở lượt kế | Dùng `break outer` nếu cần dừng hẳn |
| Nghĩ `continue outer` bỏ update của for ngoài | Hiểu sai biến đếm | Basic `for` vẫn chạy update ngoài |
| `continue someBlock;` | Không compile | Nhãn phải gắn với vòng lặp |
| Nhãn không nằm trên cấu trúc bao quanh câu lệnh | Không compile | Đặt nhãn cho vòng ngoài đích |
| Lạm dụng nhiều nhãn, nhiều cấp nhảy | Khó bảo trì | Tách thành method và dùng return khi rõ nghĩa |
| Nhầm `break;` trong switch với `break outer;` | Thoát sai cấp | Xác định switch/vòng có nhãn cần rời |

**Checklist:**

- [ ] Biết `break;` và `continue;` không nhãn mặc định tác động vòng lặp gần nhất.
- [ ] Biết cú pháp `label: for (...) { ... }`.
- [ ] Biết `break label;` thoát hoàn toàn vòng có nhãn.
- [ ] Biết `continue label;` bỏ phần còn lại của lượt hiện tại của vòng có nhãn.
- [ ] Biết `continue outer;` trong basic `for` vẫn chạy update của vòng ngoài.
- [ ] Hiểu `break outer;` không chạy update sau lượt bị ngắt.
- [ ] Phân biệt nhãn block và nhãn vòng lặp; `continue` chỉ chấp nhận nhãn vòng lặp.
- [ ] Nhận diện trường hợp switch lồng vòng lặp và chọn đúng nhãn.
- [ ] Kiểm thử biến đếm, nhánh dừng và code chạy sau vòng lặp.
- [ ] Chạy `LabeledLoopControlDemo.java` bằng JDK 17+ và đối chiếu exact stdout.

**Kết luận:** Trong vòng lặp lồng, **`break outer` rời hẳn vòng ngoài**, còn **`continue outer` chỉ bỏ lượt ngoài đang chạy rồi chuyển tới bước cập nhật/kiểm tra của vòng đó**. Không có nhãn thì `break`/`continue` thông thường chỉ tác động vòng gần nhất. Dùng nhãn khi thật sự cần nhảy giữa các cấp lặp; nếu thuật toán nhiều điểm thoát quá phức tạp, hãy tách phương thức để dễ hiểu và kiểm thử.