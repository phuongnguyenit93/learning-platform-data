# Chọn kiểu số trong Java theo ý nghĩa dữ liệu và yêu cầu tính toán

Một chương trình có thể biên dịch và chạy mà vẫn tính **sai về nghiệp vụ** nếu chọn kiểu số không phù hợp. Câu hỏi đầu tiên không phải “nên dùng `int` hay `double`?”, mà là: **giá trị này đại diện cho điều gì, được phép nhận những giá trị nào, phép tính nào sẽ thực hiện và thế nào được coi là đúng?**

Trong module **Java core – numbers**, bài học này xây dựng quy trình ra quyết định để chọn `byte`, `short`, `int`, `long`, `float`, `double`, `BigInteger`, `BigDecimal`, hoặc một kiểu **không phải số** khi dữ liệu chỉ trông giống số. Mục tiêu là lựa chọn có giải thích và có thể kiểm chứng, không chỉ ghi nhớ bảng phạm vi kiểu dữ liệu.

## 1. Bốn câu hỏi cần trả lời trước khi chọn kiểu

### Câu hỏi 1: Dữ liệu thực sự mang ý nghĩa gì?

Phân biệt **đại lượng** dùng để tính toán với **mã định danh** dùng để nhận diện:

- **Số lượng rời rạc**: số học viên, số kiện hàng, lượt truy cập, số byte → số nguyên.
- **Giá trị đo liên tục**: nhiệt độ cảm biến, tọa độ vật lý, vận tốc → thường có thể dùng `double` nếu chấp nhận sai số nhị phân.
- **Số thập phân phải tuân thủ quy tắc nghiệp vụ**: đơn giá, thuế, tiền, tỷ lệ phân bổ, điểm theo thang thập phân → thường cần `BigDecimal` hoặc số nguyên biểu diễn đơn vị nhỏ nhất.
- **Mã nhận diện**: mã bưu chính `"00123"`, số điện thoại, mã khách hàng `"000042"`, số tài khoản, số thẻ, mã hàng → thường là `String`. Những giá trị này không có ý nghĩa cộng, trừ và có thể chứa số 0 đầu.
- **Thời gian và khoảng thời gian**: thời điểm sự kiện, ngày giao hàng, hạn xử lý → thường dùng `Instant`, `LocalDate`, `Duration` hoặc kiểu `java.time` phù hợp thay vì tự chọn một con số không rõ đơn vị.

**Phản ví dụ:** đặt `int postalCode = 00123;` vừa làm mất các số 0 đầu vừa có thể vướng cú pháp literal bát phân. Đúng theo ý nghĩa dữ liệu sẽ là `String postalCode = "00123";`. Tương tự, một ID có toàn chữ số vẫn không tự động là đại lượng toán học.

### Câu hỏi 2: Miền giá trị và mức tăng trưởng là bao nhiêu?

Xác định giá trị nhỏ nhất, lớn nhất, có âm không, có thể tăng trong bao lâu, và **các giá trị trung gian** có lớn hơn kết quả cuối không.

Ví dụ, số lượng sản phẩm trong giỏ hàng có thể phù hợp `int`; tổng số byte xử lý trong một dịch vụ chạy nhiều năm có thể cần `long`; một bộ đếm tổ hợp toán học có thể vượt `long`, cần `BigInteger`.

Đừng chỉ dựa vào dữ liệu hiện tại. Hãy hỏi cả “3 năm sau thì sao?”, “cộng 10.000 đối tượng thì sao?” và “nhân hai số lớn thì sao?”. Biên độ an toàn là yêu cầu thiết kế, không phải lý do bỏ qua kiểm tra tràn số.

### Câu hỏi 3: Yêu cầu chính xác được định nghĩa thế nào?

Ba mục tiêu khác nhau dẫn đến lựa chọn khác nhau:

1. **Chính xác tuyệt đối cho số nguyên:** `int`, `long` trong phạm vi; `BigInteger` khi phạm vi có thể vượt 64 bit.
2. **Gần đúng có sai số kiểm soát:** `double` hoặc `float` cho bài toán số học nhị phân, đo lường, mô phỏng, thống kê; quy định sai số theo ngữ cảnh.
3. **Chính xác theo hệ thập phân với cách làm tròn quy định:** `BigDecimal` cho các giá trị thập phân nghiệp vụ. “Chính xác” ở đây không có nghĩa phép chia vô hạn như `1/3` tự được biểu diễn hoàn toàn; phải chỉ định scale/precision và rounding khi cần.

Một giá trị có dấu phẩy thập phân không tự động yêu cầu `BigDecimal`: phép đo nhiệt độ `23.7°C` có thể phù hợp `double`; số tiền `23.70` thường phải có quy tắc thập phân chặt chẽ.

### Câu hỏi 4: Những phép toán và biên trao đổi dữ liệu nào tham gia?

Kiểu được chọn còn phụ thuộc vào:

- Phép toán: chỉ lưu/hiển thị, cộng trừ, nhân chia, lũy thừa, so sánh, sắp xếp, tổng hợp, làm tròn.
- Luồng dữ liệu: giá trị đến từ JSON, CSV, cơ sở dữ liệu, API, cảm biến, người dùng nhập hay một phép đo đã lượng tử hóa.
- Phần mềm nhận kết quả: một số `long` không thể được giữ chính xác trong JavaScript khi truyền như JSON number; phía nhận có thể cần chuỗi hoặc giao thức số nguyên an toàn.
- Quy ước miền: đơn vị (`ms`, `s`, `bytes`, `kg`), dấu âm, scale thập phân, mức làm tròn, giới hạn hợp lệ, cách biểu diễn giá trị thiếu.

## 2. Bảng quyết định: chọn theo mục đích

| Ý nghĩa dữ liệu / yêu cầu | Lựa chọn nên ưu tiên | Vì sao | Điều cần kiểm tra |
| --- | --- | --- | --- |
| Số lượng nhỏ, chỉ số vòng lặp/mảng | `int` | Thuận tiện, nhiều API Java sử dụng `int` | Không âm khi miền yêu cầu; không tràn khi cộng/nhân |
| Bộ đếm/tổng dung lượng có thể vượt 2,1 tỷ | `long` | Miền 64 bit rộng hơn `int` | Tràn vẫn có thể xảy ra; đọc/ghi API hoặc CSDL nhất quán |
| Số nguyên vượt giới hạn `long` | `BigInteger` | Không cố định độ rộng 64 bit | Hiệu năng, bộ nhớ, giới hạn đầu vào |
| Giá trị thực đo, mô phỏng, xác suất gần đúng | `double` | Dải động và độ chính xác tốt hơn `float` | Sai số tuyệt đối/tương đối; NaN, vô cực |
| Dữ liệu `float` được yêu cầu rõ bởi API/bộ nhớ/mô hình | `float` | Tương thích định dạng 32 bit, có thể tiết kiệm bộ nhớ trong mảng lớn | Chỉ khoảng 6–7 chữ số thập phân có nghĩa |
| Đơn giá, tiền, thuế, lãi suất thập phân theo quy tắc nghiệp vụ | `BigDecimal` | Thập phân hữu hạn được biểu diễn đúng nếu khởi tạo đúng | Scale, rounding, currency, thời điểm làm tròn |
| Số tiền đã quy đổi sang đơn vị nhỏ nhất và có giới hạn rõ | `long` | Phép cộng/trừ nguyên chính xác trong miền | Đơn vị tiền, chính sách chuyển đổi/phân chia |
| Cờ trạng thái đúng/sai | `boolean` | Biểu diễn đúng miền logic | Không dùng 0/1 khi không cần |
| Mã bưu chính, điện thoại, số thẻ, mã có số 0 đầu | `String` | Mã định danh, không phải đại lượng | Giữ nguyên ký tự/độ dài; bảo vệ dữ liệu nhạy cảm |
| Ngày, thời điểm, khoảng thời gian | `java.time` phù hợp | Có ngữ nghĩa thời gian rõ ràng | Múi giờ, lịch, đơn vị, UTC so với giờ địa phương |

`byte` và `short` có vai trò khi giao tiếp nhị phân, cấu trúc lưu trữ hoặc API yêu cầu đúng bề rộng 8/16 bit. Với phép đếm và tính toán thông thường, `int` thường dễ dùng hơn dù giá trị hiện tại nhỏ: biểu thức số học trên `byte`/`short` vẫn hay được nâng lên `int`. Không lựa chọn `byte` chỉ vì “số nhỏ hơn 100”.

## 3. Quy trình quyết định có thể áp dụng lại

```text
Giá trị có phải đại lượng dùng để tính toán không?
├─ Không → String, boolean, enum, java.time hoặc kiểu miền riêng
└─ Có
   ├─ Giá trị bắt buộc là số nguyên?
   │  ├─ Có → Trong miền int?
   │  │        ├─ Có → int
   │  │        └─ Không → Trong miền long?
   │  │                     ├─ Có → long
   │  │                     └─ Không → BigInteger
   │  └─ Không
   │     ├─ Được phép sai số nhị phân có kiểm soát?
   │     │  ├─ Có → double (float nếu có yêu cầu cụ thể)
   │     │  └─ Không → BigDecimal hoặc số nguyên đã định đơn vị/scale
   │     └─ Phép chia/làm tròn → phải định nghĩa chính sách
   └─ Ở mọi nhánh: xác nhận miền dữ liệu, đơn vị, kiểm soát lỗi và
      cách bảo toàn giá trị khi lưu hoặc gửi qua API.
```

Sơ đồ là điểm khởi đầu; một kiểu số vẫn có thể không đạt yêu cầu nếu một phép tính trung gian tràn hoặc nếu lớp giao tiếp làm mất độ chính xác. Với bộ đếm có giá trị âm không hợp lệ, bạn vẫn phải kiểm tra `value >= 0`: `int` là kiểu **có dấu**, không tự ràng buộc miền nghiệp vụ.

## 4. Chọn số nguyên: phạm vi, tràn và kết quả trung gian

Các kiểu nguyên có dấu trong Java:

| Kiểu | Phạm vi | Gợi ý sử dụng |
| --- | --- | --- |
| `byte` (8 bit) | -128 đến 127 | Dữ liệu nhị phân hoặc giao thức định dạng 8 bit |
| `short` (16 bit) | -32.768 đến 32.767 | Tương thích cấu trúc 16 bit |
| `int` (32 bit) | -2.147.483.648 đến 2.147.483.647 | Số lượng và chỉ số thông thường |
| `long` (64 bit) | -9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 | Số nguyên lớn hơn `int` |
| `BigInteger` | Không bị giới hạn bởi số bit cố định | Toán học/số đếm rất lớn; giới hạn thực tế bởi bộ nhớ/tài nguyên |

**Cần xác định kiểu tại thời điểm thực hiện phép tính.** Trong ví dụ:

```java
int count = 1_500_000_000;

long wrong = count * 3;          // Nhân theo int rồi mới gán long: đã tràn.
long correct = (long) count * 3; // Nâng kiểu trước phép nhân: 4_500_000_000L.
long exact = Math.multiplyExact((long) count, 3L);
```

Đây là mảnh mã minh họa, không phải chương trình độc lập. Java không tự báo lỗi tràn cho các phép tính `int`/`long` thông thường. Dùng `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact`, `Math.toIntExact` khi tràn là điều không thể chấp nhận. Nếu không thể bảo đảm kết quả trong `long`, hãy chuyển hẳn phép tính sang `BigInteger`, thay vì ép kiểu kết quả đã tràn.

**Chia nguyên không giữ phần lẻ:**

```java
int completed = 7;
int groups = 2;
int each = completed / groups;            // 3
double average = (double) completed / groups; // 3.5
```

Nếu chia cho 0 bằng số nguyên, Java ném `ArithmeticException`. Với số đếm chính xác cần chia và cho ra phần lẻ, quyết định đó có ý nghĩa gì: có thể là tỉ lệ đo gần đúng (`double`), phép tính tỷ lệ nghiệp vụ (`BigDecimal`) hoặc quotient/remainder nguyên để phân bổ đơn vị còn dư.

**BigInteger:** tạo bằng `new BigInteger("9223372036854775808")`, dùng `add`, `multiply`, `divide`, `compareTo`. Đây là đối tượng bất biến; `value.add(BigInteger.ONE)` trả một đối tượng mới và không tự thay đổi `value`. Đừng kỳ vọng toán tử `+` hoạt động với hai đối tượng `BigInteger`.

Một lưu ý quan trọng: biểu diễn không dấu trong giao thức bên ngoài cần được xử lý rõ ràng. Các kiểu nguyên thông thường của Java đều có dấu; `Integer.toUnsignedLong`, `Long.compareUnsigned`, `Long.toUnsignedString` chỉ hỗ trợ **diễn giải/thao tác không dấu trên bit hiện có**, không biến `long` thành kiểu có phạm vi nguyên dương tùy ý. Với giá trị unsigned 64 bit đầy đủ, cân nhắc `BigInteger` ở lớp xử lý miền khi cần một giá trị toán học không âm vượt `Long.MAX_VALUE`.

## 5. Chọn số thực: sai số và tiêu chí kiểm chứng

`float` và `double` là số dấu phẩy động **nhị phân**. Chúng có thể xấp xỉ nhiều giá trị thập phân nhưng không giữ đúng mọi phân số như `0.1`. Với phép đo có nhiễu và mô hình vật lý, sai số số học có thể là một phần hợp lý của bài toán; với tiền bạc, sai số đó thường không phù hợp.

```java
double measuredTemperature = 23.75;
double a = 0.1;
double b = 0.2;
boolean exactSame = (a + b == 0.3); // false
```

Hai điều cần tránh:

1. Không dùng `==` với hai kết quả tính thực khi mục đích là hỏi “đủ gần nhau hay không”. Xác định sai số theo đơn vị và độ lớn, có thể kết hợp ngưỡng tuyệt đối và tương đối; ngưỡng thích hợp với nhiệt độ có thể vô nghĩa với khoảng cách thiên văn.
2. Không cho rằng `double` có “15 chữ số sau dấu phẩy”. Nó có khoảng 15–16 chữ số **có nghĩa**; độ phân giải phụ thuộc độ lớn. `float` thường chỉ có khoảng 6–7 chữ số thập phân có nghĩa.

`NaN`, `Infinity` và `-Infinity` tồn tại trong dấu phẩy động. Chúng không phải dữ liệu đo lường hợp lệ trong mọi miền; cần kiểm tra `Double.isFinite(value)` trước khi ghi hoặc truyền vào các phép tính yêu cầu giá trị hữu hạn. `Double.isNaN` xác định NaN; `NaN == NaN` là `false`. Một số phép chia dấu phẩy động cho 0 trả giá trị vô cực hoặc NaN, khác với chia nguyên cho 0.

**Khi nào chọn `float`?** Chỉ khi giao thức, thư viện, định dạng tệp, mảng số rất lớn hoặc mô hình tính toán cho phép độ chính xác 32 bit và có lợi ích xác định. Trong Java, literal `1.5` mặc định là `double`; viết `1.5f` cho `float`. Đừng chuyển `double` sang `float` chỉ vì giá trị in ra trông giống nhau; độ chính xác có thể mất.

## 6. Chọn số thập phân chính xác: BigDecimal và chính sách làm tròn

`java.math.BigDecimal` biểu diễn giá trị hữu hạn bằng **hệ số nguyên × 10^(-scale)**. Giá trị từ chuỗi `"19.95"` là thập phân chính xác; không mắc sai số biểu diễn của literal `double`.

```java
BigDecimal price = new BigDecimal("19.95");
BigDecimal quantity = BigDecimal.valueOf(3L);
BigDecimal subtotal = price.multiply(quantity); // 59.85
```

Mảnh mã trên cần `import java.math.BigDecimal;` và đặt trong phương thức. Các thao tác với `BigDecimal` trả đối tượng mới: phải giữ kết quả của `add`, `multiply`, `setScale`…

### 6.1. Khởi tạo từ đúng nguồn

Nên ưu tiên `new BigDecimal("0.1")` nếu nguồn là biểu diễn thập phân. Tránh `new BigDecimal(0.1)` khi ý định là **đúng một phần mười**, vì constructor nhận chính giá trị nhị phân của `double` và tạo một biểu diễn thập phân chính xác cho giá trị nhị phân đó. `BigDecimal.valueOf(0.1)` sử dụng chuỗi thập phân chuẩn của `double` và cho `0.1` trong ví dụ này, nhưng không thể sửa lỗi đã phát sinh từ phép tính `double` trước đó.

### 6.2. Precision, scale, rounding là ba quyết định khác nhau

- **Scale** là số vị trí thập phân trong biểu diễn: `12.340` có scale 3.
- **Precision** là số chữ số có nghĩa theo biểu diễn `BigDecimal`: `12.340` có precision 5.
- **RoundingMode** quyết định cách bỏ chữ số khi phải giảm độ chi tiết. `HALF_UP`, `HALF_EVEN`, `DOWN`, `CEILING` không tương đương nhau, đặc biệt với số âm và giá trị ở điểm giữa.

```java
BigDecimal amount = new BigDecimal("12.345");
BigDecimal rounded = amount.setScale(2, RoundingMode.HALF_UP); // 12.35

BigDecimal oneThird = BigDecimal.ONE.divide(
        new BigDecimal("3"), 4, RoundingMode.HALF_EVEN); // 0.3333
```

Mảnh mã cần `import java.math.RoundingMode;`. Nếu gọi `BigDecimal.ONE.divide(new BigDecimal("3"))` mà không cung cấp điều kiện làm tròn, phép chia không kết thúc sẽ ném `ArithmeticException`. Khi dùng `MathContext`, precision là **số chữ số có nghĩa** cho phép tính, không phải số vị trí sau dấu phẩy. Bài toán tiền thường còn cần đặt scale sau những bước nhất định.

### 6.3. Hai giá trị bằng nhau nhưng scale khác nhau

`new BigDecimal("2.0").equals(new BigDecimal("2.00"))` là `false`, vì `equals` có xét scale. `compareTo` trả `0`, vì so giá trị toán học. Cần chọn chủ ý theo nghiệp vụ: cùng số tiền có thể được coi là cùng **giá trị**, trong khi định dạng hiển thị vẫn cần giữ 2 chữ số thập phân.

### 6.4. Tiền dùng BigDecimal hay long?

Có hai cách thiết kế hợp lý nếu hợp đồng dữ liệu nêu đủ đơn vị:

- **`BigDecimal` theo đơn vị tiền chính**: ví dụ `19.95` USD, thao tác bằng thập phân, quy tắc scale/rounding rõ.
- **`long` theo đơn vị nhỏ nhất**: ví dụ `1995` cent, cộng và trừ nguyên; phải kiểm soát tràn và xác định phép chia/phân bổ số cent dư. Không được giả định mọi loại tiền tệ đều có 2 chữ số thập phân.

Nếu tính thuế, giảm giá, tỷ giá, lãi suất hoặc phân bổ, cần quy định **làm tròn ở mỗi dòng hay sau khi cộng tổng**. Hai thứ tự có thể cho kết quả khác nhau dù đều dùng `BigDecimal`. Một kiểu dữ liệu chính xác không thay thế quy tắc kế toán.

## 7. Ranh giới kiểu: null, boxing, lưu trữ và giao tiếp

### 7.1. Primitive hay wrapper?

- `int` là giá trị nguyên thủy, không thể là `null`. `Integer` là đối tượng có thể biểu diễn `null` trong API/DTO, và là kiểu tham số của `List<Integer>`.
- `long`/`Long`, `double`/`Double` có quan hệ tương tự. Boxing/unboxing diễn ra tự động trong nhiều ngữ cảnh, nhưng unboxing `null` sẽ gây `NullPointerException`.
- Nếu “chưa nhập” khác “bằng 0”, hãy mô hình hóa sự khác biệt rõ ràng bằng wrapper hoặc một đối tượng miền thích hợp. Không chọn `Integer` chỉ để có `null` nếu miền bắt buộc có giá trị và điều đó làm code dễ lỗi.

```java
Integer optionalScore = null;
// int score = optionalScore; // Nếu thực hiện sẽ ném NullPointerException.
```

So sánh wrapper bằng `equals` khi cần so **giá trị đối tượng**, thay vì phụ thuộc `==` vốn so tham chiếu giữa hai wrapper (và có trường hợp cache khiến kết quả gây nhầm lẫn). Kiểm tra `null` trước khi unboxing.

### 7.2. API và database có thể thay đổi quyết định

Một kiểu Java phải tương thích với môi trường lưu trữ. Khi ghi xuống database, kiểm tra giới hạn `INTEGER`/`BIGINT`, `DECIMAL(p,s)`, kiểu của driver, schema migration và ràng buộc nghiệp vụ. Ví dụ `DECIMAL(10,2)` quy định tối đa 10 chữ số tổng cộng và 2 chữ số sau dấu phẩy; kiểu này không tự bao trùm mọi `BigDecimal` mà ứng dụng có thể tạo.

Với JSON/JavaScript, các số nguyên có độ lớn hơn `2^53 - 1` có thể không được giữ chính xác trong kiểu `Number` của JavaScript. Một `long` hợp lệ phía Java không bảo đảm an toàn khi xuất trực tiếp thành JSON number để JavaScript tiêu thụ. Có thể thiết kế JSON string cho mã/số nguyên lớn, hoặc thỏa thuận rõ bộ giải mã `BigInt` ở bên nhận.

Với số thập phân chính xác, phải chắc rằng tầng JSON/parser không chuyển qua `double` rồi mới đưa vào `BigDecimal`. Truyền định dạng thập phân dưới dạng string khi giao thức yêu cầu bảo toàn nguyên văn hoặc quy tắc serialisation của cả hai phía đã được kiểm chứng.

### 7.3. Đơn vị phải đi theo dữ liệu

`long timeout = 5000;` không cho biết 5000 mili giây, giây hay nano giây. Trong code thực tế, dùng `Duration.ofSeconds(5)` hoặc tên `timeoutMillis` khi API phải nhận số nguyên. Tương tự, không cộng `distanceMeters` với `distanceKilometers` mà chưa quy đổi; cân nhắc định nghĩa class/record miền hoặc API nhận đơn vị rõ.

Một hệ thống có thể chọn `long` đúng về miền giá trị nhưng vẫn sai nếu cộng số cent với số đồng. **Kiểu nguyên thủy không mang đơn vị**, nên trách nhiệm bảo toàn đơn vị nằm ở thiết kế miền, tên biến, validation và hợp đồng API.

## 8. Những phép chuyển đổi dễ làm mất ý nghĩa

| Chuyển đổi hoặc biểu thức | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| `long` → `int` bằng cast | Cắt các bit cao, đổi giá trị | `Math.toIntExact(value)` hoặc kiểm tra miền trước |
| `int * int` → gán `long` | Nhân theo `int` rồi mới gán, có thể tràn | Nâng ít nhất một toán hạng lên `long` trước nhân |
| `long` → `double` | Không phải mọi `long` đều biểu diễn chính xác | Tránh với định danh/bộ đếm đòi hỏi exactness |
| `double` → `int` | Bỏ phần lẻ theo hướng 0; ngoài miền và NaN có quy tắc cast đặc biệt | Kiểm tra `Double.isFinite`, miền và chính sách làm tròn |
| `double` → `BigDecimal` | Dữ liệu có thể đã bị làm tròn nhị phân | Lấy chuỗi thập phân gốc; nếu nguồn là double, hiểu semantics của `valueOf` |
| `BigDecimal` → `double` | Có thể mất precision hoặc vượt miền | Chỉ thực hiện khi ứng dụng chấp nhận xấp xỉ |
| `BigDecimal` → `int`/`long` | `intValue`/`longValue` có thể bỏ phần lẻ hoặc mất bit | Dùng `intValueExact()`/`longValueExact()` khi cần chính xác |
| `int / int` → gán `double` | Phép chia đã bỏ phần lẻ | Cast một toán hạng trước phép chia |
| `String` chứa số có dấu phẩy theo locale → parser chuẩn | `NumberFormatException` hoặc hiểu sai dấu | Tách quy tắc nhập/hiển thị khỏi biểu diễn số chuẩn |
| `Integer` là `null` → `int` | `NullPointerException` khi unboxing | Validation trước unboxing hoặc thiết kế không-null |

Không phải mọi giá trị `long` đều biểu diễn chính xác bằng `double`, dù cả hai đều là 64 bit: `double` dành nhiều bit cho dấu và số mũ, nên số bit có nghĩa hữu hạn. Điều này đặc biệt nguy hiểm khi biến mã số lớn thành số thực để “tiện xử lý”.

## 9. Ví dụ tình huống: quyết định cho từng trường dữ liệu

Giả sử xây một dịch vụ xử lý đơn hàng và thống kê thiết bị:

| Trường | Kiểu đề xuất | Lập luận |
| --- | --- | --- |
| `orderCode = "0000157"` | `String` | Định danh, giữ số 0 đầu, không tính toán |
| `quantity = 3` | `int` | Đếm sản phẩm; kiểm tra `quantity >= 0` và mức tối đa theo nghiệp vụ |
| `processedBytes = 5_000_000_000` | `long` | Vượt `Integer.MAX_VALUE`; có đơn vị byte |
| `temperatureCelsius = 23.75` | `double` | Phép đo có thể chấp nhận sai số nhị phân |
| `unitPrice = "19.95"` | `BigDecimal` | Đơn giá thập phân chính xác |
| `taxRate = "0.08"` | `BigDecimal` | Tỷ lệ tính tiền theo quy tắc làm tròn |
| `globalSequence` vượt `long` | `BigInteger` (nếu cần tính toán) hoặc `String` (nếu chỉ định danh) | Ý nghĩa quyết định kiểu, không chỉ độ dài |
| `deadline` | `Instant` | Mốc thời gian; có ngữ nghĩa rõ hơn số milliseconds trần |

**Điểm cần phân biệt:** `globalSequence` nếu chỉ được gửi qua API như một mã định danh có thể phù hợp `String`; nếu là số nguyên cần tăng, so sánh số học, cộng trừ vượt 64 bit thì cần `BigInteger`. Cùng một chuỗi ký tự chứa toàn chữ số nhưng quyết định khác nhau vì hành vi nghiệp vụ khác nhau.

## 10. Chương trình Java 17+ hoàn chỉnh: biến yêu cầu thành lựa chọn kiểu

Lưu file **`NumericTypeChoices.java`**. Chương trình minh họa cách giữ mã định danh dưới dạng chuỗi, dùng `long` cho số byte lớn, `double` cho một phép đo, `BigInteger` cho số nguyên rất lớn, `BigDecimal` cho tiền, và kiểm tra tràn bằng `Math.multiplyExact`. Trong ví dụ hóa đơn, để minh họa quy tắc nghiệp vụ, thuế được làm tròn đến hai chữ số thập phân theo `HALF_UP` trước khi cộng vào tổng.

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

public class NumericTypeChoices {
    public static void main(String[] args) {
        String orderCode = "0000157";
        int quantity = 3;
        long processedBytes = 5_000_000_000L;
        double temperatureCelsius = 23.75;

        BigInteger globalSequence =
                new BigInteger("9223372036854775808");

        BigDecimal unitPrice = new BigDecimal("19.95");
        BigDecimal taxRate = new BigDecimal("0.08");
        BigDecimal subtotal =
                unitPrice.multiply(BigDecimal.valueOf(quantity));
        BigDecimal tax = subtotal.multiply(taxRate)
                .setScale(2, RoundingMode.HALF_UP);
        BigDecimal total = subtotal.add(tax);

        long checkedProduct =
                Math.multiplyExact(1_500_000_000L, 3L);

        System.out.println("order-code=" + orderCode);
        System.out.println("quantity=" + quantity);
        System.out.println("processed-bytes=" + processedBytes);
        System.out.println("temperature-c=" + temperatureCelsius);
        System.out.println("sequence=" + globalSequence);
        System.out.println("subtotal=" + subtotal);
        System.out.println("tax=" + tax);
        System.out.println("total=" + total);
        System.out.println("checked-product=" + checkedProduct);
    }
}
```

Biên dịch và chạy:

```bash
javac NumericTypeChoices.java
java NumericTypeChoices
```

Kết quả stdout chính xác:

```text
order-code=0000157
quantity=3
processed-bytes=5000000000
temperature-c=23.75
sequence=9223372036854775808
subtotal=59.85
tax=4.79
total=64.64
checked-product=4500000000
```

Kiểm tra phép tính: `19.95 × 3 = 59.85`; `59.85 × 0.08 = 4.788`; theo `HALF_UP` ở scale 2 thành `4.79`; tổng là `64.64`. Đây là quy tắc được **chọn riêng cho ví dụ**, không khẳng định mọi hóa đơn hoặc mọi loại tiền tệ đều làm tròn theo cách này.

Ví dụ cho thấy cùng một chương trình cần nhiều kiểu vì mỗi trường có vai trò khác nhau. Việc dùng một kiểu duy nhất cho mọi trường sẽ gây mất ngữ nghĩa hoặc tạo thêm rủi ro không cần thiết.

## 11. Kỹ thuật thiết kế và kiểm thử sau khi chọn kiểu

Sau khi quyết định kiểu, nên ghi lại các điều kiện bảo đảm tính đúng đắn trong hợp đồng dữ liệu:

1. **Miền hợp lệ:** Có được âm không? Có được 0 không? Giá trị tối đa? Chấp nhận `null` không?
2. **Đơn vị:** Byte, milli giây, kilogram, USD hay cent? Đơn vị đã được quy đổi trước phép toán chưa?
3. **Chính xác:** Kết quả bắt buộc chính xác nguyên/thập phân hay chỉ gần đúng? Nếu gần đúng, sai số hợp lệ được đo như thế nào?
4. **Chia và làm tròn:** Khi nào thực hiện? Scale bao nhiêu? `RoundingMode` nào? Có chính sách khi số không chia hết không?
5. **Tràn số:** Có kiểm tra trước/sau phép nhân và phép cộng, sử dụng phép `Exact`, hoặc chuyển sang `BigInteger` chưa?
6. **Đường đi dữ liệu:** Kiểu ở Java, JSON, JavaScript, database và CSV có bảo toàn cùng giá trị/đơn vị không?
7. **Giá trị thiếu/không hợp lệ:** `null`, chuỗi rỗng, NaN/vô cực, chữ số quá dài, số âm ngoài quy tắc được xử lý ra sao?

Các trường hợp kiểm thử quan trọng thường nằm ở **biên**, không phải ví dụ bình thường:

| Kiểm thử | Mục đích |
| --- | --- |
| `Integer.MAX_VALUE + 1` với `Math.addExact` | Phát hiện tràn thay vì nhận giá trị quay vòng |
| Nhân hai số `int` lớn và so kết quả khi nâng lên `long` trước nhân | Bắt lỗi tràn ở biểu thức trung gian |
| `BigDecimal.ONE.divide(new BigDecimal("3"))` | Xác nhận chính sách chia số thập phân không kết thúc |
| `0.1 + 0.2` và so gần đúng với `0.3` | Bắt giả định sai về `double` |
| `new BigDecimal("2.0")` so với `"2.00"` | Phân biệt so giá trị và so biểu diễn |
| Giá trị `long` trên `2^53 - 1` đi qua JSON/JavaScript | Xác minh không mất tính chính xác khi trao đổi |
| Mã `"0000157"` qua lưu trữ/serialize/deserialize | Xác minh số 0 đầu và định danh được bảo toàn |
| Thuế ở điểm giữa, giảm giá âm/dương và nhiều dòng hóa đơn | Xác minh đúng rounding rule và thời điểm làm tròn |
| `null` của wrapper trong DTO | Bắt unboxing ngoài ý muốn |
| Đơn vị mili giây so với giây | Bắt lỗi chuyển đổi đơn vị |

Đối với phép đo, hãy thử các giá trị 0, gần 0, cực lớn, NaN và vô cực tùy miền dữ liệu; tránh một dung sai tuyệt đối duy nhất cho mọi thang đo. Đối với tiền, chú trọng những giá trị mà rounding làm thay đổi kết quả và kết quả gộp nhiều dòng.

## 12. Bài tập áp dụng

**Bài 1 — Phân loại theo ngữ nghĩa.** Chọn kiểu Java cho mỗi trường và giải thích: `zipCode = "01234"`, `activeUserCount` tối đa 20 triệu, `totalBytes` tối đa 12 tỷ, `stockPrice = "123.4567"`, `sensorVoltage` đo gần đúng, `createdAt` là thời điểm UTC, `isEnabled` chỉ đúng/sai. Nêu kiểm tra hợp lệ và định dạng lưu trữ.

**Bài 2 — Tràn số có thể ẩn.** Viết phép tính số byte trung bình cho 3 tỷ bản ghi, biết mỗi bản ghi 4 byte; thử các biểu thức `int`, `long` và `Math.multiplyExact`. Giải thích kiểu toán hạng ở bước nhân quyết định kết quả ra sao.

**Bài 3 — Tiền và quy tắc kế toán.** Xây phương thức tính tổng cho đơn giá `"19.95"`, số lượng 3 và thuế 8%. Kiểm thử hai cách: làm tròn thuế từng dòng rồi cộng, hoặc cộng cơ sở thuế trước và làm tròn một lần. Viết ra quy tắc nào được yêu cầu trước khi chọn một kết quả.

**Bài 4 — Giao tiếp API.** Một dịch vụ Java trả `long id = 9_007_199_254_740_993L`. Đề xuất schema JSON giữ nguyên ID khi client JavaScript sử dụng `Number` theo mặc định. Giải thích vì sao ID nên được xem là mã nhận diện và kiểm tra bảo toàn khi round-trip.

**Bài 5 — Lựa chọn không hiển nhiên.** Một đo lường có 6 chữ số có nghĩa, dữ liệu gốc từ phần cứng `float32`; một chỉ số tài chính cũng có 6 chữ số nhưng cần tính lãi suất lặp nhiều kỳ. Chọn kiểu cho từng trường và lý giải tại sao “cùng số chữ số” không đủ để dùng cùng một kiểu.

## 13. Checklist quyết định trước khi đưa vào code thật

- Xác định giá trị là đại lượng, định danh hay ngày/giờ; không đánh đồng chữ số với kiểu số.
- Ghi miền min/max, có dấu, giá trị trung gian, chu kỳ tăng trưởng và đơn vị.
- Chọn `int`/`long`/`BigInteger` cho đại lượng nguyên theo phạm vi; kiểm soát overflow.
- Chọn `double` cho phép tính thực cho phép sai số; dùng `float` khi có yêu cầu rõ.
- Chọn `BigDecimal` hoặc số nguyên theo đơn vị nhỏ nhất cho nghiệp vụ thập phân chính xác; xác định scale và rounding.
- Làm rõ `null` và wrapper, không unbox khi chưa kiểm tra.
- Xác nhận kiểu và ý nghĩa được giữ nguyên qua API, JSON, CSV, database và các phép chuyển đổi.
- Kiểm thử cả biên, lỗi nhập liệu, đổi đơn vị, tràn số, giá trị không hữu hạn và trường hợp phải làm tròn.

**Quy tắc cốt lõi:** lựa chọn kiểu dữ liệu đúng bắt đầu từ **ý nghĩa và bất biến của miền dữ liệu**, sau đó mới xét phạm vi, cách biểu diễn, độ chính xác, phép tính và môi trường trao đổi. Kiểu giúp biểu diễn giá trị; validation và quy tắc nghiệp vụ quyết định giá trị đó có đúng trong hệ thống hay không.
