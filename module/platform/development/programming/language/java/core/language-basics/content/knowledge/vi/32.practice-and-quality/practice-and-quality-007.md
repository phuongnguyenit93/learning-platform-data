# Thực hành chương trình tính tiền với điều kiện và vòng lặp (Java 17+)

## 1. Bài toán và mục tiêu

Xây dựng một chương trình Java chạy trên console để **tính tiền giỏ hàng có nhiều mặt hàng**. Người dùng lần lượt nhập **đơn giá** và **số lượng**. Chương trình cộng thành tiền từng mặt hàng vào tạm tính, tiếp tục hỏi mặt hàng kế tiếp và dừng khi người dùng nhập **đơn giá bằng `0`**. Cuối cùng, dùng điều kiện để tính chiết khấu và số tiền phải trả.

Đây là bài thực hành kết hợp các kiến thức Java core: biến và kiểu dữ liệu, phép toán, `if / else if / else`, vòng lặp `while`, `break`, `Scanner`, kiểm tra dữ liệu, phương thức và `System.out.println()`.

**Các quy tắc cụ thể của chương trình mẫu:**

- Đơn giá là **số nguyên VND**. Nhập `0` để kết thúc; còn lại phải trong khoảng **1–1.000.000 VND**.
- Số lượng mỗi mặt hàng là số nguyên từ **1 đến 100**.
- Cho phép tối đa **100 dòng mặt hàng** trong một hóa đơn. Một dòng có thể đại diện nhiều sản phẩm giống nhau thông qua số lượng.
- Thành tiền một dòng = đơn giá × số lượng. Tạm tính = tổng thành tiền các dòng.
- Nếu tạm tính **từ 500.000 VND trở lên**, giảm **10%**; nếu **từ 200.000 VND đến dưới 500.000 VND**, giảm **5%**; dưới 200.000 VND **không giảm**.
- Tiền giảm = `subtotal * discountPercent / 100` bằng phép toán số nguyên, tức **lấy phần nguyên VND**. Tiền thanh toán = tạm tính − tiền giảm.
- Dữ liệu sai, hết input bất ngờ hoặc vượt giới hạn dòng mặt hàng sẽ được báo lỗi và **không in một hóa đơn hoàn chỉnh**.

Các ngưỡng, giới hạn và cách làm tròn trên là **yêu cầu giả định của bài thực hành**, không phải quy tắc bán hàng chung. Khi làm dự án thật, cần thống nhất trước cách tính thuế, phí vận chuyển, mã giảm giá, làm tròn và chính sách hủy đơn.

## 2. Phân tích Input – Process – Output

| Thành phần | Dữ liệu hoặc công việc | Kiểu Java gợi ý |
| --- | --- | --- |
| **Input** | Đơn giá từng dòng; `0` là tín hiệu kết thúc | `long` |
| **Input** | Số lượng tương ứng từng dòng | `long` hoặc `int` |
| **Process** | Kiểm tra giá, số lượng, số dòng mặt hàng | `if` và phép so sánh |
| **Process** | Tính `lineTotal = unitPrice * quantity` | `long` |
| **Process** | Cộng dồn `subtotal += lineTotal` | `long` |
| **Process** | Chọn mức giảm 0%, 5% hoặc 10% | `if / else if / else` |
| **Process** | Tính `discount` và `total` | `long` |
| **Output** | Thành tiền từng dòng, tạm tính, mức giảm và tổng thanh toán | `println` |

Dùng `long` cho số tiền VND nguyên để tránh sai số nhị phân của `double` và có miền giá trị lớn hơn `int`. Trong giới hạn của bài này, hóa đơn tối đa là `100 × 1_000_000 × 100 = 10_000_000_000` VND, vượt giới hạn của `int` nhưng nằm an toàn trong `long`.

Vì mức giảm tối đa là 10%, phép nhân `subtotal * discountPercent` cũng không tràn `long` với những giới hạn đã đặt. Nếu bỏ giới hạn hoặc xử lý giao dịch lớn, phải thiết kế thêm kiểm tra tràn số hoặc dùng mô hình tiền tệ phù hợp.

## 3. Thuật toán trước khi viết Java

```text
subtotal = 0
itemCount = 0

LẶP:
    Đọc unitPrice
    NẾU unitPrice == 0:
        THOÁT vòng lặp
    NẾU unitPrice không trong [1, 1_000_000]:
        BÁO LỖI và dừng chương trình
    NẾU đã có 100 dòng mặt hàng:
        BÁO LỖI và dừng chương trình

    Đọc quantity
    NẾU quantity không trong [1, 100]:
        BÁO LỖI và dừng chương trình

    lineTotal = unitPrice * quantity
    subtotal = subtotal + lineTotal
    itemCount = itemCount + 1
    In thành tiền dòng này

NẾU subtotal >= 500_000:
    discountPercent = 10
NGƯỢC LẠI NẾU subtotal >= 200_000:
    discountPercent = 5
NGƯỢC LẠI:
    discountPercent = 0

discount = subtotal * discountPercent / 100
total = subtotal - discount

In itemCount, subtotal, discountPercent, discount và total
```

Tại đây, `while (true)` là lựa chọn hợp lý vì chưa biết trước có bao nhiêu mặt hàng. **`break` chỉ được thực hiện khi đơn giá bằng 0**. Các trường hợp input không hợp lệ không được hiểu là yêu cầu kết thúc mua hàng; chúng được xử lý bằng thông báo lỗi riêng.

Bất biến của vòng lặp sau mỗi lượt hợp lệ: `itemCount` bằng số dòng đã nhập thành công và `subtotal` bằng tổng `unitPrice * quantity` của chính các dòng đó. Đây là cơ sở để tự kiểm tra logic cộng dồn.

## 4. Chương trình đầy đủ: InvoiceApp.java

Lưu nguyên chương trình sau trong tệp **`InvoiceApp.java`**:

```java
import java.util.Scanner;

public class InvoiceApp {
    private static final long MAX_UNIT_PRICE = 1_000_000L;
    private static final long MAX_QUANTITY = 100L;
    private static final int MAX_LINE_ITEMS = 100;

    private static long readLong(Scanner scanner, String prompt) {
        System.out.println(prompt);

        if (!scanner.hasNextLine()) {
            throw new IllegalArgumentException("missing input");
        }

        String input = scanner.nextLine().strip();
        try {
            return Long.parseLong(input);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("expected an integer", ex);
        }
    }

    public static void main(String[] args) {
        try (Scanner scanner = new Scanner(System.in)) {
            try {
                long subtotal = 0L;
                int itemCount = 0;

                while (true) {
                    long unitPrice = readLong(
                            scanner, "Unit price VND (0 to finish):");

                    if (unitPrice == 0L) {
                        break;
                    }
                    if (unitPrice < 0L || unitPrice > MAX_UNIT_PRICE) {
                        throw new IllegalArgumentException(
                                "unit price must be from 1 to 1000000");
                    }
                    if (itemCount >= MAX_LINE_ITEMS) {
                        throw new IllegalArgumentException(
                                "too many line items");
                    }

                    long quantity = readLong(scanner, "Quantity:");
                    if (quantity < 1L || quantity > MAX_QUANTITY) {
                        throw new IllegalArgumentException(
                                "quantity must be from 1 to 100");
                    }

                    long lineTotal = unitPrice * quantity;
                    subtotal += lineTotal;
                    itemCount++;

                    System.out.println("Item " + itemCount
                            + ": " + lineTotal + " VND");
                }

                int discountPercent;
                if (subtotal >= 500_000L) {
                    discountPercent = 10;
                } else if (subtotal >= 200_000L) {
                    discountPercent = 5;
                } else {
                    discountPercent = 0;
                }

                long discount = subtotal * discountPercent / 100L;
                long total = subtotal - discount;

                System.out.println("Items: " + itemCount);
                System.out.println("Subtotal: " + subtotal + " VND");
                System.out.println("Discount: " + discountPercent
                        + "% = " + discount + " VND");
                System.out.println("Total: " + total + " VND");
            } catch (IllegalArgumentException ex) {
                System.out.println("Error: " + ex.getMessage());
            }
        }
    }
}
```

### Vai trò của từng khối

**`readLong(...)` — đọc và kiểm tra định dạng.** Phương thức in lời nhắc, đọc **cả dòng** bằng `nextLine()`, loại khoảng trắng ở hai đầu bằng `strip()`, rồi chuyển bằng `Long.parseLong`. Đọc theo dòng tránh lỗi `nextLine()` nhận phần xuống dòng còn lại sau `nextInt()`. Nếu đã EOF, phương thức báo `missing input`; nếu không parse được số nguyên, báo `expected an integer`.

**`while (true)` — duyệt các mặt hàng.** Vì không biết trước số lần lặp, chương trình tiếp tục cho tới khi thấy giá `0`. Câu `break` thoát **vòng lặp gần nhất**, rồi thực thi khối tính giảm giá ở phía sau. Không nhầm `break` với `return`: `return` khỏi `main` sẽ không chạy phần tổng kết.

**`if` — kiểm tra từng input.** Đơn giá và số lượng có giới hạn độc lập. Giá âm hoặc quá lớn, số lượng 0 hoặc quá lớn đều không được tính vào hóa đơn. Giá `0` được kiểm tra **trước** kiểm tra khoảng để làm tín hiệu kết thúc.

**Phép cộng dồn — giữ đúng trạng thái.** Tính thành tiền từng dòng, cộng vào `subtotal`, sau đó tăng `itemCount` đúng một lần cho mỗi dòng hợp lệ. Tránh khai báo `subtotal = 0` **bên trong** vòng lặp, vì như vậy tổng sẽ bị đặt lại ở mỗi lượt.

**`if / else if / else` — chọn đúng một mức giảm.** Mốc cao nhất được kiểm tra trước (`>= 500_000`), kế tiếp là `>= 200_000`, cuối cùng 0%. Nếu dùng hai `if` độc lập và áp dụng chiết khấu hai lần, đơn hàng đạt 500.000 VND có thể bị tính sai.

**Kiểu `long` — số tiền nguyên VND.** Chương trình không thêm dấu phân nhóm hàng nghìn để stdout nhất quán giữa các môi trường. Có thể dùng `printf` với `Locale` phù hợp nếu yêu cầu trình bày tiền có dấu phân cách.

## 5. Biên dịch và chạy với JDK 17+

Tại thư mục chứa `InvoiceApp.java`, tạo thư mục `out` nếu chưa tồn tại:

```sh
mkdir out
javac -encoding UTF-8 --release 17 -d out InvoiceApp.java
java -cp out InvoiceApp
```

Lệnh `javac` tạo `out/InvoiceApp.class`. Lệnh `java` chạy chương trình và chờ người dùng nhập lần lượt. Thử nhập các dòng sau, nhấn Enter sau mỗi giá trị:

```text
100000
2
150000
1
0
```

**Stdout chính xác do Java in** (không tính phần terminal tự hiển thị lại phím người dùng gõ):

```text
Unit price VND (0 to finish):
Quantity:
Item 1: 200000 VND
Unit price VND (0 to finish):
Quantity:
Item 2: 150000 VND
Unit price VND (0 to finish):
Items: 2
Subtotal: 350000 VND
Discount: 5% = 17500 VND
Total: 332500 VND
```

Kiểm tra bằng tay:

- Mặt hàng 1: `100000 × 2 = 200000`.
- Mặt hàng 2: `150000 × 1 = 150000`.
- Tạm tính: `200000 + 150000 = 350000`.
- `350000` nằm trong khoảng từ 200.000 đến dưới 500.000 VND nên giảm `5%`.
- Tiền giảm: `350000 × 5 / 100 = 17500`.
- Tổng thanh toán: `350000 - 17500 = 332500`.

**Chạy từ file input để kiểm thử lặp lại:** tạo `sample.txt` chứa đúng năm dòng input ở trên, rồi chạy bằng cú pháp phù hợp:

- **Linux/macOS hoặc Windows CMD:** `java -cp out InvoiceApp < sample.txt`.
- **Windows PowerShell:** `Get-Content -LiteralPath sample.txt | java -cp out InvoiceApp`.

Không cần sửa Java để đổi từ nhập bàn phím sang đọc từ file/pipe: cả hai đều cung cấp dữ liệu qua `System.in`.

## 6. Theo dõi vòng lặp bằng bảng trace

Trước khi chạy, có thể lập bảng theo từng vòng lặp để chứng minh việc cộng dồn:

| Lượt | Đơn giá | Số lượng | Thành tiền dòng | Tạm tính sau lượt | Số dòng sau lượt |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 100.000 | 2 | 200.000 | 200.000 | 1 |
| 2 | 150.000 | 1 | 150.000 | 350.000 | 2 |
| 3 | 0 | Không hỏi | Không thêm | 350.000 | 2 |

Ở lượt 3, giá `0` khiến `break`, nên chương trình **không hỏi số lượng** và không thêm dòng mặt hàng. Đây cũng là cách phát hiện lỗi thường gặp: nếu code vẫn hỏi số lượng sau khi nhập `0`, câu `break` đặt sai vị trí.

Sau vòng lặp, các biến `subtotal`, `itemCount` vẫn giữ giá trị đã tích lũy. Biến `lineTotal` chỉ phục vụ lượt hiện tại; `subtotal` mới là tổng của mọi lượt.

## 7. Kiểm tra các mốc điều kiện và trường hợp biên

Với chính sách của bài thực hành, bảng sau thể hiện các mốc quan trọng:

| Tạm tính | Mức giảm | Tiền giảm theo phép chia nguyên | Phải trả |
| ---: | ---: | ---: | ---: |
| 0 VND | 0% | 0 | 0 |
| 199.999 VND | 0% | 0 | 199.999 |
| 200.000 VND | 5% | 10.000 | 190.000 |
| 499.999 VND | 5% | 24.999 | 475.000 |
| 500.000 VND | 10% | 50.000 | 450.000 |
| 1.000.000 VND | 10% | 100.000 | 900.000 |

Ở mốc 499.999 VND, `499999 * 5 / 100` bằng `24999` theo chia nguyên, **không** làm tròn lên thành 25.000. Cần phân biệt cách làm tròn với độ chính xác của phép tính; nếu thay quy tắc nghiệp vụ thành làm tròn tới VND gần nhất, phần Process và kiểm thử phải được thay đổi đồng bộ.

### Trường hợp không mua mặt hàng nào

Nếu giá đầu tiên là `0`, không có dòng mặt hàng:

```text
0
```

**Stdout chính xác:**

```text
Unit price VND (0 to finish):
Items: 0
Subtotal: 0 VND
Discount: 0% = 0 VND
Total: 0 VND
```

Đây là một quyết định trong hợp đồng mẫu: cho phép hóa đơn rỗng có tổng 0. Nếu nghiệp vụ không cho phép, hãy kiểm tra `itemCount == 0` sau vòng lặp và báo lỗi thay vì in hóa đơn.

### Trường hợp đạt đúng mốc 500.000 VND

Nhập:

```text
500000
1
0
```

**Stdout chính xác:**

```text
Unit price VND (0 to finish):
Quantity:
Item 1: 500000 VND
Unit price VND (0 to finish):
Items: 1
Subtotal: 500000 VND
Discount: 10% = 50000 VND
Total: 450000 VND
```

Trường hợp này kiểm tra dấu `>=` tại mốc giảm cao: nếu viết nhầm `subtotal > 500_000`, hóa đơn đúng 500.000 VND sẽ rơi vào mức 5%.

## 8. Input sai và phản hồi của chương trình

Dữ liệu nhập từ console không nên được giả định luôn hợp lệ. Trong chương trình mẫu:

| Input/tình huống | Hành vi |
| --- | --- |
| Gõ `abc` khi hỏi đơn giá hoặc số lượng | `Error: expected an integer` |
| Đơn giá `-1` hoặc `1000001` | `Error: unit price must be from 1 to 1000000` |
| Số lượng `0`, `-3`, `101` | `Error: quantity must be from 1 to 100` |
| EOF khi đang cần đọc giá hoặc số lượng | `Error: missing input` |
| Sau 100 dòng mặt hàng hợp lệ lại nhập một giá dương để thêm dòng thứ 101 | `Error: too many line items` |
| Đơn giá `0` | Kết thúc nhập mặt hàng, **không phải lỗi** |

Ví dụ, với input chỉ có một dòng `abc`:

```text
abc
```

**Stdout chính xác:**

```text
Unit price VND (0 to finish):
Error: expected an integer
```

Với input gồm đơn giá hợp lệ và số lượng `0`:

```text
100000
0
```

**Stdout chính xác:**

```text
Unit price VND (0 to finish):
Quantity:
Error: quantity must be from 1 to 100
```

Các lỗi input này được biểu diễn bằng `IllegalArgumentException`, sau đó `main` bắt và in thông báo dễ hiểu. `try-with-resources` đóng `Scanner` khi chương trình kết thúc; trong một ứng dụng lớn hơn có nhiều bộ phận còn cần `System.in`, nên giao trách nhiệm quản lý luồng nhập cho một nơi thay vì đóng scanner giữa chừng.

**Vì sao chương trình không hỏi nhập lại khi sai?** Đó là quyết định để ví dụ tập trung vào vòng lặp mặt hàng, điều kiện chiết khấu và kiểm tra lỗi. Có thể mở rộng thành vòng lặp nhập lại có giới hạn số lần, nhưng phải tránh để dữ liệu sai lặp vô tận hoặc thêm mặt hàng chưa được kiểm tra.

## 9. Các lỗi lập trình phổ biến

### 9.1. Đặt biến cộng dồn vào trong vòng lặp

**Sai về logic:**

```java
while (true) {
    long subtotal = 0L; // mỗi lần lặp lại về 0
    // ... đọc và cộng tiền ...
}
```

Đây chỉ là đoạn minh họa không hoàn chỉnh. Hãy khai báo `subtotal` **trước vòng lặp** để giữ lại tổng qua các lượt.

### 9.2. Dùng gán thay cho cộng dồn

```java
subtotal = lineTotal;  // chỉ giữ tiền của mặt hàng cuối
subtotal += lineTotal; // cộng thêm dòng mới vào tổng hiện có
```

Hai dòng là minh họa cách so sánh hai lựa chọn, **không** được thực hiện cả hai liên tiếp. Trong chương trình thật, dùng dòng thứ hai để cộng dồn.

### 9.3. Sai thứ tự điều kiện chiết khấu

Nếu kiểm tra `subtotal >= 200_000` **trước** trong cùng chuỗi `if / else if`, trường hợp từ 500.000 VND sẽ thỏa nhánh 5% và **không đến nhánh 10%**.

Đúng:

```java
if (subtotal >= 500_000L) {
    discountPercent = 10;
} else if (subtotal >= 200_000L) {
    discountPercent = 5;
} else {
    discountPercent = 0;
}
```

Đây là đoạn minh họa thuộc phương thức đã khai báo `subtotal` và `discountPercent`. Hãy kiểm tra mốc lớn hơn trước vì các điều kiện có tính bao hàm nhau.

### 9.4. Nhầm `break`, `continue` và `return`

- `break` thoát vòng lặp hiện tại, giúp chuyển sang bước tính tổng cuối.
- `continue` bỏ phần còn lại của **lượt hiện tại** rồi bắt đầu lượt mới; nếu dùng sai có thể bỏ kiểm tra hoặc bỏ việc cập nhật biến.
- `return` kết thúc phương thức đang chạy. Dùng `return` trong `main` tại giá `0` sẽ khiến bước in hóa đơn phía sau không chạy.

### 9.5. Dùng `double` và kỳ vọng mọi số tiền đều chính xác

`double` không biểu diễn chính xác mọi phân số thập phân. Với VND nguyên và giới hạn nhỏ, `long` là lựa chọn đơn giản. Nếu hóa đơn sử dụng đơn vị nhỏ nhất của tiền có phần thập phân hoặc cần áp dụng quy tắc thuế/phí chính xác, cân nhắc **`BigDecimal`** hay số nguyên đơn vị nhỏ nhất, cùng chính sách làm tròn rõ ràng.

### 9.6. Không kiểm tra giới hạn gây tràn số

Nếu vô hạn số lượng mặt hàng, hoặc cho nhập giá và số lượng rất lớn, biểu thức `unitPrice * quantity` hay `subtotal += lineTotal` có thể tràn `long`. Chương trình mẫu bảo vệ bằng cả ba giới hạn: đơn giá, số lượng và số dòng. Khi làm ứng dụng thật có giới hạn khác, cần tính lại cận trên, dùng `Math.multiplyExact()`/`Math.addExact()` hoặc kiểu phù hợp.

### 9.7. Lỗi luồng đọc khi trộn `nextLong()` và `nextLine()`

`Scanner.nextLong()` chỉ đọc một token số; `nextLine()` ngay sau đó có thể nhận phần còn lại của dòng cũ. Ví dụ chính dùng **`nextLine()` cho tất cả các lần đọc** và `Long.parseLong()` để chuyển đổi, nên tránh được lỗi này. Nếu đổi sang `nextLong()`, cần thiết kế lại cách xử lý dấu xuống dòng.

## 10. Mở rộng bài tập có kiểm soát

Sau khi chương trình mẫu chạy đúng, có thể mở rộng từng chức năng một, luôn xác định lại Input, Process, Output và trường hợp kiểm thử.

**Bài A — Giảm giá theo mã ưu đãi:** cho nhập mã `SAVE5` để giảm thêm theo quy định. Phải nêu rõ mã được áp dụng **trước hay sau** chiết khấu theo ngưỡng, mức giảm có thể cộng dồn không và tiền giảm có được vượt tạm tính không.

**Bài B — Phí giao hàng:** miễn phí nếu tổng sau giảm từ 300.000 VND; nếu không thu 20.000 VND. Quy định rõ phí tính theo số tiền **trước hay sau giảm**, rồi đưa phí vào Output thay vì tự cộng thẳng trong câu lệnh in.

**Bài C — Nhập lại khi số sai:** tổ chức vòng lặp riêng yêu cầu nhập đúng giá/số lượng, có thông báo và điều kiện dừng. Cần phân biệt `0` kết thúc giỏ hàng tại câu hỏi về **giá**, còn `0` khi hỏi **số lượng** vẫn là sai.

**Bài D — Số mặt hàng cố định:** nếu đầu vào cho biết trước chính xác `n` dòng, vòng lặp `for (int i = 0; i < n; i++)` thường phù hợp hơn `while (true)`. Vẫn phải kiểm tra miền của `n`.

**Bài E — Tách chức năng:** chuyển cách tính mức giảm thành `discountPercentFor(long subtotal)` và cách tính tiền thanh toán thành một phương thức thuần không đọc console. Điều này giúp thử các ngưỡng 199.999, 200.000, 499.999 và 500.000 VND mà không cần nhập lại cả giỏ hàng.

Các gợi ý trên là **bài mở rộng**, không phải phần của mã `InvoiceApp.java`; đầu ra đã cam kết ở các ví dụ trước không phụ thuộc những tính năng chưa triển khai.

## 11. Checklist trước khi kết thúc bài thực hành

- Tôi đã xác định input là **đơn giá và số lượng theo từng dòng**, cùng ký hiệu kết thúc rõ ràng chưa?
- Giá `0` có được kiểm tra **trước** khi hỏi số lượng không?
- `subtotal` và `itemCount` có nằm **ngoài vòng lặp** và tăng đúng mỗi dòng hợp lệ không?
- Có kiểm tra giá/số lượng âm, vượt giới hạn, chuỗi không phải số và EOF không?
- Tôi dùng `if / else if / else` với **mốc cao trước, mốc thấp sau** chưa?
- Có kiểm tra hóa đơn rỗng, đúng mốc 200.000, đúng mốc 500.000 và trường hợp tổng ngay dưới mốc không?
- Tôi đã thống nhất làm tròn tiền giảm theo phép chia nguyên VND chưa?
- Sau khi `javac` thành công, tôi có chạy `java` và đối chiếu **stdout thực** với bảng trace/đầu ra dự kiến không?

**Ghi nhớ:** vòng lặp giải quyết việc **có bao nhiêu mặt hàng**, điều kiện giải quyết việc **đầu vào hợp lệ và được giảm bao nhiêu**, còn biến cộng dồn giữ **tạm tính sau mỗi lượt**. Phân chia rõ ba trách nhiệm giúp chương trình tính tiền dễ kiểm thử và ít lỗi hơn.
