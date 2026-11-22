# Phân biệt cú pháp đúng với kết quả nghiệp vụ đúng

## 1. Vì sao một chương trình chạy được vẫn có thể sai?

Xét hai đoạn Java sau:

~~~java
int quantity = 3;
int unitPrice = 100_000;
int subtotal = quantity * unitPrice;
System.out.println(subtotal); // 300000
~~~

~~~java
int quantity = 3;
int unitPrice = 100_000;
int subtotal = quantity + unitPrice;
System.out.println(subtotal); // 100003
~~~

Cả hai đoạn đều **đúng cú pháp**, hợp lệ về kiểu và có thể biên dịch. Nhưng nếu yêu cầu là **thành tiền = số lượng × đơn giá**, chỉ đoạn đầu thực hiện đúng nghiệp vụ.

Điều quan trọng cần nhớ: **`javac` có thể kiểm tra nhiều quy tắc của ngôn ngữ Java, nhưng không tự biết người dùng muốn tính gì**. Một chương trình có thể biên dịch thành công, không ném exception, vẫn trả kết quả sai, tính sai tiền hoặc vi phạm điều kiện của bài toán.

Bài này tập trung vào cách đi từ **yêu cầu bằng lời** đến **quy tắc kiểm chứng được**, viết mã Java đúng và kiểm thử kết quả. Không cần framework hay cơ sở dữ liệu để thực hành.

## 2. Bốn lớp kiểm tra tính đúng

| Lớp kiểm tra | Câu hỏi | Ví dụ vấn đề | Cách phát hiện |
|---|---|---|---|
| **Cú pháp (syntax)** | Mã có tuân ngữ pháp Java? | Thiếu dấu `;`, ngoặc chưa đóng | `javac` báo lỗi biên dịch |
| **Ngữ nghĩa tĩnh / kiểu (static semantics)** | Biến, phép toán, kiểu trả về có hợp lệ? | `int n = "ba";` | Trình biên dịch kiểm tra kiểu |
| **Hành vi lúc chạy (runtime)** | Khi chạy có exception hoặc sự cố? | Chia số nguyên cho 0, truy cập mảng quá chỉ số | Chạy thử, test, log, stack trace |
| **Tính đúng nghiệp vụ (business correctness)** | Kết quả và hành vi có đúng quy tắc đã thống nhất? | Giảm giá sai đối tượng, miễn phí ship sai ngưỡng | Acceptance tests, ví dụ kỳ vọng, đối chiếu yêu cầu |

Cả ba điều kiện đầu đều cần thiết trong nhiều ứng dụng, nhưng **chưa đủ để bảo đảm điều kiện thứ tư**.

~~~mermaid
flowchart TD
    A["Yêu cầu nghiệp vụ"] --> B["Quy tắc có thể kiểm chứng"]
    B --> C["Viết mã Java"]
    C --> D{"Biên dịch thành công?"}
    D -->|"Không"| E["Sửa cú pháp / kiểu"]
    E --> C
    D -->|"Có"| F["Thực thi và kiểm thử"]
    F --> G{"Kết quả khớp quy tắc?"}
    G -->|"Không"| H["Tìm lỗi logic / giả định / dữ liệu"]
    H --> B
    G -->|"Có"| I["Đạt các ca đã kiểm; tiếp tục review và kiểm thử thêm"]
~~~

Ngay cả khi một bộ test đều xanh, điều đó chỉ chứng minh chương trình **đạt các trường hợp đã kiểm**, không chứng minh mọi đầu vào và mọi môi trường đều đúng.

## 3. Biến yêu cầu bằng lời thành một hợp đồng rõ ràng

Giả sử cửa hàng bán hàng hóa theo **đồng Việt Nam nguyên đơn vị** và đưa ra chính sách sau:

- **BR-01 – Dữ liệu hợp lệ:** đơn giá phải **lớn hơn 0**; số lượng phải **lớn hơn 0**.
- **BR-02 – Tiền hàng:** `subtotal = unitPrice × quantity`.
- **BR-03 – Giảm giá:** khách là **thành viên đang hoạt động** và tiền hàng ban đầu **từ 200.000 đồng trở lên** được giảm **10% tiền hàng**. Các trường hợp khác không giảm.
- **BR-04 – Làm tròn:** phần tiền giảm được **lấy phần nguyên theo đơn vị đồng** (làm tròn xuống); đầu vào và kết quả đều không âm.
- **BR-05 – Vận chuyển:** nếu **tiền hàng sau giảm giá** từ **300.000 đồng trở lên**, phí vận chuyển bằng 0; nếu thấp hơn, phí là **30.000 đồng**.
- **BR-06 – Tổng thanh toán:** `payable = subtotal − discount + shipping`.
- **BR-07 – Quá giới hạn số:** nếu phép tính vượt miền `long`, phải báo lỗi thay vì âm thầm tạo số tiền sai.

**Điểm dễ nhầm:** ngưỡng giảm giá xét trên `subtotal` **trước giảm**, nhưng ngưỡng miễn phí vận chuyển xét trên số tiền **sau giảm**. Cả hai ngưỡng đều dùng “**từ ... trở lên**”, nghĩa là dùng `>=`, không phải `>`.

Quy tắc làm tròn là một phần của yêu cầu: với giảm giá 10% và tiền nguyên đồng không âm, `subtotal / 10` (chia nguyên) cho phần tiền giảm đã làm tròn xuống. Nếu chính sách đổi sang 7,5% hoặc tính thuế, công thức và quy tắc làm tròn phải được xác nhận lại.

### Bảng dự đoán trước khi viết mã

| Tiền hàng | Thành viên hoạt động? | Giảm giá | Sau giảm | Ship | Tổng trả |
|---:|---|---:|---:|---:|---:|
| 199.999 | Có | 0 | 199.999 | 30.000 | 229.999 |
| 200.000 | Có | 20.000 | 180.000 | 30.000 | 210.000 |
| 300.000 | Có | 30.000 | 270.000 | 30.000 | 300.000 |
| 300.000 | Không | 0 | 300.000 | 0 | 300.000 |
| 400.000 | Có | 40.000 | 360.000 | 0 | 360.000 |

Bảng này là **test oracle**: kết quả mong đợi được suy ra từ quy tắc trước khi xem chương trình trả về gì.

## 4. Một đoạn Java hợp lệ nhưng vi phạm nghiệp vụ

Đoạn sau có cú pháp hợp lệ, nhưng tính phí vận chuyển theo tiền hàng **trước** giảm:

~~~java
long subtotal = 300_000L;
boolean activeMember = true;

long discount = activeMember && subtotal >= 200_000L
        ? subtotal / 10
        : 0L;

long shipping = subtotal >= 300_000L ? 0L : 30_000L; // SAI QUY TẮC
long payable = subtotal - discount + shipping;

System.out.println(payable); // 270000
~~~

Theo BR-05, đúng ra phải xét `subtotal - discount = 270000`, vì vậy phí vận chuyển là `30000` và tổng đúng là **300000**. `javac` không thể biết quy tắc BR-05 từ một đoạn mã.

Sửa tối thiểu:

~~~java
long afterDiscount = subtotal - discount;
long shipping = afterDiscount >= 300_000L ? 0L : 30_000L;
long payable = afterDiscount + shipping;
System.out.println(payable); // 300000
~~~

**Cảnh báo:** các snippet trên tập trung minh họa bug logic; khi triển khai hoàn chỉnh vẫn cần bảo vệ đầu vào, kiểm tra tràn số và kiểm thử ngưỡng.

## 5. Chương trình Java 17 độc lập và có thể chạy

Tạo tệp chính xác tên **`BusinessCorrectnessDemo.java`**:

~~~java
public final class BusinessCorrectnessDemo {
    private static final long DISCOUNT_MIN = 200_000L;
    private static final long FREE_SHIPPING_MIN = 300_000L;
    private static final long SHIPPING_FEE = 30_000L;

    private BusinessCorrectnessDemo() {}

    // Record chỉ lưu kết quả; toàn bộ số tiền tính theo đồng nguyên.
    record Quote(long subtotal, long discount,
                 long shipping, long payable) {}

    static Quote calculate(long unitPrice, int quantity,
                           boolean activeMember) {
        if (unitPrice <= 0) {
            throw new IllegalArgumentException("Don gia phai duong");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("So luong phai duong");
        }

        // Phát hiện tràn long trước khi có số tiền hàng.
        long subtotal = Math.multiplyExact(unitPrice, (long) quantity);

        // 10% và làm tròn xuống đồng, chỉ khi đủ cả hai điều kiện.
        long discount = activeMember && subtotal >= DISCOUNT_MIN
                ? subtotal / 10
                : 0L;

        long afterDiscount = Math.subtractExact(subtotal, discount);
        long shipping = afterDiscount >= FREE_SHIPPING_MIN
                ? 0L
                : SHIPPING_FEE;
        long payable = Math.addExact(afterDiscount, shipping);

        return new Quote(subtotal, discount, shipping, payable);
    }

    static void expect(String label, long unitPrice, int quantity,
                       boolean member, long expectedSubtotal,
                       long expectedDiscount, long expectedShipping,
                       long expectedPayable) {
        Quote q = calculate(unitPrice, quantity, member);
        if (q.subtotal() != expectedSubtotal
                || q.discount() != expectedDiscount
                || q.shipping() != expectedShipping
                || q.payable() != expectedPayable) {
            throw new AssertionError(
                    label + ": ket qua khong dung, actual=" + q);
        }
        System.out.println(label + " -> " + q.payable() + " VND");
    }

    static void checkInvalidInput() {
        boolean invalidPrice = false;
        boolean invalidQuantity = false;
        try {
            calculate(0, 1, false);
        } catch (IllegalArgumentException expected) {
            invalidPrice = true;
        }
        try {
            calculate(100, 0, true);
        } catch (IllegalArgumentException expected) {
            invalidQuantity = true;
        }
        if (!invalidPrice || !invalidQuantity) {
            throw new AssertionError("Input invalid was accepted");
        }
        System.out.println("Invalid input: PASS");
    }

    static void checkOverflow() {
        boolean overflowDetected = false;
        try {
            calculate(Long.MAX_VALUE, 2, true);
        } catch (ArithmeticException expected) {
            overflowDetected = true;
        }
        if (!overflowDetected) {
            throw new AssertionError("Overflow was not detected");
        }
        System.out.println("Overflow: PASS");
    }

    public static void main(String[] args) {
        expect("A", 100_000, 3, true,
                300_000, 30_000, 30_000, 300_000);
        expect("B", 100_000, 3, false,
                300_000, 0, 0, 300_000);
        expect("C", 199_999, 1, true,
                199_999, 0, 30_000, 229_999);
        expect("D", 200_000, 1, true,
                200_000, 20_000, 30_000, 210_000);
        expect("E", 100_000, 4, true,
                400_000, 40_000, 0, 360_000);
        checkInvalidInput();
        checkOverflow();
        System.out.println("ALL CASES PASS");
    }
}
~~~

Chương trình cần **JDK 17 trở lên** do dùng `record`. Mở terminal trong thư mục chứa tệp và chạy:

~~~bash
javac --release 17 -encoding UTF-8 BusinessCorrectnessDemo.java
java BusinessCorrectnessDemo
~~~

**Đầu ra kỳ vọng:**

~~~text
A -> 300000 VND
B -> 300000 VND
C -> 229999 VND
D -> 210000 VND
E -> 360000 VND
Invalid input: PASS
Overflow: PASS
ALL CASES PASS
~~~

Mã dùng `if`, `&&`, toán tử điều kiện `?:`, các phép toán số nguyên và method để kiểm chứng quy tắc. Các câu lệnh `throw` ở đầu vào chỉ từ chối dữ liệu sai; chúng không thay cho việc kiểm thử công thức tiền hàng.

**Lưu ý về kiểm thử:** phương thức `expect` tự ném `AssertionError` khi phát hiện sai, nên không phụ thuộc vào cờ `-ea`. Các kết quả trong bài là **kỳ vọng để người học tự chạy đối chiếu**, không phải báo cáo đã thực thi code trên máy của người học.

## 6. Đọc mã đúng theo thứ tự nghiệp vụ

Hãy theo dấu trường hợp `unitPrice = 100000`, `quantity = 3`, `activeMember = true`:

| Bước | Phép tính/điều kiện | Kết quả |
|---|---|---:|
| 1 | Kiểm tra đơn giá và số lượng dương | Hợp lệ |
| 2 | `100000 × 3` | `subtotal = 300000` |
| 3 | Thành viên active và `300000 >= 200000` | Đủ điều kiện |
| 4 | `300000 / 10` | `discount = 30000` |
| 5 | `300000 - 30000` | `afterDiscount = 270000` |
| 6 | `270000 >= 300000` | Sai |
| 7 | Cộng phí ship `30000` | `payable = 300000` |

Ở bước 6, nếu ai đó vô tình dùng `subtotal` thay vì `afterDiscount`, chương trình vẫn đúng cú pháp và đúng kiểu, nhưng sai BR-05.

**Nguyên tắc quan trọng:** đặt tên biến thể hiện đúng **ý nghĩa và thời điểm** của dữ liệu. `subtotal` và `afterDiscount` đều là `long`, nhưng không thể thay thế nhau trong mọi công thức chỉ vì chúng cùng kiểu Java.

## 7. Kiểm thử ngưỡng và edge cases

Các lỗi nghiệp vụ thường xuất hiện tại **ranh giới điều kiện**, trong trường hợp dữ liệu không hợp lệ hoặc lúc các điều kiện kết hợp.

| Tình huống | Dữ liệu kiểm thử | Kết quả cần xác nhận |
|---|---|---|
| Ngay dưới ngưỡng giảm giá | `subtotal = 199999`, member=true | Không giảm |
| Đúng ngưỡng giảm giá | `subtotal = 200000`, member=true | Có giảm 10% |
| Cùng mức tiền nhưng không là thành viên | `subtotal = 200000`, member=false | Không giảm |
| Sau giảm ngay dưới ngưỡng ship | `subtotal = 300000`, member=true | Sau giảm 270000, phí 30000 |
| Đúng ngưỡng ship | `subtotal = 300000`, member=false | Ship 0 |
| Tổng sau giảm vượt ngưỡng ship | `subtotal = 400000`, member=true | Ship 0 |
| Số lượng 0 hoặc âm | `quantity <= 0` | Từ chối đầu vào |
| Đơn giá 0 hoặc âm | `unitPrice <= 0` | Từ chối đầu vào |
| Tràn phép nhân | `unitPrice = Long.MAX_VALUE`, `quantity = 2` | `ArithmeticException` |
| Tiền hàng 200.001 và member=true | `subtotal = 200001` | Giảm 20000 đồng (lấy phần nguyên) |

Khi kiểm thử ngưỡng `T`, thường chọn **`T - 1`, `T`, `T + 1`** theo đơn vị có ý nghĩa. Với BR-05, nhớ tạo dữ liệu sao cho **số tiền sau giảm** nằm ở những điểm này; chỉ kiểm thử số tiền trước giảm có thể bỏ lọt bug.

### Thuộc tính có thể kiểm thử thêm

Với đầu vào hợp lệ và không tràn số, mọi kết quả phải thỏa:

- `subtotal > 0`.
- `0 <= discount <= subtotal`.
- `shipping == 0` hoặc `shipping == 30000`.
- `payable == subtotal - discount + shipping`.
- Nếu `activeMember == false` thì `discount == 0`.
- Nếu `afterDiscount >= 300000` thì `shipping == 0`, nếu nhỏ hơn thì `shipping == 30000`.

Các thuộc tính này rất hữu ích để rà soát nhiều ca; nhưng một implementation sai có thể vẫn giữ vài thuộc tính, nên phải kết hợp với **ví dụ kết quả cụ thể được xác nhận từ nghiệp vụ**.

## 8. Những bẫy Java khiến kết quả nghiệp vụ sai

### 8.1. Chia nguyên và làm tròn không rõ ràng

~~~java
int percent = 15;
int amount = 101;
int discount = amount * percent / 100; // 15, phần lẻ bị bỏ
~~~

Công thức có thể đúng **hoặc sai** tùy quy tắc làm tròn được yêu cầu. Với tiền, phải thống nhất đơn vị, phép chia, thứ tự làm tròn và chính sách rounding. `double` có thể không biểu diễn chính xác nhiều số thập phân; số nguyên theo đơn vị nhỏ nhất hoặc `BigDecimal` thường dễ kiểm soát hơn.

### 8.2. Tràn số vẫn đúng kiểu `long`

~~~java
long price = Long.MAX_VALUE;
long total = price * 2; // Tràn long nếu nhân thông thường
~~~

Java không tự ném exception khi mọi phép toán nguyên thông thường bị tràn. Dùng `Math.multiplyExact`/`Math.addExact` hoặc giới hạn miền dữ liệu rõ ràng khi tràn không được phép.

### 8.3. Nhầm `>` với `>=`

~~~java
boolean eligible = subtotal > 200_000;  // Sai khi subtotal đúng 200000
boolean correct = subtotal >= 200_000; // Đúng với "từ 200000"
~~~

Một ký tự khác nhau có thể làm sai hàng nghìn giao dịch sát ngưỡng.

### 8.4. `==` không kiểm tra nội dung hai chuỗi

~~~java
String role = new String("MEMBER");
System.out.println(role == "MEMBER");      // false
System.out.println("MEMBER".equals(role));  // true
~~~

Nếu điều kiện giảm giá dựa trên role lấy từ input, dùng `==` với `String` có thể làm sai logic dù biên dịch và chạy bình thường. Gọi `"MEMBER".equals(role)` cũng an toàn khi `role == null`.

### 8.5. `&&` và `&` không hoàn toàn như nhau

~~~java
String memberId = null;
boolean valid = memberId != null && !memberId.isBlank(); // false
~~~

`&&` ngắn mạch: khi vế trái sai, vế phải không được đánh giá. Đổi sang `&` trên boolean sẽ đánh giá cả hai vế, ở đây gây `NullPointerException`.

### 8.6. Điều kiện đúng nhưng kiểm tra sai thời điểm

Quy tắc “ship miễn phí từ 300.000 đồng **sau giảm**” cần dùng `afterDiscount`. Dù `subtotal`, `afterDiscount` và `payable` cùng kiểu `long`, chúng đại diện cho các giai đoạn khác nhau. Tên biến và thứ tự phép tính phải phản ánh chính sách.

### 8.7. Kiểm tra đầu vào không thay cho kiểm tra kết quả

Đơn giá và số lượng đều dương **không bảo đảm** phép nhân an toàn khỏi tràn. Ngược lại, có tổng tiền tính được cũng không chứng minh người mua đủ điều kiện giảm giá. Cần kiểm tra **cả điều kiện đầu vào, ranh giới số học và kết quả theo nghiệp vụ**.

## 9. Quy trình tìm lỗi khi test thất bại

Khi kết quả không khớp yêu cầu, đừng sửa ngẫu nhiên cho tới khi test xanh. Thử lần lượt:

1. **Đọc lại câu yêu cầu**: xác định ngưỡng, dấu bằng, đối tượng được áp dụng, thời điểm tính, đơn vị và cách làm tròn.
2. **Viết expected result bằng tay** từ quy tắc. Với bài toán có nhiều điều kiện, lập bảng quyết định.
3. **Tái hiện bằng ca nhỏ nhất**: ví dụ `subtotal=300000`, member=true đủ để phát hiện nhầm ngưỡng phí ship.
4. **Theo dõi giá trị trung gian**: `subtotal`, `discount`, `afterDiscount`, `shipping`, `payable`.
5. **Kiểm tra toán tử, kiểu và thứ tự tính**: đặc biệt `>=`, `&&`, chia nguyên và overflow.
6. **Sửa đúng quy tắc bị vi phạm**, thêm test hồi quy cho ca vừa tìm được và chạy lại các ca cũ.

Một lỗi có thể đến từ chính **đặc tả chưa rõ**. Nếu yêu cầu không nói giảm giá làm tròn như thế nào, người lập trình không nên tự giả định rồi xem kết quả là đúng; cần làm rõ với người phụ trách nghiệp vụ.

## 10. Bộ công cụ kiểm chứng: mỗi công cụ trả lời một câu hỏi

| Hoạt động | Xác minh được | Không tự bảo đảm |
|---|---|---|
| `javac` | Cú pháp, kiểu, tên, điều kiện biên dịch | Công thức tiền đã đúng |
| Chạy chương trình | Quan sát hành vi ở dữ liệu đã chạy | Đúng ở mọi dữ liệu khác |
| Unit test / assertion rõ ràng | Một quy tắc cụ thể với input và expected | Bao phủ toàn bộ nghiệp vụ |
| Boundary testing | Các trường hợp ngay dưới, đúng và trên ngưỡng | Mọi quy tắc tổ hợp |
| Code review đối chiếu BR | Rà lại đơn vị, công thức, nhánh, ngoại lệ | Tự thay cho chạy test |
| Static analysis / lint | Một số mẫu lỗi và vấn đề chất lượng | Hiểu hết quy định kinh doanh |
| Integration/acceptance test | Các thành phần phối hợp và kịch bản thực tế | Bao phủ vô hạn trạng thái hệ thống |

Dùng `assert` của ngôn ngữ Java trong chương trình thông thường cần nhớ assertions có thể **bị vô hiệu hóa** nếu không bật `-ea`. Vì vậy ví dụ dùng `AssertionError` trực tiếp trong phương thức kiểm tra để luôn phát hiện kết quả không khớp khi chạy demo. Trong dự án thực tế, nên dùng framework kiểm thử với assertions được quản lý rõ ràng.

## 11. Bài tập thực hành kèm đáp án

### Bài A — tìm lỗi nghiệp vụ trong mã hợp lệ

~~~java
long subtotal = 300_000;
long discount = 30_000;
long shipping = subtotal >= 300_000 ? 0 : 30_000;
long payable = subtotal - discount + shipping;
~~~

**Hỏi:** mã có biên dịch được không (khi nằm trong method hợp lệ)? Kết quả có đúng BR-05 không?

**Đáp án:** mã đúng cú pháp/kiểu; `payable=270000`, nhưng BR-05 yêu cầu phí ship dựa trên `270000` sau giảm, nên tổng đúng là `300000`. Sửa điều kiện thành `subtotal - discount >= 300_000` hoặc đặt tên `afterDiscount` rồi dùng biến ấy.

### Bài B — xét ranh giới

Cùng một khách active, hãy tính kết quả với tiền hàng `199999`, `200000`, `200001`.

**Đáp án:** lần lượt:

- 199999: discount 0, ship 30000, payable **229999**.
- 200000: discount 20000, sau giảm 180000, ship 30000, payable **210000**.
- 200001: discount 20000 sau làm tròn xuống, sau giảm 180001, ship 30000, payable **210001**.

### Bài C — phát hiện kiểm thử thiếu

Nhóm chỉ thử `subtotal=400000` và thấy thành viên được giảm giá, miễn ship, tổng đúng. Liệu đã chứng minh BR-05 chưa?

**Đáp án:** chưa. Cần ca `subtotal=300000, activeMember=true`: sau giảm còn 270000, do đó **không được miễn ship**. Đây là ca bắt lỗi “ship tính trước giảm”.

### Bài D — thử dữ liệu sai và tràn số

Chạy `calculate(0,1,false)`, `calculate(100,0,true)`, `calculate(Long.MAX_VALUE,2,true)`.

**Đáp án:** hai ca đầu ném `IllegalArgumentException` vì vi phạm BR-01; ca cuối ném `ArithmeticException` do `Math.multiplyExact` phát hiện tràn. Không được thay lỗi bằng giá âm rồi tiếp tục tính phí.

### Bài E — thay đổi chính sách

Chủ cửa hàng đổi điều kiện: “miễn phí vận chuyển từ 300.000 đồng **trước giảm**”. Cần sửa gì?

**Đáp án:** trong BR-05 mới, ngưỡng dùng `subtotal` thay cho `afterDiscount`. Phải sửa code, expected ở các ca chịu ảnh hưởng (đặc biệt tiền hàng 300000 có giảm giá), và lưu sự thay đổi của đặc tả. Một bản sửa theo BR mới có thể **cố tình khác** kết quả của bộ test cũ: test cũng phải được cập nhật có căn cứ, không sửa ngầm để làm xanh.

## 12. Checklist nghiệm thu và ghi nhớ

- [ ] Phân biệt được **compile-time error**, **runtime error** và **lỗi logic nghiệp vụ**.
- [ ] Viết được quy tắc kinh doanh thành điều kiện đầu vào, công thức và kết quả kỳ vọng.
- [ ] Biết xác định giá trị nào là trước/sau một bước xử lý.
- [ ] Kiểm tra đúng các ngưỡng `<`, `<=`, `>`, `>=` và tổ hợp điều kiện.
- [ ] Dùng loại số và đơn vị tiền phù hợp; xác định quy tắc làm tròn.
- [ ] Bảo vệ đầu vào sai, overflow và nhánh có thể gây exception.
- [ ] Biên dịch và chạy `BusinessCorrectnessDemo.java`, đối chiếu đầu ra.
- [ ] Có các ca **dưới ngưỡng, đúng ngưỡng, trên ngưỡng**, trường hợp thành viên và không thành viên.
- [ ] Có test hồi quy chứng minh một bug nghiệp vụ đã sửa không xuất hiện trở lại.
- [ ] Không xem “`javac` không báo lỗi” hoặc “chạy không crash” là bằng chứng đủ về tính đúng nghiệp vụ.

**Kết luận:** Java quyết định **mã có hợp lệ theo ngôn ngữ hay không**; còn các quy tắc nghiệp vụ xác định **kết quả nào mới là đúng**. Muốn có phần mềm đáng tin cậy, phải nối hai phía bằng ví dụ đầu vào/đầu ra, phép tính có ý nghĩa rõ ràng, xử lý edge cases và kiểm thử đối chiếu yêu cầu.