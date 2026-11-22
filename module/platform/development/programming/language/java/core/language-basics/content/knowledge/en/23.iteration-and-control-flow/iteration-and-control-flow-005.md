# `break` và `continue` không nhãn — Java 17+

Hai lệnh `break;` và `continue;` giúp đổi luồng thực thi bên trong vòng lặp mà **không cần đặt nhãn (label)**.

- **`break;`**: kết thúc **vòng lặp hoặc `switch` gần nhất** đang bao quanh lệnh.
- **`continue;`**: bỏ phần còn lại của **lượt hiện tại của vòng lặp gần nhất**, chuyển sang bước chuẩn bị lượt tiếp theo. Nó **không** chuyển sang nhánh `case` kế tiếp của `switch`.

~~~java
for (int i = 0; i < 5; i++) {
    if (i == 3) break;
    if (i % 2 == 0) continue;
    System.out.println(i);
}
// Chỉ in 1.
~~~

Với `i = 0` và `i = 2`, `continue` bỏ lệnh in; với `i = 3`, `break` kết thúc hẳn vòng lặp.

## 1. Khác nhau ở đâu?

| Tiêu chí | `break;` không nhãn | `continue;` không nhãn |
| --- | --- | --- |
| Đích tác động | Vòng lặp hoặc `switch` gần nhất | **Vòng lặp** gần nhất |
| Thân hiện tại | Dừng ngay | Bỏ các câu lệnh còn lại trong lượt hiện tại |
| Sau lệnh | Đi đến câu lệnh phía sau cấu trúc bị thoát | Chuẩn bị lượt tiếp theo của vòng lặp |
| Trong basic `for` | Không chạy phần cập nhật của vòng vừa thoát | **Có chạy phần cập nhật** rồi mới kiểm tra điều kiện |
| Trong `while` | Thoát vòng | Quay lại kiểm tra điều kiện |
| Trong `do-while` | Thoát vòng | Tới bước kiểm tra điều kiện ở cuối |
| Trong `switch` | Thoát `switch` gần nhất | Chỉ hợp lệ nếu bên ngoài có vòng lặp thích hợp; chuyển sang lượt lặp |

**Quan trọng:** `if` không phải đích của `break` hay `continue`. Khi viết `if (condition) break;`, lệnh `break` tác động đến vòng lặp/`switch` bao quanh, không chỉ kết thúc khối `if`.

## 2. Demo Java 17+ tự chứa

Tạo file UTF-8 **`UnlabeledBreakContinueDemo.java`**:

~~~java
public class UnlabeledBreakContinueDemo {
    static void breakFor() {
        for (int i = 0; i < 5; i++) {
            if (i == 3) {
                System.out.println("breakAt=" + i);
                break;
            }
            System.out.println("keep=" + i);
        }
        System.out.println("afterBreakFor");
    }

    static int step(int i) {
        System.out.println("update=" + i);
        return i + 1;
    }

    static void continueFor() {
        for (int i = 0; i < 4; i = step(i)) {
            if (i == 1) {
                System.out.println("skip=" + i);
                continue;
            }
            System.out.println("body=" + i);
        }
        System.out.println("afterContinueFor");
    }

    static void continueWhile() {
        int n = 0;
        while (n < 4) {
            n++;  // Tiến triển trước khi có thể continue.
            if (n % 2 == 0) {
                System.out.println("skipEven=" + n);
                continue;
            }
            System.out.println("odd=" + n);
        }
        System.out.println("afterWhile=" + n);
    }

    static void continueDoWhile() {
        int attempt = 0;
        do {
            attempt++;
            if (attempt == 1) {
                System.out.println("doSkip=" + attempt);
                continue;
            }
            System.out.println("doBody=" + attempt);
        } while (attempt < 2);
        System.out.println("afterDo=" + attempt);
    }

    static void nestedLoops() {
        for (int row = 1; row <= 2; row++) {
            for (int col = 1; col <= 3; col++) {
                if (col == 2) {
                    System.out.println("innerContinue=" + row + "," + col);
                    continue;
                }
                if (row == 2 && col == 3) {
                    System.out.println("innerBreak=" + row + "," + col);
                    break;
                }
                System.out.println("grid=" + row + "," + col);
            }
            System.out.println("outerEnd=" + row);
        }
    }

    static void switchInsideFor() {
        for (int value = 0; value < 4; value++) {
            switch (value) {
                case 0:
                    System.out.println("caseZero");
                    break; // Chỉ thoát switch.
                case 1:
                    System.out.println("continueLoop");
                    continue; // Chuyển sang lượt for tiếp theo.
                case 2:
                    System.out.println("caseTwo");
                    break;
                default:
                    System.out.println("caseDefault");
            }
            System.out.println("afterSwitch=" + value);
        }
    }

    public static void main(String[] args) {
        System.out.println("== break for ==");
        breakFor();

        System.out.println("== continue for ==");
        continueFor();

        System.out.println("== continue while ==");
        continueWhile();

        System.out.println("== continue do-while ==");
        continueDoWhile();

        System.out.println("== nested loops ==");
        nestedLoops();

        System.out.println("== switch inside for ==");
        switchInsideFor();
        System.out.println("done");
    }
}
~~~

Dùng **JDK 17 trở lên**, mở PowerShell hoặc Bash tại thư mục chứa file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 UnlabeledBreakContinueDemo.java
java UnlabeledBreakContinueDemo
~~~

**Exact expected stdout** của riêng lệnh `java UnlabeledBreakContinueDemo`:

~~~text
== break for ==
keep=0
keep=1
keep=2
breakAt=3
afterBreakFor
== continue for ==
body=0
update=0
skip=1
update=1
body=2
update=2
body=3
update=3
afterContinueFor
== continue while ==
odd=1
skipEven=2
odd=3
skipEven=4
afterWhile=4
== continue do-while ==
doSkip=1
doBody=2
afterDo=2
== nested loops ==
grid=1,1
innerContinue=1,2
grid=1,3
outerEnd=1
grid=2,1
innerContinue=2,2
innerBreak=2,3
outerEnd=2
== switch inside for ==
caseZero
afterSwitch=0
continueLoop
caseTwo
afterSwitch=2
caseDefault
afterSwitch=3
done
~~~

`java -version` và `javac -version` cho thông tin khác nhau theo môi trường JDK và không nằm trong stdout cố định. Ví dụ không cần thư viện ngoài.

## 3. `break`: thoát hoàn toàn vòng lặp gần nhất

~~~java
int[] numbers = {2, 4, -1, 8};
for (int n : numbers) {
    if (n < 0) {
        break;
    }
    System.out.println(n);
}
// In: 2, 4. Giá trị 8 không được xử lý.
~~~

Gặp `-1` thì `break` lập tức thoát vòng; vòng không được khởi động lượt tiếp theo. Nếu cần tìm phần tử đầu tiên phù hợp, thoát sớm bằng `break` thường tiết kiệm các bước thừa.

`break` không kết thúc phương thức đang chứa nó: Java tiếp tục chạy các câu lệnh **sau vòng lặp**. Muốn kết thúc hẳn phương thức, dùng `return` thích hợp.

Trong các vòng **lồng nhau**, `break;` không nhãn chỉ thoát **vòng trong gần nhất**:

~~~java
for (int row = 0; row < 2; row++) {
    for (int col = 0; col < 3; col++) {
        if (col == 1) break;
        System.out.println(row + ":" + col);
    }
}
// In 0:0 rồi 1:0.
~~~

Vòng ngoài vẫn chạy lượt tiếp theo. Nếu nghiệp vụ muốn thoát nhiều tầng, cần thiết kế lại luồng (ví dụ dùng phương thức hỗ trợ trả `boolean` hoặc `return`); trường hợp dùng `break` có nhãn là một chủ đề riêng, không phải hành vi của `break;` không nhãn.

## 4. `continue`: bỏ phần còn lại của lượt hiện tại

~~~java
int[] values = {3, -1, 5};
for (int value : values) {
    if (value < 0) {
        continue;
    }
    System.out.println(value);
}
// In 3 rồi 5.
~~~

Lệnh `continue` **không thoát vòng hoàn toàn**: nó chỉ bỏ các câu lệnh nằm sau nó trong thân *của lượt hiện tại*. Vòng sẽ tiếp tục nếu còn lượt và điều kiện cho phép.

**Điểm dễ quên:** với basic `for`, `continue` vẫn chạy phần cập nhật:

~~~java
for (int i = 0; i < 3; i++) {
    if (i == 1) continue;
    System.out.println(i);
}
// In 0 rồi 2, kết thúc bình thường.
~~~

Trong chương trình đầy đủ, hàm `step(i)` in log, chứng minh rằng cả lượt có `continue` tại `i == 1` vẫn tạo dòng `update=1`.

Với `while`, `continue` quay thẳng về điều kiện, nên phải bảo đảm biến điều khiển **đã tiến triển**:

~~~java
int i = 0;
while (i < 3) {
    i++;
    if (i == 2) continue;
    System.out.println(i);
}
// In 1 rồi 3.
~~~

Nếu để `i++` sau `continue`, rất dễ tạo vòng lặp vô hạn. Với `do-while`, `continue` chuyển tới **bước kiểm tra điều kiện sau thân**, không nhảy lên đầu thân một cách vô điều kiện.

## 5. `switch` nằm trong vòng lặp: đích có thể khác nhau

~~~java
for (int i = 0; i < 3; i++) {
    switch (i) {
        case 0:
            System.out.println("zero");
            break;    // Thoát switch, KHÔNG thoát for.
        case 1:
            continue; // Đến lượt for kế tiếp.
        default:
            System.out.println("other");
    }
    System.out.println("after-switch");
}
~~~

Với `i == 0`, lệnh `break` đi tới câu lệnh `after-switch` **trong cùng lượt for**. Với `i == 1`, `continue` bỏ luôn lệnh `after-switch`, cập nhật `i++` rồi xét lượt kế. Với `i == 2`, nhánh `default` được chạy và sau đó in `after-switch`.

Đây là khác biệt quan trọng giữa hai từ khóa:

| Vị trí câu lệnh | `break;` | `continue;` |
| --- | --- | --- |
| Trong `for`, không có `switch` bao quanh | Thoát `for` | Lượt tiếp theo của `for` |
| Trong `switch` nằm trong `for` | Thoát `switch` | Lượt tiếp theo của `for` |
| Trong vòng trong của hai vòng lồng nhau | Thoát vòng trong | Lượt tiếp theo của vòng trong |
| Trong `switch` độc lập, không nằm trong vòng lặp | Hợp lệ, thoát `switch` | **Không hợp lệ**, không có vòng lặp để tiếp tục |

Không nhầm `break` của `switch` dạng `case:` với ngữ nghĩa `case ->`: rule dùng dấu mũi tên tự tách nhánh, còn lệnh `break;` không nhãn vẫn dùng để thoát vòng lặp hoặc switch thích hợp.

## 6. Phân biệt với `return` và tác động đến dọn dẹp tài nguyên

| Lệnh | Ý nghĩa chính |
| --- | --- |
| `break;` | Thoát vòng lặp / switch gần nhất |
| `continue;` | Bỏ phần còn lại của lượt lặp gần nhất |
| `return;` hoặc `return value;` | Rời **phương thức** đang chạy |
| `throw ...;` | Ném ngoại lệ, chuyển theo cơ chế xử lý ngoại lệ |

Dù `break` hoặc `continue` đổi điểm đến, các khối `finally` cần chạy theo quy tắc Java vẫn được thực thi khi thoát qua chúng; không dùng hai lệnh này để né đóng tài nguyên. Với stream/file, ưu tiên `try-with-resources` khi cần bảo đảm đóng.

Nếu có vòng vô hạn chủ đích, có thể dùng `while (true)` cộng điều kiện `break`. Còn nếu mục tiêu chỉ là bỏ qua một giá trị không hợp lệ trong các lượt duyệt tiếp, `continue` thường sát ý định hơn.

## 7. Các lỗi thường gặp

| Hiểu nhầm | Cách đúng |
| --- | --- |
| “`break` trong vòng lồng nhau thoát cả hai vòng.” | Không nhãn chỉ thoát cấu trúc gần nhất thích hợp |
| “`continue` kết thúc toàn bộ vòng lặp.” | Chỉ kết thúc **lượt hiện tại** |
| “`continue` trong `for` bỏ luôn `i++`.” | Phần cập nhật vẫn chạy nếu `continue` nhắm vào `for` đó |
| “`continue` trong `while` tự tăng biến đếm.” | Không; tự bảo đảm tiến triển |
| “`break` trong `switch` nằm trong vòng sẽ thoát vòng.” | Chỉ thoát `switch` gần nhất |
| “`continue` chuyển sang `case` kế.” | Nó chuyển sang lượt của **vòng lặp**, không phải nhãn `case` |
| “Chỉ cần nằm trong `if` là có thể dùng `break`.” | Phải có vòng lặp hoặc switch thích hợp bao quanh |
| “`continue` dùng được trong `switch` độc lập.” | Không; phải nằm trong vòng lặp phù hợp |

## 8. Bài tập tự kiểm tra

1. `for (int i=0; i<4; i++) { if (i==2) break; print(i); }` in gì?  
   *Đáp án:* 0, 1.
2. Thay `break` bằng `continue` ở câu trên thì in gì?  
   *Đáp án:* 0, 1, 3.
3. Hai vòng lồng nhau, `break;` trong vòng trong có làm vòng ngoài dừng luôn không?  
   *Đáp án:* Không.
4. `continue;` trong basic `for` có chạy phần cập nhật không?  
   *Đáp án:* Có.
5. `break;` trong `switch` nằm trong `while` thoát cấu trúc nào?  
   *Đáp án:* `switch` gần nhất.
6. `continue;` trong `switch` nằm trong `while` chuyển đến đâu?  
   *Đáp án:* Bước kiểm tra điều kiện của `while` gần nhất.
7. Vì sao `continue` trước lệnh cập nhật trong `while` nguy hiểm?  
   *Đáp án:* Biến điều khiển có thể không đổi và khiến vòng lặp vô hạn.

## Checklist

- [ ] `break;` thoát vòng lặp hoặc switch gần nhất, không tự kết thúc phương thức.
- [ ] `continue;` bỏ phần còn lại của lượt hiện tại của vòng gần nhất.
- [ ] Nắm khác biệt về cập nhật của basic `for`, `while` và `do-while`.
- [ ] Xác định đúng vòng **bên trong** khi có các vòng lồng nhau.
- [ ] Phân biệt `break` của `switch` và `continue` hướng tới vòng lặp bao ngoài.
- [ ] Bảo đảm điều kiện tiến triển và tài nguyên được xử lý đúng.

**Kết luận:** `break;` không nhãn là **thoát cấu trúc lặp/`switch` gần nhất**, còn `continue;` không nhãn là **bỏ phần còn lại của lượt trong vòng lặp gần nhất**. Luôn xác định chính xác cấu trúc bao quanh và bước cập nhật tiếp theo để tránh dừng sai hoặc lặp vô hạn.
