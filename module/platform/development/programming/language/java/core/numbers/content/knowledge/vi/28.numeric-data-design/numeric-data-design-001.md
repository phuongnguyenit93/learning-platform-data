# Ghi rõ miền giá trị, đơn vị và giới hạn khi thiết kế dữ liệu số trong Java

Một trường số như `amount`, `distance`, `quantity` hay `rate` không được mô tả đầy đủ chỉ bằng kiểu `int`, `long`, `double` hoặc `BigDecimal`. Cùng một giá trị `100` có thể là 100 đồng, 100 cent, 100 mét, 100 mili giây hoặc 100 phần trăm. Tương tự, kiểu `long` có thể lưu một số âm rất lớn, nhưng một số lượng hàng hóa trong miền nghiệp vụ lại chỉ được phép từ 0 đến 10.000. Sử dụng kiểu Java phù hợp là cần thiết; **hợp đồng dữ liệu số phải ghi rõ miền giá trị, đơn vị, độ chính xác và cách xử lý khi vượt giới hạn**.

Bài này tập trung vào cách mô tả và thực thi hợp đồng số tại ranh giới API, DTO, model, lưu trữ và phép tính. Kết quả mong muốn: hai người phát triển độc lập có thể đọc đặc tả và hiểu giống nhau về ý nghĩa của một con số, thay vì tự suy đoán từ tên biến hay kiểu primitive.

## 1. Phân biệt phạm vi của kiểu Java và phạm vi nghiệp vụ

**Miền biểu diễn của kiểu** là mọi giá trị mà kiểu dữ liệu lưu được. **Miền hợp lệ của nghiệp vụ** là tập con được hệ thống cho phép.

| Dữ liệu | Kiểu Java khả dĩ | Miền nghiệp vụ ví dụ | Đơn vị |
| --- | --- | --- | --- |
| Số lượng mặt hàng | `int` | 0 đến 10.000 | sản phẩm |
| Thời hạn yêu cầu | `long` | 1 đến 120.000 | mili giây |
| Quãng đường | `long` | 0 đến 10.000.000 | milimét |
| Giá không âm | `long` | 0 đến 100.000.000 | đơn vị tiền tệ nhỏ nhất |
| Tỷ lệ chiết khấu | `int` | 0 đến 10.000 | basis point, 1 bp = 0,01% |
| Khối lượng | `BigDecimal` | 0 đến 1.000, độ phân giải 0,001 | kilôgam |

**Các con số trong bảng là ví dụ về một hợp đồng cụ thể**, không phải giới hạn mặc định do Java hoặc từng ngành nghề áp đặt. Mỗi sản phẩm phải tự quyết định phạm vi của mình.

Về kỹ thuật:

- `byte`: từ -128 đến 127.
- `short`: từ -32.768 đến 32.767.
- `int`: từ -2.147.483.648 đến 2.147.483.647.
- `long`: từ -9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807.
- `BigInteger`: biểu diễn số nguyên độ lớn thay đổi, không bị giới hạn ở 32/64 bit nhưng vẫn chịu giới hạn tài nguyên.
- `BigDecimal`: biểu diễn số thập phân chính xác theo phần nguyên không tỉ lệ (`unscaled value`) và `scale`; vẫn cần xác định miền, độ phân giải và quy tắc làm tròn phù hợp.
- `float` và `double`: số dấu phẩy động nhị phân, có `NaN`, vô cực dương/âm và sai số biểu diễn; chỉ nên chọn nếu các đặc tính đó phù hợp miền dữ liệu.

Chẳng hạn, nếu `quantity` là `int`, Java không ngăn người gọi truyền `-5` hoặc `2_000_000`. Điều kiện “0 đến 10.000” phải được **nêu trong hợp đồng và kiểm tra trong chương trình**, không được suy ra từ kiểu `int`.

Đặc tả cần nói rõ hai đầu biên là **bao gồm** hay **loại trừ**. Ví dụ `0 <= count && count <= 10_000` khác với `0 < count && count < 10_000`. Một trường cho phép 0 cũng khác trường luôn phải dương.

## 2. Ghi rõ đơn vị và ý nghĩa của mỗi trường

Các con số cùng kiểu Java vẫn có thể là những đại lượng không tương thích về đơn vị. Đoạn mã dưới đây biên dịch nhưng rất dễ sai:

```java
long timeout = 5;       // 5 giây hay 5 mili giây?
long distance = 1200;   // 1200 mét hay 1200 milimét?
long price = 1999;      // 1999 đồng hay 19,99 đơn vị tiền?
```

Không đủ thông tin để biết các giá trị trên có chính xác không. Hãy ghi rõ ý nghĩa và, khi hợp lý, đưa đơn vị vào tên biến/API:

```java
long timeoutMillis = 5_000L;
long distanceMillimeters = 1_200L;
long priceMinorUnits = 1_999L;
```

Hợp đồng cho một trường số nên mô tả ít nhất:

1. **Tên đại lượng:** số lượng, thời gian, chiều dài, giá, tỷ lệ hay mã định danh.
2. **Đơn vị gốc (canonical unit):** mili giây, milimét, cent, basis point, byte...
3. **Miền hợp lệ:** min/max, có bao gồm biên không, có cho phép số âm và số 0 không.
4. **Độ phân giải và độ chính xác:** bước tăng nhỏ nhất, số chữ số thập phân được chấp nhận.
5. **Chính sách với giá trị thiếu:** `null` có hợp lệ hay không; 0 có mang nghĩa “chưa biết” hay không.
6. **Chính sách chuyển đổi và làm tròn:** chuyển đơn vị theo hệ số nào; loại bỏ hay làm tròn phần dư; nếu làm tròn thì theo quy tắc nào.
7. **Hành vi khi vi phạm:** từ chối với ngoại lệ/kết quả lỗi, hay xử lý theo quy định nghiệp vụ.

Ví dụ, trường thời gian có thể được đặc tả: “`timeoutMillis`: số nguyên mili giây; từ 1 đến 120.000 tính cả hai đầu; bắt buộc có; giá trị 0 và âm không hợp lệ; giá trị vượt giới hạn bị từ chối.” Đây là hợp đồng có thể dùng để triển khai và kiểm thử.

### Tránh phép cộng trộn đơn vị

```java
long durationSeconds = 3;
long durationMillis = 500;

// Sai nghĩa: 3 giây + 500 mili giây không phải là 503 mili giây.
long wrong = durationSeconds + durationMillis;

// Đúng: cùng đơn vị mili giây trước khi cộng.
long correct = Math.addExact(
        Math.multiplyExact(durationSeconds, 1_000L), durationMillis);
// correct = 3500
```

`Math.multiplyExact` và `Math.addExact` giúp phát hiện tràn trong chuyển đổi/cộng nguyên. Đây là mảnh mã minh họa đặt trong một phương thức. Nếu đầu vào từ các hệ thống khác nhau, hãy chuyển tất cả về cùng đơn vị **trước khi tính**, đồng thời nêu rõ nơi phép chuyển đổi được thực hiện.

Java có các kiểu làm rõ một số miền dữ liệu, ví dụ `java.time.Duration` cho khoảng thời gian. Khi dùng `Duration`, không nên coi hai tham số `long` tùy ý mang cùng ý nghĩa. Các API như `Duration.ofSeconds(3)` và `Duration.ofMillis(500)` nói rõ đơn vị ngay ở chỗ tạo dữ liệu.

## 3. Độ phân giải và chính sách decimal thuộc hợp đồng trường

Ngay cả khi biết **đơn vị** của một số, API vẫn phải quy định bước nhỏ nhất, ví dụ 0,001 kg hoặc 0,01 đơn vị tiền. `BigDecimal.scale()` là bậc lũy thừa 10 của biểu diễn, còn `precision()` là số chữ số có nghĩa của hệ số. Chúng không tự định nghĩa đơn vị hoặc quy tắc nghiệp vụ.

```java
BigDecimal value = new BigDecimal("12.30");
System.out.println(value.scale());     // 2
System.out.println(value.precision()); // 4
BigDecimal accepted = value.setScale(2, RoundingMode.UNNECESSARY);
```

Với yêu cầu **không được làm tròn**, `setScale(2, RoundingMode.UNNECESSARY)` chấp nhận `12.30` nhưng từ chối `12.345`. Điều này kiểm tra khả năng biểu diễn ở độ phân giải 0,01, không buộc token gốc có đúng hai ký tự sau dấu thập phân. Nếu hệ thống cho phép làm tròn, phải ghi rõ thời điểm và `RoundingMode` (không mặc định một mode cho mọi đồng tiền). Bài `Đưa precision, scale và rounding vào hợp đồng` triển khai đầy đủ chính sách và các phép chia.

Đối với tiền, số nguyên của **đơn vị nhỏ nhất** có thể thích hợp nếu đồng tiền và tỉ lệ giữa hai đơn vị được đặc tả. Không tự giả định mọi đồng tiền có đúng hai chữ số thập phân hoặc có thể cộng số tiền khác đơn vị.

## 4. Giới hạn phải bao phủ cả phép tính trung gian

Miền của mỗi trường có thể nhỏ nhưng **tổng hoặc tích** vượt kiểu primitive của toán hạng. Nếu số lượng tối đa là 50.000 và đơn giá tối đa là 100.000 đơn vị nhỏ, tích có thể đến 5.000.000.000, vượt `int`:

```java
int quantity = 50_000;
int unitPriceMinor = 100_000;
long correct = (long) quantity * unitPriceMinor; // 5000000000
```

Thăng hạng phải xảy ra **trước khi nhân**, không đợi tới biến nhận kết quả. Sử dụng `Math.multiplyExact`, `Math.addExact`, `Math.toIntExact` hoặc kiểu `BigInteger` theo giới hạn của nghiệp vụ. Nếu kết quả cuối nhỏ nhưng bước trung gian tràn, phải xác định hợp đồng từ chối trung gian hay tính với kiểu rộng rồi xét kết quả cuối.

Bài `Chọn kiểu tính toán trung gian riêng với kiểu lưu trữ` phân tích đầy đủ `IntStream`, các phép toán trung gian, thu hẹp và ranh giới lưu trữ.

## 5. Cùng hợp đồng phải có hiệu lực từ Java đến hệ thống nhận

Hợp đồng dữ liệu số cần khớp giữa model Java, DTO/API, JSON, cơ sở dữ liệu và biểu diễn trong file. Một `long` hợp lệ tại backend có thể vượt `Number.MAX_SAFE_INTEGER` của client JavaScript; nếu cần số nguyên chính xác hai chiều, phải thống nhất schema, ví dụ truyền chuỗi decimal với parser tương ứng. Một cột `DECIMAL(p,s)` vẫn cần quy tắc nghiệp vụ về miền, dấu, precision, scale.

Các giao diện có thể nhập **mét** nhưng model lưu **milimét**; phải chuyển đơn vị ở ranh giới rõ ràng, kiểm tra tràn và xuất đúng đơn vị được công bố. Không được tự dùng chuỗi đã phân nhóm hoặc làm tròn cho người đọc làm payload chuẩn. Bài `Tách định dạng hiển thị khỏi tính toán và trao đổi` mở rộng phần giao thức và locale.

## 6. Từ trường primitive đến kiểu đại diện miền dữ liệu

Trường `long` có thể phù hợp khi code nhỏ và mọi nơi cùng hiểu hợp đồng. Với API quan trọng, có thể bọc giá trị trong một **value object** để kiểm tra miền ngay lúc tạo:

```java
record DistanceMillimeters(long value) {
    static final long MAX_VALUE = 10_000_000L; // Ví dụ giới hạn 10 km.

    DistanceMillimeters {
        if (value < 0 || value > MAX_VALUE) {
            throw new IllegalArgumentException("distance out of range");
        }
    }
}
```

Đây là một `record` Java 17 và là **mảnh mã minh họa**. Constructor compact được gọi khi tạo record và từ chối mọi giá trị ngoài miền. `DistanceMillimeters` giúp hạn chế việc truyền nhầm milli giây cho tham số quãng đường; compiler chỉ nhìn `long` sẽ không có khả năng phân biệt hai đại lượng.

Có thể mở rộng value object để nhận đầu vào theo mét rồi chuyển sang milimét:

```java
static DistanceMillimeters fromMeters(String meters) {
    long mm = new BigDecimal(meters)
            .movePointRight(3)
            .longValueExact();
    return new DistanceMillimeters(mm);
}
```

Phương thức này nằm **bên trong** record `DistanceMillimeters` và cần import `java.math.BigDecimal`. `movePointRight(3)` chuyển mét sang milimét; `longValueExact()` từ chối nếu có phần lẻ nhỏ hơn 1 milimét (mà không thể chuyển chính xác sang số nguyên milimét) hoặc nếu số ngoài miền `long`. Constructor tiếp tục từ chối giá trị âm hoặc vượt 10.000.000 milimét.

Ví dụ `fromMeters("1.250")` lưu 1.250 mm; `fromMeters("0.0005")` bị từ chối vì tương đương 0,5 mm và hợp đồng này **không cho phép làm tròn**. Nếu sản phẩm muốn cho phép làm tròn nửa milimét, phải mô tả `RoundingMode` và quyết định đó trước khi triển khai.

Các đơn vị vật lý có thể có cả giá trị âm (ví dụ nhiệt độ Celsius) hoặc không (ví dụ độ dài). Không nên áp quy tắc “mọi đại lượng không được âm” một cách mặc định; đặt giới hạn đúng với từng miền.

## 7. Chương trình Java 17+ hoàn chỉnh: ràng buộc đơn vị, miền và độ phân giải

Ví dụ sau giả định một miền giá có **hai chữ số thập phân**, cùng một đồng tiền, chỉ nhận giá **không âm** và không vượt 1.000.000 đơn vị tiền lớn. Quãng đường được nhập bằng **mét**, lưu dưới dạng **milimét**, không âm và không vượt 10 km. Các giới hạn được chọn để minh họa cách viết hợp đồng, không phải quy tắc chung của thương mại hoặc đo lường.

Lưu tệp **`NumericContractDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.Objects;

public final class NumericContractDemo {
    private NumericContractDemo() {}

    record PriceCents(long value) {
        static final long MAX_CENTS = 100_000_000L;

        PriceCents {
            if (value < 0 || value > MAX_CENTS) {
                throw new IllegalArgumentException("price out of range");
            }
        }

        static PriceCents fromDecimal(String text) {
            Objects.requireNonNull(text, "price text");
            long cents = new BigDecimal(text)
                    .movePointRight(2)
                    .longValueExact();
            return new PriceCents(cents);
        }

        PriceCents plus(PriceCents other) {
            Objects.requireNonNull(other, "other");
            return new PriceCents(Math.addExact(value, other.value()));
        }

        String asDecimal() {
            return BigDecimal.valueOf(value, 2).toPlainString();
        }
    }

    record DistanceMillimeters(long value) {
        static final long MAX_MM = 10_000_000L;

        DistanceMillimeters {
            if (value < 0 || value > MAX_MM) {
                throw new IllegalArgumentException("distance out of range");
            }
        }

        static DistanceMillimeters fromMeters(String text) {
            Objects.requireNonNull(text, "meters text");
            long mm = new BigDecimal(text)
                    .movePointRight(3)
                    .longValueExact();
            return new DistanceMillimeters(mm);
        }

        String asMeters() {
            return BigDecimal.valueOf(value, 3).toPlainString();
        }
    }

    public static void main(String[] args) {
        PriceCents a = PriceCents.fromDecimal("12.34");
        PriceCents b = PriceCents.fromDecimal("2.66");
        System.out.println("total price = " + a.plus(b).asDecimal());

        DistanceMillimeters distance =
                DistanceMillimeters.fromMeters("1.250");
        System.out.println("distance m = " + distance.asMeters());

        try {
            PriceCents.fromDecimal("1.234");
        } catch (ArithmeticException ex) {
            System.out.println("price precision = rejected");
        }

        try {
            DistanceMillimeters.fromMeters("10000.001");
        } catch (IllegalArgumentException ex) {
            System.out.println("distance limit = rejected");
        }

        try {
            PriceCents.fromDecimal("-1.00");
        } catch (IllegalArgumentException ex) {
            System.out.println("negative price = rejected");
        }

        long widened = (long) Integer.MAX_VALUE + 1;
        System.out.println("int widened sum = " + widened);
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 NumericContractDemo.java
java NumericContractDemo
```

Stdout kỳ vọng:

```text
total price = 15.00
distance m = 1.250
price precision = rejected
distance limit = rejected
negative price = rejected
int widened sum = 2147483648
```

**Giải thích:**

- `"12.34"` và `"2.66"` được nhân chính xác với 100 và lưu dưới dạng `long` cent. Tổng 1.500 cent hiển thị thành `15.00`.
- `"1.250"` mét chuyển chính xác thành 1.250 milimét. Khi hiển thị bằng `BigDecimal.valueOf(value, 3)`, nó trở về `1.250`.
- `"1.234"` ở đơn vị tiền lớn tương ứng 123,4 cent; `longValueExact()` từ chối vì phần nhỏ hơn 1 cent. Hợp đồng ví dụ **không làm tròn**.
- `"10000.001"` mét tương ứng 10.000.001 mm, vượt giới hạn 10.000.000 mm nên bị từ chối.
- `"-1.00"` bị từ chối do miền không cho phép giá âm, mặc dù `long` hoàn toàn biểu diễn được -100.
- Biểu thức `(long) Integer.MAX_VALUE + 1` chuyển sang `long` **trước phép cộng**, vì vậy không tràn `int`.

Chương trình này dùng `record` có từ Java 16, tương thích Java 17+. Nó cố ý không chứa mã tiền tệ hoặc quy tắc quy đổi tỷ giá vì hợp đồng ví dụ giả định **một loại tiền đã được thống nhất**. Nếu ứng dụng xử lý nhiều tiền tệ, kiểu giá phải gắn rõ mã tiền tệ và không cho phép cộng trực tiếp khác mã khi chưa có quy tắc đổi.

## 8. Mô tả trường số trong API và tài liệu

Một đặc tả rõ ràng có thể được viết thành bảng để frontend, backend, kiểm thử và lưu trữ cùng sử dụng:

| Trường | Kiểu truyền | Ý nghĩa/đơn vị | Miền/độ phân giải | Khi không hợp lệ |
| --- | --- | --- | --- | --- |
| `quantity` | JSON integer | sản phẩm | 0–10.000, bước 1 | Trả lỗi miền |
| `timeoutMillis` | JSON integer | mili giây | 1–120.000, bước 1 | Trả lỗi miền |
| `distanceMillimeters` | JSON integer | milimét | 0–10.000.000, bước 1 | Trả lỗi miền |
| `priceMinorUnits` | JSON integer hoặc chuỗi số nếu client cần độ chính xác 64 bit | đơn vị nhỏ của một đồng tiền đã xác định | 0–100.000.000, bước 1 | Trả lỗi miền |
| `discountBasisPoints` | JSON integer | basis point | 0–10.000, bước 1 (= 0,01%) | Trả lỗi miền |
| `massKg` | chuỗi số decimal | kilôgam | 0–1.000, bước 0,001 kg | Từ chối số quá chi tiết |

Mọi miền ví dụ đều **bao gồm hai đầu biên**. Nếu chọn JSON string để bảo toàn số nguyên lớn, tài liệu API phải ghi **kiểu dữ liệu thực tế** là chuỗi và định nghĩa định dạng hợp lệ; không được ghi JSON integer rồi âm thầm trả chuỗi.

Ví dụ JSON minh họa một đối tượng số lượng và thời gian:

```json
{
  "quantity": 12,
  "timeoutMillis": 5000,
  "distanceMillimeters": 1250
}
```

Tài liệu phải nói rõ `distanceMillimeters: 1250` là 1,25 mét, không phải 1.250 mét. Trường có hậu tố đơn vị thường giảm nhầm lẫn đáng kể khi tích hợp.

Nếu có trường nullable, cần ghi rõ cách diễn giải: `null` là “không biết” hay “không áp dụng”, nó có bị từ chối ở request hay được giữ lại trong database, và **không** dùng `0` hoặc `-1` làm sentinel tùy tiện nếu những giá trị này có thể hợp lệ. Một trường hợp khác là **giá trị không đo được**; có thể cần kiểu trạng thái riêng để phân biệt `NOT_MEASURED`, `UNAVAILABLE` và giá trị số thực.

## 9. Kiểm tra giá trị ở đúng ranh giới

Ràng buộc dữ liệu nên xuất hiện ở nơi tạo/nhận giá trị từ bên ngoài: khi parse request, tạo value object, chuyển đổi đơn vị hoặc ghi xuống kho dữ liệu.

Một chuỗi xử lý thường hợp lý:

1. **Nhận đầu vào:** xác định loại dữ liệu, đơn vị, locale và quy tắc thiếu giá trị.
2. **Parse không làm mất chính xác:** ưu tiên `BigDecimal(String)` cho dữ liệu decimal; tránh đi qua `double` nếu cần decimal chính xác.
3. **Chuyển về đơn vị chuẩn:** nhân/chia theo hệ số xác định bằng arithmetic phù hợp; kiểm tra độ phân giải và làm tròn nếu hợp đồng có cho phép.
4. **Kiểm tra miền:** min/max và các ràng buộc của nghiệp vụ; thất bại rõ khi không hợp lệ.
5. **Lưu trữ và xử lý:** giữ nguyên đơn vị chuẩn; không lặp đi lặp lại chuyển đổi bằng những quy tắc khác nhau.
6. **Trả dữ liệu:** phản ánh đúng đơn vị và độ chính xác; cập nhật API schema tương ứng.

`Objects.requireNonNull` dùng khi trường bắt buộc; với đầu vào không hợp lệ từ người dùng, API có thể chuyển lỗi parse/miền sang một mã lỗi có cấu trúc như `INVALID_FORMAT`, `OUT_OF_RANGE`, `INVALID_PRECISION`, `UNSUPPORTED_UNIT`. Không dựa vào thông báo nguyên văn của JDK làm hợp đồng công khai vì thông báo có thể thay đổi.

Đối với đối tượng bất biến, đưa kiểm tra vào constructor/factory giúp tránh tạo trạng thái không hợp lệ. Nhưng vẫn nên có xác thực ở API boundary để trả về thông báo dễ hiểu thay vì để lỗi lan sâu.

## 10. Những quyết định dễ bị bỏ sót

### Không dựa vào tên kiểu nguyên thủy để suy ra đại lượng

`long` không có nghĩa là “mili giây”, cũng không có nghĩa là “giá tiền lớn”. Nếu nhiều tầng dùng cùng một `long` cho quãng đường, thời gian và số tiền, cần tên trường, value object hoặc schema làm rõ sự khác biệt.

### Không tự xem `null` là 0

`0` có thể là dữ liệu hợp lệ; `null` có thể là thiếu dữ liệu. Một model có thể quy định giá tối thiểu là 0, đồng thời một trường giá nhập chưa được cung cấp là không hợp lệ hoặc chưa xác định. Tài liệu cần nói rõ.

### Không đồng nhất “hai số như nhau” với “hai chuỗi biểu diễn như nhau”

Với `BigDecimal`, `"1.0"` và `"1.00"` có cùng giá trị số nhưng khác `scale`. `compareTo` trả 0, còn `equals` trả `false`. Nếu scale hoặc số chữ số thập phân là một phần của dữ liệu, quy tắc equality phải được mô tả rõ; nếu chỉ cần số học, tránh vô tình dùng `equals` để quyết định hai số tiền khác nhau.

### Không làm tròn mà không có hợp đồng

Một API chấp nhận giá `"1.234"` rồi âm thầm biến thành `"1.23"` có thể khác với yêu cầu từ chối độ phân giải không hỗ trợ. Quy tắc làm tròn cần định nghĩa cả rounding mode, thời điểm làm tròn và đơn vị đích.

### Không chấp nhận mọi giá trị `double` theo mặc định

`Double.NaN`, `Double.POSITIVE_INFINITY` và `Double.NEGATIVE_INFINITY` có thể truyền qua kiểu `double`, dù một đại lượng nghiệp vụ yêu cầu số hữu hạn. Có thể dùng `Double.isFinite(value)` khi hợp đồng chỉ nhận số hữu hạn, đồng thời kiểm tra min/max phù hợp. Với tiền tệ decimal chính xác, dùng kiểu dữ liệu decimal thích hợp.

### Không trông chờ database tự thay thế quy tắc nghiệp vụ

Kiểu SQL xác định miền biểu diễn, nhưng giới hạn số lượng, đơn vị hoặc “tỷ lệ không vượt 100%” cần được xác minh trong ứng dụng và/hoặc ràng buộc database. Không nên để frontend, backend và database mỗi nơi chọn một biên khác nhau.

## 11. Bộ kiểm thử hợp đồng số

Một bộ kiểm thử có giá trị cần thử **tại biên và ngoài biên**, thay vì chỉ dùng các giá trị bình thường. Với trường `quantity` từ 0 đến 10.000:

| Giá trị | Kỳ vọng |
| --- | --- |
| `0` | Hợp lệ nếu biên dưới được bao gồm |
| `1` | Hợp lệ |
| `10_000` | Hợp lệ nếu biên trên được bao gồm |
| `-1` | Bị từ chối |
| `10_001` | Bị từ chối |
| `null` | Theo hợp đồng bắt buộc/nullable |
| `"1.5"` | Bị từ chối nếu chỉ nhận số nguyên |

Với trường có đơn vị và độ phân giải, thử thêm: `1.250 m` → 1.250 mm; `0.0005 m` → từ chối nếu không được làm tròn; 10.000 m là biên tối đa và 10.000,001 m vượt giới hạn. Với tiền 2 chữ số decimal: thử `"0"`, `"0.01"`, `"1000000.00"`, `"1000000.01"`, `"-0.01"` và `"1.234"`. Kiểm tra cả phép tính trung gian (cộng/nhân vượt `int`, `long`), chuyển sang kiểu nhỏ hơn và serialize đến client JavaScript.

Nếu yêu cầu “tổng cuối phải nằm trong phạm vi” khác với “không phép cộng trung gian nào được vượt phạm vi”, cần kiểm thử trường hợp các số dương và âm triệt tiêu nhau. Điều này giúp khẳng định chính xác hợp đồng thay vì chỉ dựa vào tình cờ của cách triển khai.

## 12. Checklist dùng cho mọi trường số mới

Trước khi phát hành một trường số trong API hay lưu trữ, trả lời được:

- **Nó đo/cố định đại lượng gì?** Đây là số lượng, thời gian, tiền hay mã định danh (mã định danh dạng số chưa chắc thích hợp cho arithmetic)?
- **Đơn vị là gì?** Tên trường và tài liệu có thể hiện cùng một đơn vị chuẩn không? Nếu có chuyển đổi, quy tắc là gì?
- **Giá trị nhỏ nhất/lớn nhất hợp lệ là bao nhiêu?** Biên đóng hay mở, có cho phép âm hoặc 0 không?
- **Độ phân giải và scale là gì?** Có được làm tròn không và dùng quy tắc nào?
- **Giá trị thiếu có nghĩa gì?** `null`, trường vắng mặt, số 0 và sentinel có bị lẫn nhau không?
- **Phép tính trung gian có an toàn không?** Nâng kiểu trước cộng/nhân; dùng kiểm tra exact hoặc `BigInteger` khi cần.
- **Các lớp có hiểu giống nhau không?** Java, JSON/client, SQL, CSV và tài liệu có thống nhất đơn vị, biên, precision và cách xử lý lỗi không?
- **Kiểm thử biên đã có chưa?** Gồm biên, ngoài biên, chuyển đổi có phần dư, overflow và serializing giá trị lớn.

**Thông điệp chính:** Kiểu dữ liệu nói “máy tính lưu giá trị như thế nào”; hợp đồng số còn phải nói **giá trị nào hợp lệ, nó mang đơn vị gì, chính xác tới đâu, và khi vượt giới hạn thì hệ thống làm gì**. Ghi rõ các điều đó từ đầu giúp tránh lỗi âm thầm trong tính toán, API và lưu trữ.

### Tài liệu tham khảo Java SE 21

- [`Integer` và giới hạn kiểu `int`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html)
- [`Long` và giới hạn kiểu `long`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Long.html)
- [`BigDecimal`: scale, precision, conversion exact](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
- [`Math`: addExact, multiplyExact, toIntExact](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html)
- [`Duration`: biểu diễn và chuyển đổi thời lượng](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Duration.html)