# BigDecimal.toString() và dạng khoa học khi phù hợp

## Mục tiêu

Khi chuyển một `BigDecimal` thành chuỗi trong Java, phương thức `toString()` không phải lúc nào cũng tạo ra một số viết đầy đủ theo dạng thập phân thông thường. Nó có thể chọn **dạng khoa học** (*scientific notation*) như `1E-7` hoặc `1E+6`. Hành vi này có quy tắc rõ ràng, phụ thuộc vào **giá trị không chia tỷ lệ**, **scale** và **precision** của `BigDecimal`.

Sau bài này, bạn có thể giải thích khi nào `toString()` sinh dạng khoa học, chọn đúng giữa `toString()`, `toPlainString()` và `toEngineeringString()`, và hiểu tác động của việc chuyển chuỗi ngược lại thành `BigDecimal`.

## 1. BigDecimal lưu giá trị như thế nào?

`BigDecimal` biểu diễn một số bằng hai thành phần chính:

- **Unscaled value**: số nguyên chứa các chữ số có nghĩa, lấy bằng `unscaledValue()`.
- **Scale**: số chữ số thập phân về mặt biểu diễn, lấy bằng `scale()`. Scale có thể dương, bằng 0 hoặc âm.

Giá trị số học được tính theo công thức:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

Ví dụ:

| Chuỗi tạo BigDecimal | Unscaled value | Scale | Giá trị |
|---|---:|---:|---|
| `"123.4500"` | `1234500` | `4` | `123.4500` |
| `"0.000001"` | `1` | `6` | `0.000001` |
| `"0.0000001"` | `1` | `7` | `0.0000001` |
| `"1E+3"` | `1` | `-3` | `1000` |
| `"1000"` | `1000` | `0` | `1000` |

Hai đối tượng `new BigDecimal("1E+3")` và `new BigDecimal("1000")` **bằng nhau về giá trị số học**, nhưng khác scale và unscaled value. Vì vậy `compareTo()` có thể trả `0` trong khi `equals()` trả `false`.

**Precision** là số chữ số trong giá trị không chia tỷ lệ nếu không tính dấu và số 0 dẫn đầu (riêng giá trị 0 có precision bằng 1). Ví dụ `123.4500` có precision `7`, scale `4`; `1E+3` có precision `1`, scale `-3`. Đừng nhầm precision với số chữ số sau dấu thập phân.

## 2. toString() sinh dạng thập phân hay dạng khoa học?

`BigDecimal.toString()` tạo **biểu diễn chuỗi chuẩn (canonical)** của cặp unscaled value và scale. Phương thức bảo toàn giá trị, scale và các số 0 cuối có ý nghĩa đối với biểu diễn; nó **không làm tròn** và không chuyển qua `double`.

Để hiểu quy tắc hiển thị, xét **adjusted exponent** của `BigDecimal`:

\[
\text{adjustedExponent} = \text{precision} - \text{scale} - 1
\]

Với `BigDecimal` khác 0, adjusted exponent cho biết lũy thừa của 10 ứng với chữ số có nghĩa đầu tiên. Cơ chế chuẩn của `toString()` chọn:

1. **Dạng thập phân thông thường** nếu **scale không âm** (`scale >= 0`) **và adjusted exponent từ -6 trở lên** (`adjustedExponent >= -6`).
2. **Dạng khoa học** trong các trường hợp còn lại, với một chữ số có nghĩa đứng trước dấu chấm, phần còn lại (nếu có) đứng sau, rồi ký hiệu `E` và số mũ.

Với số mũ dương, Java thêm dấu `+` sau `E`, chẳng hạn `1E+3`. Với số mũ âm, Java dùng dấu `-` như `1E-7`. Ở dạng thông thường, dấu thập phân là `.`, không phụ thuộc thiết lập ngôn ngữ của máy.

Hai ví dụ sát ngưỡng rất đáng nhớ:

- `new BigDecimal("0.000001").toString()` tạo `"0.000001"`: precision `1`, scale `6`, adjusted exponent `-6`, nên giữ dạng thông thường.
- `new BigDecimal("0.0000001").toString()` tạo `"1E-7"`: precision `1`, scale `7`, adjusted exponent `-7`, nên chuyển sang dạng khoa học.

Quy tắc còn phụ thuộc **scale**, không chỉ độ lớn của số. `new BigDecimal("1000000").toString()` là `"1000000"` vì scale `0`; `new BigDecimal("1E+6").toString()` là `"1E+6"` vì scale `-6`. Giá trị số học của chúng giống nhau.

### Chuỗi khoa học có nghĩa gì?

Trong cú pháp Java `BigDecimal`:

- `1E-7` nghĩa là \(1 \times 10^{-7}\), tức `0.0000001`.
- `1.23E+4` nghĩa là \(1.23 \times 10^4\), tức `12300`.
- `1E+6` nghĩa là \(1 \times 10^6\), tức `1000000`.

`E` là ký hiệu số mũ cơ số 10, không phải phép tính bằng hằng số toán học Euler. Trong Java, có thể dựng lại giá trị bằng `new BigDecimal("1E-7")`.

## 3. Phân biệt toString(), toPlainString(), toEngineeringString()

Cả ba phương thức **chỉ tạo chuỗi**, không sửa hoặc làm tròn đối tượng `BigDecimal`.

| Phương thức | Mục đích | Ví dụ với `new BigDecimal("0.0000001")` |
|---|---|---|
| `toString()` | Chuỗi chuẩn, có thể dùng dạng khoa học tùy scale và adjusted exponent | `"1E-7"` |
| `toPlainString()` | Chuỗi dạng thập phân đầy đủ, **không có ký hiệu E** | `"0.0000001"` |
| `toEngineeringString()` | Khi viết dưới dạng số mũ, chọn **số mũ là bội số của 3**; hệ số có thể có 1–3 chữ số trước dấu thập phân | `"100E-9"` |

Ví dụ dễ gặp:

| Giá trị được tạo | `toString()` | `toPlainString()` | `toEngineeringString()` |
|---|---|---|---|
| `"123.4500"` | `123.4500` | `123.4500` | `123.4500` |
| `"0.000001"` | `0.000001` | `0.000001` | `0.000001` |
| `"0.0000001"` | `1E-7` | `0.0000001` | `100E-9` |
| `"1E+3"` | `1E+3` | `1000` | `1E+3` |
| `"1.23E+4"` | `1.23E+4` | `12300` | `12.3E+3` |
| `"1000000"` | `1000000` | `1000000` | `1000000` |
| `"1000000.00"` | `1000000.00` | `1000000.00` | `1000000.00` |

`100E-9` và `1E-7` có cùng giá trị vì \(100 \times 10^{-9} = 10^{-7}\). Dạng kỹ thuật có ích khi trình bày bậc độ lớn theo nhóm nghìn, triệu, tỷ; còn dạng khoa học tiêu chuẩn của `toString()` ưu tiên một chữ số trước dấu chấm.

### Chọn phương thức nào?

- **Ghi lại biểu diễn BigDecimal để có thể đọc lại chính xác cả value/scale**: dùng `toString()`. Chuỗi chuẩn chứa đủ thông tin để `new BigDecimal(original.toString()).equals(original)` là `true`.
- **Giao diện, log hoặc trường văn bản yêu cầu không có E**: dùng `toPlainString()`, nhưng kiểm tra độ dài vì số có scale rất lớn về độ lớn tuyệt đối có thể tạo chuỗi dài.
- **Hiển thị số mũ theo bội của 3**: dùng `toEngineeringString()` nếu đây là quy tắc trình bày mong muốn.

Với số lượng tiền có cách hiển thị cố định, phải xác định **scale/làm tròn** riêng trước khi tạo chuỗi. `toPlainString()` chỉ đổi cách biểu diễn, không tự áp dụng hai chữ số phần lẻ. Ví dụ `new BigDecimal("12.345").toPlainString()` vẫn là `"12.345"`.

## 4. Chương trình Java 17+ có thể chạy ngay

Lưu dưới tên **`BigDecimalStringDemo.java`**:

```java
import java.math.BigDecimal;

public class BigDecimalStringDemo {
    private static void show(String source) {
        BigDecimal number = new BigDecimal(source);

        System.out.println(source
                + " | " + number.toString()
                + " | " + number.toPlainString()
                + " | " + number.toEngineeringString()
                + " | " + number.precision()
                + " | " + number.scale());
    }

    public static void main(String[] args) {
        System.out.println("input | toString | plain | engineering | precision | scale");

        for (String source : new String[] {
                "123.4500",
                "0.000001",
                "0.0000001",
                "1E+3",
                "1.23E+4",
                "1000000",
                "1000000.00"
        }) {
            show(source);
        }

        BigDecimal withZeros = new BigDecimal("1000000.00");
        BigDecimal stripped = withZeros.stripTrailingZeros();
        System.out.println("stripTrailingZeros: " + stripped.toString());

        BigDecimal scientific = new BigDecimal("1E+3");
        BigDecimal fromCanonical = new BigDecimal(scientific.toString());
        BigDecimal fromPlain = new BigDecimal(scientific.toPlainString());

        System.out.println("canonical equals: " + scientific.equals(fromCanonical));
        System.out.println("plain equals: " + scientific.equals(fromPlain));
        System.out.println("plain compareTo: " + scientific.compareTo(fromPlain));
    }
}
```

Biên dịch và chạy:

```bash
javac BigDecimalStringDemo.java
java BigDecimalStringDemo
```

Kết quả chính xác:

```text
input | toString | plain | engineering | precision | scale
123.4500 | 123.4500 | 123.4500 | 123.4500 | 7 | 4
0.000001 | 0.000001 | 0.000001 | 0.000001 | 1 | 6
0.0000001 | 1E-7 | 0.0000001 | 100E-9 | 1 | 7
1E+3 | 1E+3 | 1000 | 1E+3 | 1 | -3
1.23E+4 | 1.23E+4 | 12300 | 12.3E+3 | 3 | -2
1000000 | 1000000 | 1000000 | 1000000 | 7 | 0
1000000.00 | 1000000.00 | 1000000.00 | 1000000.00 | 9 | 2
stripTrailingZeros: 1E+6
canonical equals: true
plain equals: false
plain compareTo: 0
```

**Cách đọc kết quả:** Dòng `0.0000001` cho thấy `toString()` có thể tự chọn dạng mũ khi adjusted exponent nhỏ hơn `-6`. Dòng `1E+3` cho thấy `toPlainString()` biến giá trị thành `1000` nhưng **không giữ scale âm** sau khi parse chuỗi trở lại. Dòng `stripTrailingZeros` minh họa rằng cùng giá trị `1000000` có thể được biểu diễn bằng dạng mũ khi scale thay đổi.

## 5. Vì sao toPlainString() không luôn phù hợp với round-trip của BigDecimal?

Đối với `BigDecimal`, có hai cách so sánh khác nhau:

- `compareTo()` so sánh **giá trị số học**; `new BigDecimal("1E+3").compareTo(new BigDecimal("1000")) == 0`.
- `equals()` yêu cầu cùng **giá trị số học và scale**; hai đối tượng trên không `equals` vì scale lần lượt `-3` và `0`.

Xét:

```java
BigDecimal original = new BigDecimal("1E+3");
BigDecimal parsedCanonical = new BigDecimal(original.toString());
BigDecimal parsedPlain = new BigDecimal(original.toPlainString());

System.out.println(original.scale());             // -3
System.out.println(parsedCanonical.scale());      // -3
System.out.println(parsedPlain.scale());          // 0
System.out.println(original.equals(parsedPlain)); // false
System.out.println(original.compareTo(parsedPlain) == 0); // true
```

`toString()` là lựa chọn chuẩn khi cần **round-trip tái lập cùng biểu diễn BigDecimal**, bao gồm scale. `toPlainString()` phù hợp hơn khi cần chuỗi dễ đọc không có ký hiệu khoa học. Nếu ứng dụng chỉ quan tâm đến giá trị số học, `compareTo()` phản ánh quan hệ số học phù hợp hơn `equals()`; nếu scale là một phần hợp đồng dữ liệu, hãy giữ thông tin scale hoặc dùng `toString()`.

Chú ý `System.out.println(number)`, phép ghép chuỗi `"x=" + number` và `String.valueOf(number)` đều gọi `toString()` đối với `BigDecimal` không null. Vì vậy các cách in đó **vẫn có thể hiện dạng khoa học**. Gọi `toPlainString()` trực tiếp nếu đích hiển thị cần dạng đầy đủ.

## 6. stripTrailingZeros() có thể làm xuất hiện E

`stripTrailingZeros()` trả về một `BigDecimal` tương đương về **giá trị số học** nhưng bỏ các số 0 tận cùng trong biểu diễn unscaled value khi có thể. Kết quả có thể có **scale âm**, làm `toString()` đổi sang dạng khoa học.

Ví dụ:

```java
BigDecimal before = new BigDecimal("1000000.00");
BigDecimal after = before.stripTrailingZeros();

System.out.println(before.toString());  // 1000000.00
System.out.println(before.scale());     // 2
System.out.println(after.toString());   // 1E+6
System.out.println(after.scale());      // -6
System.out.println(after.toPlainString()); // 1000000
```

Đây **không phải sai số và không phải phép làm tròn**. Giá trị vẫn bằng một triệu; chính biểu diễn unscaled value/scale đã thay đổi. `stripTrailingZeros()` cũng không sửa đối tượng `before` vì `BigDecimal` bất biến.

Điều này hay gây nhầm lẫn khi một hàm chuẩn hóa dữ liệu gọi `stripTrailingZeros()` rồi nơi khác vô tình dùng `toString()` để xuất kết quả. Nếu yêu cầu đầu ra là chuỗi không E, chọn `toPlainString()` sau khi có đối tượng kết quả. Nếu yêu cầu giữ nguyên số chữ số thập phân ban đầu (ví dụ `1000000.00`), **đừng bỏ trailing zeros trước khi lưu biểu diễn**.

## 7. Các trường hợp biên và sai lầm thường gặp

### Coi dạng khoa học là mất giá trị hoặc mất độ chính xác

`1E-7` và `0.0000001` đều là giá trị thập phân chính xác \(10^{-7}\). `toString()` không rút gọn chữ số có nghĩa theo một precision mới. Nó chỉ chọn cách viết tương ứng với unscaled value/scale hiện có. Đừng dùng `doubleValue()` rồi chuyển sang chuỗi để “né E”: `double` có miền biểu diễn và độ chính xác nhị phân khác `BigDecimal`.

### Nghĩ rằng BigDecimal lớn tự động phải in khoa học

`new BigDecimal("1000000")` in `1000000`; `new BigDecimal("1E+6")` in `1E+6` dù giá trị bằng nhau. Điều kiện của `toString()` là **scale và adjusted exponent**, không phải một ngưỡng giá trị tuyệt đối duy nhất.

### Xóa số 0 cuối rồi kỳ vọng cùng scale

`new BigDecimal("12.3400").toString()` là `"12.3400"` vì scale `4` vẫn được bảo toàn. `stripTrailingZeros()` có thể thay đổi scale; `toPlainString()` không tự khôi phục số 0 biểu diễn ban đầu. Nếu dữ liệu yêu cầu đúng số chữ số, dùng `setScale(scale, roundingMode)` theo quy định nghiệp vụ trước khi xuất chuỗi. Phương thức `setScale` có thể cần làm tròn và yêu cầu `RoundingMode`; khác về chức năng so với ba phương thức chỉ tạo chuỗi.

### Dùng chuỗi để quyết định số nào lớn hơn

So sánh chuỗi `"1E+3"` và `"900"` theo thứ tự từ điển không tương đương so sánh số. Hãy so sánh chính các đối tượng `BigDecimal` bằng `compareTo()` trước, rồi chuyển sang chuỗi khi cần hiển thị hoặc truyền dữ liệu.

### Quên yêu cầu định dạng theo vùng miền

`toString()`, `toPlainString()` và `toEngineeringString()` đều dùng ký hiệu thập phân kiểu Java (dấu chấm và ký hiệu E khi có), **không tự đổi** thành dấu phẩy theo locale hoặc thêm dấu phân cách hàng nghìn. Nếu giao diện cần quy tắc trình bày theo vùng miền, dùng cơ chế định dạng như `NumberFormat`/`DecimalFormat`, cấu hình locale và làm tròn phù hợp. Việc định dạng để hiển thị cần được phân biệt với biểu diễn chuẩn dùng để lưu/đọc lại BigDecimal.

### Không chú ý kích thước đầu ra

`toPlainString()` luôn cố tạo dạng đầy đủ; với scale có độ lớn rất lớn, chuỗi có thể chứa số lượng chữ số hoặc số 0 rất lớn. Chỉ chọn dạng đầy đủ khi thật sự cần và dữ liệu đầu vào có giới hạn phù hợp. Dạng mũ của `toString()` ngắn hơn trong nhiều trường hợp, nhưng không phải cơ chế giới hạn dung lượng đầu ra.

## 8. Quy trình chọn cách chuyển chuỗi

1. **Cần lưu và khôi phục chính xác đối tượng BigDecimal, kể cả scale?** Dùng `toString()` rồi đọc bằng `new BigDecimal(text)`. Đây là biểu diễn chuẩn phù hợp cho round-trip.
2. **Cần hiển thị đầy đủ, không được có E?** Dùng `toPlainString()`; tự quy định scale/làm tròn và độ dài đầu ra nếu nghiệp vụ đòi hỏi.
3. **Cần ký pháp lũy thừa với số mũ theo bội của 3?** Dùng `toEngineeringString()`.
4. **Bất ngờ thấy E sau một bước chuẩn hóa?** Kiểm tra `stripTrailingZeros()` và `scale()` trước/sau.
5. **Hai chuỗi khác nhau nhưng mô tả cùng một số?** Kiểm tra cả `compareTo()` và `scale()`; không mặc định `equals()` phản ánh riêng giá trị số học.

**Tự kiểm tra:** Tại sao `new BigDecimal("0.000001").toString()` là `"0.000001"`, còn `new BigDecimal("0.0000001").toString()` là `"1E-7"`? Vì adjusted exponent lần lượt là `-6` và `-7`, trong khi scale đều không âm. Và tại sao `new BigDecimal("1E+3").toPlainString()` tạo `"1000"` nhưng đọc lại có thể `equals() == false`? Vì chuỗi thông thường làm mất scale âm `-3`, đối tượng đọc lại có scale `0` dù giá trị số học không đổi.

**Ghi nhớ:** `BigDecimal.toString()` chọn dạng khoa học dựa trên scale và adjusted exponent, bảo toàn biểu diễn để round-trip; `toPlainString()` bảo đảm không có E; `toEngineeringString()` dùng số mũ theo bội số của 3. Cả ba **không thực hiện làm tròn**.
