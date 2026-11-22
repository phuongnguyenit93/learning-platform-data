# Không viết chuỗi so sánh kiểu toán học như `0 < x < 10` trong Java

> **Java core — language-basics / So sánh**  
> **Phiên bản:** Java 17+, một file runnable không cần thư viện ngoài.  
> **Mục tiêu:** Giải thích lỗi biên dịch của `0 < x < 10`; chuyển thành các phép so sánh độc lập nối bằng `&&`, chọn đúng biên mở/đóng và tránh tác dụng phụ khi đánh giá biểu thức.

## 1. Vì sao `0 < x < 10` không biên dịch?

Trong toán học, `0 < x < 10` có nghĩa `x` **đồng thời** lớn hơn 0 và nhỏ hơn 10. Trong Java, toán tử quan hệ `<` trả **`boolean`**, không phải một số.

~~~java
int x = 5;
// boolean valid = 0 < x < 10; // LỖI BIÊN DỊCH.
~~~

Hai toán tử `<` ở cùng mức ưu tiên và nhóm từ trái sang phải, nên cách hiểu cú pháp là:

~~~text
(0 < x) < 10
 \___/
 boolean
~~~

`0 < x` trả true/false, sau đó chương trình cố so sánh `boolean < int` — không hợp lệ. Đây là **lỗi kiểu khi biên dịch**, không phải một phép kiểm tra khoảng trả false.

Lỗi tương tự xuất hiện với `0 <= x <= 10`, `a < b < c` hoặc `a > b >= c`. Java không biến chuỗi so sánh quan hệ thành phép AND một cách tự động.

## 2. Viết đúng bằng `&&`

~~~java
int x = 5;
boolean inside = 0 < x && x < 10; // true.
~~~

Tương đương:

~~~java
boolean inside = (0 < x) && (x < 10);
~~~

Đây là **hai** phép so sánh độc lập, mỗi phép tạo một giá trị `boolean`. `&&` kết hợp các kết quả: toàn bộ true chỉ khi **cả hai đều true**.

Toán tử quan hệ có độ ưu tiên cao hơn `&&`, nên dấu ngoặc là tùy chọn ở biểu thức đơn giản. Với điều kiện dài hoặc trộn nhiều phép toán, dấu ngoặc giúp làm rõ ý định.

**Không dùng OR để thay thế:** `0 < x || x < 10` là điều kiện “hoặc”; với `x = -5`, vế thứ hai true; với `x = 20`, vế thứ nhất true. Nó không có nghĩa “x nằm giữa 0 và 10”.

## 3. Chọn đúng dấu ở các biên

| Khoảng cần kiểm tra | Biểu thức Java | Với `x=0` | Với `x=10` |
| --- | --- | --- | --- |
| Mở: lớn hơn 0, nhỏ hơn 10 | `0 < x && x < 10` | false | false |
| Đóng: từ 0 đến 10 | `0 <= x && x <= 10` | true | true |
| Lấy 0, loại 10 | `0 <= x && x < 10` | true | false |
| Loại 0, lấy 10 | `0 < x && x <= 10` | false | true |

Với khoảng mở `(0, 10)`, các giá trị 1 đến 9 (nếu `x` là số nguyên) hợp lệ; 0, 10 và mọi số ngoài khoảng đều không hợp lệ. Với chỉ số mảng, khoảng thường là **`0 <= index && index < array.length`**, vì chỉ số cuối là `length - 1`.

Muốn kiểm tra **nằm ngoài khoảng mở** thì dùng `x <= 0 || x >= 10`. Quy tắc De Morgan cho phép viết phủ định của `0 < x && x < 10` dưới dạng `!(0 < x && x < 10)`; chú ý với số thực `NaN`, hai cách diễn đạt phủ định phải được xét theo đúng semantics.

## 4. Short-circuit và kiểm tra an toàn

`&&` đánh giá vế trái trước. Nếu vế trái false, Java **bỏ qua vế phải**. Ví dụ bảo vệ chỉ số mảng:

~~~java
int[] values = {10, 20, 30};
int index = -1;

boolean safe = index >= 0
        && index < values.length
        && values[index] > 0;
// safe=false; values[-1] không được truy cập.
~~~

Nếu đặt `values[index] > 0` trước kiểm tra `index >= 0`, chương trình có thể ném `ArrayIndexOutOfBoundsException`. Với boolean `&`, Java đánh giá cả hai vế, không short-circuit, nên không thích hợp để bảo vệ vế phải trong tình huống này.

`&&` không làm cho mọi lỗi biến mất; chỉ bỏ qua **vế phải chưa cần đánh giá**. Vẫn phải viết điều kiện bảo vệ đúng thứ tự, bao gồm kiểm tra `null` trước khi gọi phương thức trên đối tượng.

## 5. Không đọc hoặc tính lại một giá trị có tác dụng phụ

Cách viết sau có thể kiểm tra **hai giá trị khác nhau**, không phải một số `x`:

~~~java
// Không nên dùng nếu readValue() có thể trả kết quả khác mỗi lần:
boolean result = 0 < readValue() && readValue() < 10;
~~~

Nếu lời gọi đầu tiên trả 5 và lời gọi thứ hai trả 50, toàn bộ điều kiện false, dù 5 thực sự nằm trong khoảng mở. Short-circuit còn làm cho lời gọi thứ hai **không được thực hiện** khi lời gọi đầu không thỏa giới hạn dưới.

Khi muốn kiểm tra **một lần đọc duy nhất**, hãy lưu kết quả:

~~~java
int x = readValue();
boolean inside = 0 < x && x < 10;
~~~

Điều này đặc biệt quan trọng với việc đọc input, đo thời gian, lấy dữ liệu thay đổi, random hoặc hàm có side effect.

## 6. Hai bẫy: `==` giữa boolean và `NaN`

Không nên cố thay `&&` bằng một phép so sánh bằng nhau giữa hai điều kiện:

~~~java
// Biên dịch được nhưng KHÔNG tương đương kiểm tra trong khoảng:
boolean wrong = (0 < x) == (x < 10);
~~~

Phép `==` chỉ hỏi **hai giá trị boolean có giống nhau không**. Nếu cả hai cùng false, kết quả vẫn true, trong khi AND phải false.

Điều này có thể được chứng minh bằng số thực `Double.NaN`:

~~~java
double x = Double.NaN;
boolean valid = 0.0 < x && x < 10.0; // false.
boolean wrong = (0.0 < x) == (x < 10.0); // true.
~~~

Vì mọi so sánh thứ tự `<`/`>` đối với `NaN` là false, biểu thức `false == false` trở thành true. Khi cần kiểm tra đầu vào `double` phải **hữu hạn**, thêm `Double.isFinite(x)`:

~~~java
boolean inside = Double.isFinite(x) && 0.0 < x && x < 10.0;
~~~

Đừng cố chuyển `boolean` thành số để viết chuỗi so sánh: Java không hỗ trợ ép `boolean` thành `int`. Dùng trực tiếp các phép toán logic.

## 7. Chương trình Java 17+ chạy độc lập

Tạo file **RangeComparisonDemo.java**:

~~~java
public final class RangeComparisonDemo {
    private static int reads;

    private static int readValue() {
        reads++;
        return reads == 1 ? 5 : 50;
    }

    private static boolean open(int x) {
        return 0 < x && x < 10;
    }

    private static boolean closed(int x) {
        return 0 <= x && x <= 10;
    }

    public static void main(String[] args) {
        for (int x : new int[] {-1, 0, 1, 9, 10, 11}) {
            System.out.println("x=" + x
                    + ",open=" + open(x)
                    + ",closed=" + closed(x));
        }

        int[] values = {10, 20, 30};
        int index = -1;
        boolean safe = index >= 0
                && index < values.length
                && values[index] > 0;
        System.out.println("guardedIndex=" + safe);

        double nan = Double.NaN;
        System.out.println("nanInRange="
                + (Double.isFinite(nan) && 0.0 < nan && nan < 10.0));
        System.out.println("nanEqualityTrap="
                + ((0.0 < nan) == (nan < 10.0)));

        reads = 0;
        boolean repeated = 0 < readValue() && readValue() < 10;
        System.out.println("repeated=" + repeated + ",reads=" + reads);

        reads = 0;
        int x = readValue();
        boolean sampled = 0 < x && x < 10;
        System.out.println("sampled=" + sampled + ",reads=" + reads);

        reads = 0;
        boolean skipped = readValue() < 0 && readValue() < 10;
        System.out.println("shortCircuit=" + skipped + ",reads=" + reads);
    }
}
~~~

Biên dịch và chạy ở thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 RangeComparisonDemo.java
java RangeComparisonDemo
~~~

**Expected stdout chính xác:**

~~~text
x=-1,open=false,closed=false
x=0,open=false,closed=true
x=1,open=true,closed=true
x=9,open=true,closed=true
x=10,open=false,closed=true
x=11,open=false,closed=false
guardedIndex=false
nanInRange=false
nanEqualityTrap=true
repeated=false,reads=2
sampled=true,reads=1
shortCircuit=false,reads=1
~~~

Trong ví dụ, `readValue()` trả 5 ở lần gọi đầu và 50 ở lần gọi thứ hai. `repeated` dùng **cả hai giá trị** nên false, còn `sampled` chỉ lấy một giá trị 5 nên true. Với `shortCircuit`, vế trái `5 < 0` false nên Java chỉ gọi `readValue()` một lần. `nanEqualityTrap=true` chứng minh so sánh **bằng nhau** giữa hai boolean không thay được `&&`.

## 8. Quy tắc thực hành và bài tập

| Trường hợp | Viết như thế nào? |
| --- | --- |
| Kiểm tra giá trị nằm giữa hai biên mở | `min < x && x < max` |
| Kiểm tra giá trị thuộc cả hai biên | `min <= x && x <= max` |
| Kiểm tra chỉ số mảng hợp lệ | `0 <= i && i < array.length` |
| Điều kiện ở vế phải có thể gây lỗi | Đặt guard bên trái `&&` |
| Giá trị lấy từ hàm có side effect | Gọi một lần, lưu vào biến trước khi so sánh |
| Số thực phải hữu hạn | Kết hợp `Double.isFinite(x)` với kiểm tra khoảng |

**Bài 1.** Viết điều kiện hợp lệ Java cho `-5 < x < 5` và `0 ≤ x ≤ 100`. Đừng dùng chuỗi quan hệ.

**Bài 2.** Giải thích vì sao `1 < x < 10` lỗi ngay từ lúc biên dịch; kiểu của `1 < x` là gì?

**Bài 3.** Kiểm tra `0 <= index && index < length` ở ba giá trị `index=-1`, `index=0`, `index=length`.

**Bài 4.** Vì sao `0 < getValue() && getValue() < 10` không nhất thiết kiểm tra một giá trị? Viết lại chỉ gọi `getValue()` một lần.

**Bài 5.** Chứng minh `(0.0 < Double.NaN) == (Double.NaN < 10.0)` true nhưng điều kiện AND trả false.

### Ghi nhớ

**Java không hỗ trợ `0 < x < 10`.** Phải viết **`0 < x && x < 10`** — hai phép so sánh độc lập nối bằng AND. Chọn `<` hoặc `<=` phù hợp với biên, tận dụng short-circuit cho guard và tránh gọi lại hàm có tác dụng phụ khi muốn kiểm tra **một** giá trị nhất quán.
