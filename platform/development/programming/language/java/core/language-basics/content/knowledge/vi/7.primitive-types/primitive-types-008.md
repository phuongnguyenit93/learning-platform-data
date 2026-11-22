# Chọn kiểu theo miền dữ liệu và yêu cầu tính toán trong Java

> **Java core — language-basics / Kiểu nguyên thủy**  
> **Yêu cầu:** JDK 17+, không cần thư viện ngoài cho ví dụ chạy chính.  
> **Mục tiêu:** Chọn kiểu đủ miền giá trị, độ chính xác và phép toán; tránh tràn số, chia nguyên ngoài ý muốn và sai số thập phân. Khi cần tính chính xác vượt đặc tính của kiểu nguyên thủy, biết lúc nào chuyển sang kiểu thư viện chuẩn.

## 1. Không chọn kiểu chỉ vì giá trị hiện tại vừa với nó

Một biến có kiểu khai báo cố định, nhưng **kết quả các phép tính trong tương lai** mới là yếu tố quan trọng. Trước khi chọn, tự hỏi:

1. Dữ liệu có **số nguyên, số lẻ, đúng/sai hay ký tự**?
2. Biên **nhỏ nhất/lớn nhất** của giá trị đầu vào và **kết quả trung gian** là bao nhiêu?
3. Có cần **chính xác tuyệt đối** (ví dụ số tiền) hay chấp nhận sai số làm tròn?
4. Có phải lưu số lượng rất lớn trong **mảng/buffer** hoặc giao tiếp với định dạng nhị phân cần độ rộng bit cụ thể?
5. Khi kết quả vượt miền, phải **báo lỗi** hay được phép chấp nhận quy tắc tràn/làm tròn?

Ví dụ: số lượng một đơn hàng có thể chỉ vài trăm, nhưng `quantity * priceInCents` có thể lớn hơn phạm vi `int`. Đừng chọn kiểu kết quả theo riêng biến `quantity`.


## 2. Ma trận quyết định dựa trên yêu cầu

Thay vì chọn kiểu chỉ theo số bit, hãy ghi rõ khả năng **biểu diễn**, **tính toán** và **tích hợp dữ liệu**:

| Nhu cầu thật sự | Chọn ban đầu | Điều phải kiểm chứng |
| --- | --- | --- |
| Đếm/số nguyên trong API Java thông thường | `int` | Tổng/tích lớn nhất có vượt khoảng ±2,1 tỷ không? |
| Đếm/tổng lớn hơn miền `int` | `long` | Trung gian đã nâng sang `long` chưa; liệu `long` có đủ? |
| Dữ liệu byte, giao thức số nguyên 16 bit | `byte`/`short` | Định dạng có dấu hay không dấu; cần diễn giải/kiểm tra miền ra sao? |
| Giá trị đo có dung sai | `double`, đôi khi `float` | Độ phân giải và cách xử lý `NaN`/`Infinity` có đáp ứng không? |
| Tiền hoặc phép tính decimal chính xác | `long` theo đơn vị nhỏ nhất hoặc `BigDecimal` | Quy tắc scale, làm tròn, miền giá trị và phép chia là gì? |
| Trạng thái đúng/sai | `boolean` | Có cần biểu diễn trạng thái chưa xác định bằng `Boolean` không? |
| Văn bản/Unicode | `String`; `char` cho code unit | Cần code unit, code point hay ký tự hiển thị? |

Bảng này là cách đưa **ràng buộc của bài toán** vào quyết định. Các bài trước đã giải thích cấu trúc và giới hạn của từng primitive; phần tiếp theo kiểm tra hậu quả khi chọn sai kiểu toán hạng.

## 3. Chọn `int` hay `long`: xét cả phép tính trung gian

Các literal số nguyên thập phân mặc định thường thuộc `int`. Dùng hậu tố `L` khi cần literal `long`:

~~~java
int count = 12_000;
long customers = 3_000_000_000L;
// long wrong = 3_000_000_000; // Sai: literal đã quá lớn cho int.
~~~

Quan trọng hơn, **kiểu biến nhận kết quả không tự nâng kiểu các toán hạng trước khi tính**:

~~~java
int side = 50_000;
long wrongArea = side * side;        // Phép nhân int đã tràn trước khi gán long.
long correctArea = (long) side * side; // Ít nhất một toán hạng long -> nhân long.
~~~

Giá trị đúng là `2_500_000_000`, vượt `Integer.MAX_VALUE`. `wrongArea` nhận `-1_794_967_296`: việc chuyển kết quả `int` đã tràn sang `long` không thể phục hồi thông tin bị mất.

Nếu muốn **phát hiện tràn**, có thể dùng `Math.multiplyExact`, `Math.addExact` hoặc `Math.subtractExact`; các phương thức đó ném `ArithmeticException` khi vượt miền `int`/`long` tương ứng. Chỉ ép lên `long` giải quyết tình huống `int` quá hẹp, **không** bảo đảm mọi phép nhân `long` đều an toàn.

## 4. Chọn kiểu theo cách phép toán được thực hiện

### Chia số nguyên khác chia số thực

~~~java
int whole = 7 / 4;          // 1: phép chia hai int, phần lẻ bị bỏ.
double stillWhole = 7 / 4;  // 1.0: phép chia int thực hiện trước khi gán.
double fraction = 7.0 / 4;  // 1.75: có toán hạng double.
~~~

Đừng kỳ vọng kiểu `double` của **biến đích** sửa được phép chia nguyên ở vế phải. Cần đưa ít nhất một toán hạng thành `double` trước phép tính nếu muốn kết quả phân số.

### `float` và `double` đều là số thực xấp xỉ

`float` tiết kiệm dung lượng hơn `double` nhưng có ít bit chính xác hơn. Ngay cả `double` cũng **không biểu diễn chính xác mọi số thập phân**, ví dụ kết quả của `0.1 + 0.2` thường không bằng chính xác literal `0.3` theo phép so sánh `==`.

Khi xử lý **tiền tệ/số thập phân cần chính xác**:

- Dùng **`long` chứa đơn vị nhỏ nhất** (ví dụ cents) nếu miền giá trị đủ, các quy tắc làm tròn/chia được xác định rõ và phép tính được kiểm soát tràn.
- Hoặc dùng **`BigDecimal`** trong `java.math`: đây là **kiểu tham chiếu**, không phải primitive. Khởi tạo từ chuỗi như `new BigDecimal("0.1")` để biểu diễn chính xác giá trị thập phân mong muốn; tránh `new BigDecimal(0.1)` khi muốn đúng 0,1 thập phân.
- Khi phép chia thập phân không kết thúc (chẳng hạn `1 / 3`), `BigDecimal.divide` cần quy định độ chính xác/cách làm tròn phù hợp.

Đừng dùng `float` chỉ vì giá trị hiện tại “nhỏ”; **độ chính xác** khác với **độ lớn miền biểu diễn**.

## 5. Chương trình Java 17+ chạy được

Tạo file **TypeChoiceDemo.java**:

~~~java
import java.math.BigDecimal;

public final class TypeChoiceDemo {
    public static void main(String[] args) {
        int units = 1_200;
        long centsPerUnit = 2_499L;
        long totalCents = units * centsPerUnit;

        int side = 50_000;
        long wrongArea = side * side;
        long correctArea = (long) side * side;

        int integerDivide = 7 / 4;
        double floatingDivide = 7.0 / 4;

        float roundedFloat = 16_777_217f;
        double approximate = 0.1 + 0.2;
        BigDecimal exact = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));

        boolean qualifies = totalCents >= 3_000_000L;
        char grade = 'A';

        System.out.println("totalCents=" + totalCents);
        System.out.println("intArea=" + wrongArea);
        System.out.println("longArea=" + correctArea);

        try {
            Math.multiplyExact(side, side);
        } catch (ArithmeticException ex) {
            System.out.println("checked=overflow");
        }

        System.out.println("integerDivide=" + integerDivide);
        System.out.println("floatingDivide=" + floatingDivide);
        System.out.println("floatRounded=" + (long) roundedFloat);
        System.out.println("doubleEquals0.3=" + (approximate == 0.3));
        System.out.println("exactDecimal=" + exact.toPlainString());
        System.out.println("qualifies=" + qualifies + ",grade=" + grade);
    }
}
~~~

Dùng terminal trong thư mục chứa tệp (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 TypeChoiceDemo.java
java TypeChoiceDemo
~~~

**Expected output chính xác:**

~~~text
totalCents=2998800
intArea=-1794967296
longArea=2500000000
checked=overflow
integerDivide=1
floatingDivide=1.75
floatRounded=16777216
doubleEquals0.3=false
exactDecimal=0.3
qualifies=false,grade=A
~~~

Giải thích: `units * centsPerUnit` dùng phép nhân `long` vì một toán hạng là `long`; kết quả 2.998.800 cents. `side * side` thực hiện `int` nên tràn; ép `side` sang `long` **trước phép nhân** cho 2.500.000.000. `Math.multiplyExact` báo tràn qua exception. `7 / 4` bỏ phần lẻ; `7.0 / 4` là phép chia `double`. Giá trị 16.777.217 không biểu diễn chính xác bằng `float` 32 bit và được làm tròn về 16.777.216. `BigDecimal` tạo từ chuỗi cho kết quả thập phân `0.3` chính xác.

## 6. Chuyển kiểu: khi nào có thể mất dữ liệu?

| Tình huống | Ví dụ | Điều cần lưu ý |
| --- | --- | --- |
| Mở rộng nguyên | `int x = 100; long y = x;` | Bảo toàn giá trị |
| Nguyên lớn sang số thực | `long x = 9_007_199_254_740_993L; double y = x;` | Có thể **mất độ chính xác** |
| Thu hẹp nguyên | `int x = 130; byte y = (byte) x;` | `y == -126` do giữ 8 bit thấp |
| Thực sang nguyên | `int n = (int) 3.9;` | `n == 3`, bỏ phần lẻ |
| `long` về `int` có kiểm tra | `int n = Math.toIntExact(big);` | Ném exception nếu không vừa `int` |

Các toán hạng `byte`, `short`, `char` trong phép cộng/nhân thông thường được nâng lên `int`, nên ví dụ `byte a = 10, b = 20;` rồi `byte c = a + b;` **không hợp lệ** nếu không chuyển kiểu phù hợp.

## 7. Checklist lựa chọn thực tế

1. **Đếm/chỉ số/số nguyên thông thường:** chọn `int`; nếu dự báo vượt miền, chọn `long` và nâng kiểu **trước** phép tính có thể tràn.
2. **Dữ liệu số thực đo lường/xấp xỉ:** ưu tiên `double`; chỉ chọn `float` khi có lý do về bộ nhớ, định dạng hoặc giao diện API.
3. **Số tiền hoặc giá trị cần đúng tới chữ số thập phân:** cân nhắc `long` theo đơn vị nhỏ nhất hoặc `BigDecimal` với quy tắc làm tròn rõ ràng.
4. **Cờ điều kiện:** `boolean`, không dùng `0`/`1` thay thế.
5. **Đơn vị mã ký tự:** `char`; nếu cần code point Unicode đầy đủ, dùng API String tương ứng.
6. **Phép chia, nhân, cộng trung gian:** kiểm tra **kiểu toán hạng**, không chỉ kiểu biến đích; thử các giá trị biên và trường hợp tràn.
7. **Giá trị ngoài `long`:** cân nhắc `BigInteger` nếu cần số nguyên chính xác rất lớn.

### Tự luyện

**Bài 1:** Chọn kiểu cho (a) số lần đăng nhập; (b) tổng cents của giao dịch rất lớn; (c) cân nặng đo xấp xỉ; (d) cờ đã thanh toán. Nêu ràng buộc miền và độ chính xác trước khi quyết định.

**Bài 2:** Giải thích vì sao `long x = 50_000 * 50_000;` có thể sai, rồi sửa mà **không** thay đổi ý nghĩa phép nhân.

**Bài 3:** Thử `double d = 5 / 2;` và `double d = 5.0 / 2;` trong hai trường hợp độc lập. Dự đoán `println`.

**Bài 4:** Đổi `centsPerUnit` thành `3_000_000L` trong chương trình; dự đoán tổng và đánh giá liệu `int` có còn đủ làm **kiểu kết quả** không.

**Tổng kết:** Chọn primitive theo **miền dữ liệu + độ chính xác + phép toán**, không chỉ theo độ lớn của giá trị ban đầu. Đặc biệt, lỗi tràn `int` và chia nguyên xuất hiện **trước khi gán**; còn `float`/`double` không phải giải pháp tính thập phân tuyệt đối chính xác.
