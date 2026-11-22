# Vòng lặp vô hạn và điều kiện bảo đảm kết thúc trong Java

> **Java core — language-basics / Vòng lặp**  
> **Môi trường:** Java 17+, ví dụ một file tự chứa, chỉ dùng JDK.  
> **Mục tiêu:** Phân biệt vòng lặp vô hạn do lỗi với vòng lặp chạy lâu có chủ đích; xác định điều kiện dừng, trạng thái tiến triển, giới hạn số lượt và cách tránh bẫy `continue`, `break`, tràn số.

## 1. Thế nào là vòng lặp vô hạn?

Một vòng lặp tiếp tục khi điều kiện lặp còn `true` (hoặc cố ý dùng `for (;;)`/`while (true)`). Nó trở thành **vòng lặp vô hạn** khi không có đường đi thực tế khiến luồng thoát khỏi vòng lặp.

~~~java
// Ví dụ lỗi: KHÔNG CHẠY đoạn này.
// int count = 0;
// while (count < 3) {
//     System.out.println(count);
//     // Quên count++: count mãi bằng 0.
// }
~~~

Có hai tình huống cần phân biệt:

- **Vô hạn ngoài ý muốn:** Biến không cập nhật, điều kiện không thể sai, bỏ qua cập nhật bằng `continue`, hoặc tràn số làm vòng lặp quay lại trạng thái cũ.
- **Vô hạn có chủ đích:** Bộ xử lý sự kiện, server hoặc worker chạy cho tới khi nhận tín hiệu dừng. Loại này vẫn cần cơ chế **hủy, ngắt, thoát hoặc đóng tài nguyên** rõ ràng.

Đừng coi “chạy rất lâu” đồng nghĩa “vô hạn”. Một vòng lặp có giới hạn hàng triệu lần vẫn hữu hạn, nhưng có thể tốn CPU hoặc làm ứng dụng thiếu phản hồi. Ngược lại, có điều kiện thoát trong mã **không bảo đảm** điều kiện đó nhất định sẽ xảy ra khi dữ liệu từ bên ngoài không hợp tác.

## 2. Ba câu hỏi để đánh giá khả năng kết thúc

Đối với mỗi vòng lặp, hãy xác định:

1. **Điều kiện tiếp tục / dừng:** Khi nào phép kiểm tra trở thành false, hoặc khi nào `break`/`return` được thực hiện?
2. **Trạng thái tiến triển:** Trong mọi đường chạy tiếp, biến hoặc dữ liệu nào được cập nhật để tiến gần điểm dừng?
3. **Giới hạn:** Có miền hữu hạn, giới hạn số lượt thử, deadline hoặc tín hiệu hủy đáng tin cậy không?

Một cách chứng minh hữu ích là tìm *loop variant* (đại lượng đo tiến triển): một số nguyên **không âm**, **giảm nghiêm ngặt mỗi lượt** khi vòng lặp tiếp tục và không bị reset hoặc tràn số. Khi đó nó không thể giảm mãi, nên vòng lặp phải dừng nếu mỗi lượt đều hoàn thành.

Ví dụ:

~~~java
int remaining = 4;

while (remaining > 0) {
    System.out.println("remaining=" + remaining);
    remaining--; // 4 -> 3 -> 2 -> 1 -> 0
}
~~~

Bất biến có ích: đầu mỗi lượt, `remaining >= 0`. Variant: `remaining`. Mỗi lượt giảm đúng 1, đến 0 thì `remaining > 0` false. Với biến ban đầu bằng 4, thân chạy bốn lần.

**Điều kiện cần nêu rõ:** Lập luận trên giả định thân vòng lặp luôn chạy đến bước cập nhật (không bị treo chờ bên ngoài) và phép tính không vi phạm miền/giới hạn kiểu số.

## 3. Ví dụ có bảo đảm kết thúc với `for` và `while`

~~~java
static int countUp(int limit) {
    int count = 0;
    for (int i = 0; i < limit; i++) {
        count++;
    }
    return count;
}
~~~

Với `limit = 4`, `i` đi qua 0, 1, 2, 3 và dừng khi `i == 4`. Với `limit <= 0`, thân chạy 0 lần. Điều kiện biên và cập nhật nằm gần nhau nên dễ kiểm tra.

Ví dụ đếm ngược:

~~~java
static int countdown(int start) {
    int remaining = Math.max(start, 0);
    int rounds = 0;
    while (remaining > 0) {
        rounds++;
        remaining--;
    }
    return rounds;
}
~~~

Với `start = 3`, variant là `remaining`: 3 → 2 → 1 → 0. Với `start <= 0`, vòng lặp không chạy.

Ví dụ tiến triển không cần giảm mỗi lần đúng 1:

~~~java
int n = 15;
int rounds = 0;
while (n > 0) {
    n /= 2;    // 15 -> 7 -> 3 -> 1 -> 0.
    rounds++;
}
// rounds == 4
~~~

Khi `n` là số nguyên dương, `n / 2 < n` và kết quả không âm, nên số lượt hữu hạn. Một variant tốt cần thể hiện **tiến triển trên mọi nhánh có thể quay lại đầu vòng lặp**.

## 4. Những lỗi khiến trạng thái không tiến triển

| Lỗi | Ví dụ | Cách sửa |
| --- | --- | --- |
| Quên cập nhật biến | `while (i < 5) { print(i); }` | Tăng `i` hoặc làm trạng thái thay đổi trong mọi đường đi |
| Cập nhật sai chiều | `while (i < 5) { i--; }` khi `i=0` | Cập nhật hướng tới ngưỡng dừng |
| `continue` bỏ qua cập nhật | `while (i < 5) { if (i==2) continue; i++; }` | Di chuyển cập nhật trước `continue` hoặc dùng `for` phù hợp |
| Điều kiện luôn đúng | `while (true)` không có cơ chế thoát | Thiết kế `break`, `return` hoặc tín hiệu hủy |
| Điều kiện chỉ phụ thuộc ngoại cảnh | Chờ một giá trị không bao giờ đến | Giới hạn retry, timeout và xử lý hết hạn |
| Tràn số ở biến điều khiển | `i++` sau `Integer.MAX_VALUE` | Dùng giới hạn phù hợp và không dựa vào overflow để dừng |

Ví dụ `continue` đúng với vòng `while`:

~~~java
int i = 0;
int oddCount = 0;

while (i < 6) {
    i++; // Cập nhật TRƯỚC mọi continue.
    if (i % 2 == 0) {
        continue;
    }
    oddCount++;
}
// i == 6; oddCount == 3 (1, 3, 5).
~~~

Trong `while`, `continue` nhảy thẳng tới kiểm tra điều kiện. Trong `for (init; condition; update)`, `continue` sẽ chuyển tới **biểu thức update** rồi mới kiểm tra điều kiện, miễn không có luồng thoát bất thường.

**Tràn `int`:** `Integer.MAX_VALUE + 1` trở thành `Integer.MIN_VALUE`. Vòng như sau có thể chạy mãi vì mọi giá trị `int` đều thỏa `i <= Integer.MAX_VALUE`:

~~~java
// KHÔNG CHẠY: điều kiện luôn đúng với kiểu int.
// for (int i = 0; i <= Integer.MAX_VALUE; i++) {
//     // ...
// }
~~~

Dùng điều kiện giới hạn thực sự có thể thành false, tránh so sánh với giá trị lớn nhất của kiểu, và cân nhắc `long` hay một thiết kế lặp khác nếu miền đếm lớn.

## 5. `while (true)` có thể đúng nếu có lối ra hữu hạn

Dùng vòng vô hạn có chủ đích khi **điểm dừng được quyết định trong thân**. Ví dụ đọc một dãy cho tới khi thấy số dương hoặc hết dữ liệu:

~~~java
static String firstPositive(int[] values) {
    int index = 0;
    while (true) {
        if (index >= values.length) {
            return "NOT_FOUND"; // Hết dữ liệu -> kết thúc.
        }

        int candidate = values[index++]; // Tiến triển trước continue.
        if (candidate <= 0) {
            continue;
        }
        return "FOUND:" + candidate;
    }
}
~~~

Dù điều kiện vòng là hằng `true`, hàm vẫn **bảo đảm kết thúc** với mảng hữu hạn: `index` tăng mỗi lượt, hoặc tìm được số dương để `return`, hoặc đến `values.length` để `return`. Không truy cập ngoài mảng, kể cả mảng rỗng vì kiểm tra trước khi lấy phần tử.

Đây là bằng chứng dừng dựa trên đại lượng `values.length - index` (không âm và giảm mỗi lượt có thể lặp lại).

**Nếu nguồn dữ liệu là mạng/bàn phím** thay vì mảng hữu hạn, việc “sớm muộn gì cũng có dữ liệu hợp lệ” chỉ là giả định. Cần tính đến hết luồng, timeout, lỗi I/O và tín hiệu hủy.

## 6. Chặn số lần thử, xử lý `break` và hủy tác vụ

Một giới hạn rõ ràng làm vòng lặp dừng ngay cả khi chưa tìm thấy kết quả:

~~~java
static String tryGuess(int[] guesses, int target, int maxAttempts) {
    int bound = Math.min(guesses.length, Math.max(maxAttempts, 0));
    int attempts = 0;

    while (attempts < bound) {
        int guess = guesses[attempts++];
        if (guess == target) {
            return "FOUND:" + attempts;
        }
    }
    return "STOP:" + attempts;
}
~~~

Vì `attempts` tăng mỗi lượt và `bound` cố định, không âm và không vượt độ dài mảng, vòng lặp dừng tối đa `bound` lượt. Hàm phân biệt thành công với hết lượt thử thay vì giả định kết thúc nghĩa là đã tìm thấy.

Một ví dụ ngắn cho `break`:

~~~java
int attempts = 0;
while (true) {
    attempts++;
    if (attempts == 2) {
        break;
    }
}
// attempts == 2.
~~~

`break` rời vòng gần nhất; `return` rời phương thức. Tuy nhiên, **chỉ đặt `break` trong thân chưa phải bằng chứng dừng**: phải chỉ ra vì sao điều kiện dẫn tới `break` cuối cùng chắc chắn đúng.

Với worker/service chạy lâu, bổ sung cơ chế hủy bằng cách phù hợp (ví dụ `Thread.interrupt()` và xử lý ngắt ở nơi chờ), tránh vòng `while (true)` quay liên tục không nghỉ làm chiếm CPU. Nếu dùng cờ dừng chia sẻ giữa các luồng, cần cơ chế nhìn thấy cập nhật đúng như `volatile` hoặc lớp đồng bộ phù hợp; biến boolean thường không đảm bảo đủ tính hiển thị giữa các luồng.

## 7. Chương trình Java 17+ runnable

Tạo file **LoopTerminationDemo.java**:

~~~java
public final class LoopTerminationDemo {
    private static int countUp(int limit) {
        int count = 0;
        for (int i = 0; i < limit; i++) {
            count++;
        }
        return count;
    }

    private static int countdown(int start) {
        int remaining = Math.max(start, 0);
        int rounds = 0;
        while (remaining > 0) {
            rounds++;
            remaining--;
        }
        return rounds;
    }

    private static int halveUntilZero(int start) {
        int n = Math.max(start, 0);
        int rounds = 0;
        while (n > 0) {
            n /= 2;
            rounds++;
        }
        return rounds;
    }

    private static String firstPositive(int[] values) {
        int index = 0;
        while (true) {
            if (index >= values.length) {
                return "NOT_FOUND";
            }

            int candidate = values[index++];
            if (candidate <= 0) {
                continue;
            }
            return "FOUND:" + candidate;
        }
    }

    private static int countOdds(int limit) {
        int i = 0;
        int oddCount = 0;
        while (i < limit) {
            i++;
            if (i % 2 == 0) {
                continue;
            }
            oddCount++;
        }
        return oddCount;
    }

    private static String tryGuess(
            int[] guesses, int target, int maxAttempts) {
        int bound = Math.min(guesses.length, Math.max(maxAttempts, 0));
        int attempts = 0;

        while (attempts < bound) {
            int guess = guesses[attempts++];
            if (guess == target) {
                return "FOUND:" + attempts;
            }
        }
        return "STOP:" + attempts;
    }

    public static void main(String[] args) {
        System.out.println("forCount4=" + countUp(4));
        System.out.println("forCount0=" + countUp(0));
        System.out.println("countdown3=" + countdown(3));
        System.out.println("countdown0=" + countdown(0));
        System.out.println("halve15=" + halveUntilZero(15));
        System.out.println("halve1=" + halveUntilZero(1));

        System.out.println("positiveFound="
                + firstPositive(new int[] {-2, 0, 5, 9}));
        System.out.println("positiveMissing="
                + firstPositive(new int[] {-3, 0}));
        System.out.println("positiveEmpty="
                + firstPositive(new int[] {}));

        System.out.println("oddsUpTo6=" + countOdds(6));

        int[] guesses = {2, 7, 9};
        System.out.println("guessFound=" + tryGuess(guesses, 7, 3));
        System.out.println("guessStop=" + tryGuess(guesses, 9, 2));
        System.out.println("guessZero=" + tryGuess(guesses, 9, 0));

        int attempts = 0;
        while (true) {
            attempts++;
            if (attempts == 2) {
                break;
            }
        }
        System.out.println("breakAfter=" + attempts);

        int max = Integer.MAX_VALUE;
        System.out.println("intOverflow=" + (max + 1));
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 LoopTerminationDemo.java
java LoopTerminationDemo
~~~

**Expected stdout chính xác:**

~~~text
forCount4=4
forCount0=0
countdown3=3
countdown0=0
halve15=4
halve1=1
positiveFound=FOUND:5
positiveMissing=NOT_FOUND
positiveEmpty=NOT_FOUND
oddsUpTo6=3
guessFound=FOUND:2
guessStop=STOP:2
guessZero=STOP:0
breakAfter=2
intOverflow=-2147483648
~~~

Những dòng `positiveMissing`, `positiveEmpty` và `guessStop` cho thấy lối thoát khi không thành công. `oddsUpTo6=3` chứng tỏ `continue` không chặn cập nhật biến điều khiển. `intOverflow` minh họa vì sao không dùng giới hạn `Integer.MAX_VALUE` theo cách khiến điều kiện luôn true.

## 8. Checklist và bài tập

| Câu hỏi trước khi chấp nhận vòng lặp | Yêu cầu |
| --- | --- |
| Điều kiện dừng là gì? | Có điều kiện trở thành false hoặc lối thoát bảo đảm đạt được |
| Tiến triển đo bằng đại lượng nào? | Không âm, tiến về giới hạn theo mọi đường tiếp tục |
| Có đường `continue` không cập nhật? | Cập nhật trước `continue` hoặc có update bảo đảm |
| Biến đếm có thể tràn số không? | Kiểm tra miền số và cấu trúc điều kiện |
| Có đang phụ thuộc vào input/nguồn ngoài? | Có giới hạn, timeout, EOF hoặc hủy |
| Khi hết lượt mà chưa thành công? | Trả trạng thái thất bại riêng, không suy diễn là thành công |

**Bài 1.** Xác định vì sao `int i=0; while(i<5){ if(i==2)continue; i++; }` kẹt ở `i == 2`, sau đó sửa bằng cách bảo đảm tăng `i` ở mọi đường đi.

**Bài 2.** Dùng variant để giải thích tại sao `while (remaining > 0) { remaining--; }` kết thúc khi `remaining` là số nguyên không âm ban đầu.

**Bài 3.** Thay `n /= 2` thành `n = n - 2` cho `n=15`. Viết điều kiện dừng sao cho không có giá trị âm gây hành vi sai ý định.

**Bài 4.** Viết `while(true)` để tìm phần tử phù hợp trong mảng hữu hạn. Phải có các trường hợp kết thúc nào khi mảng rỗng hoặc không tìm thấy?

**Bài 5.** Thiết kế hàm thử đăng nhập tối đa 3 lần: nếu đúng, trả thành công; nếu hết 3 lần, trả thất bại. Giải thích vì sao chỉ chờ người dùng nhập đúng không phải một bảo đảm kết thúc.

### Ghi nhớ

**Bảo đảm kết thúc = có điểm dừng + tiến triển đáng tin cậy + không mất điểm dừng do tràn số, đường nhánh hoặc dữ liệu bên ngoài.** Với vòng lặp hữu hạn, dùng giới hạn hoặc một variant không âm giảm nghiêm ngặt. Với `while(true)`, cần lối thoát có thể chứng minh và cơ chế hủy thích hợp; tránh vòng quay chiếm CPU không mục đích.
