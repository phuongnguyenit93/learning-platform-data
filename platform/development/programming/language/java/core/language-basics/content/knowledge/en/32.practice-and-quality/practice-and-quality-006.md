# Kiểm tra trường hợp rỗng, biên, số âm, dữ liệu sai và giá trị lớn trong Java

Kiểm thử không chỉ xác nhận đầu vào thông thường chạy đúng. Một chương trình Java đáng tin cậy còn phải có **hành vi được xác định rõ** khi không có dữ liệu, dữ liệu nằm sát giới hạn, xuất hiện số âm, sai định dạng hoặc vượt khả năng biểu diễn của kiểu số. Những ca này cần được thiết kế từ **hợp đồng của chương trình** (đầu vào được chấp nhận, giới hạn, kết quả và lỗi mong đợi), thay vì thử các con số tùy ý.

Bài này dùng Java 17+ và một ví dụ xử lý **số lượng sản phẩm** hợp lệ trong đoạn `0..1_000_000`. Quy tắc minh họa: giá trị `0` hợp lệ; giá trị âm và lớn hơn `1_000_000` bị từ chối; đầu vào phải là một chuỗi biểu diễn số nguyên `int` hợp lệ, không tự cắt khoảng trắng. Với nghiệp vụ khác, các giới hạn có thể khác; cần nêu rõ trước khi viết test.

## 1. Phân loại đầu vào và đặt kết quả mong đợi

| Nhóm | Ví dụ đầu vào | Cần xác nhận |
| --- | --- | --- |
| Thiếu dữ liệu | `null` đối với tham chiếu `String` | Báo lỗi thiếu giá trị; không gọi phương thức của `null` |
| Chuỗi rỗng | `""` | Báo lỗi rõ ràng, không cố phân tích thành số |
| Chỉ khoảng trắng | `"   "` | Phân biệt với chuỗi chứa số hợp lệ |
| Cận dưới và lân cận | `-1`, `0`, `1` | `-1` bị từ chối, `0` và `1` hợp lệ |
| Cận trên và lân cận | `999999`, `1000000`, `1000001` | Hai số đầu hợp lệ, số cuối vượt giới hạn |
| Sai định dạng | `"12x"`, `"3.5"`, `" 5 "` | Không âm thầm chuyển thành dữ liệu khác; thông báo nhất quán |
| Ngoài miền biểu diễn `int` | `"2147483648"` | `Integer.parseInt` báo `NumberFormatException`; chương trình phải xử lý |
| Tính toán giá trị lớn | Giá `50_000` × số lượng `1_000_000` | Kết quả `50_000_000_000` cần `long` hoặc kiểu phù hợp, không được tràn `int` |

**Rỗng không có một nghĩa duy nhất:** `null` là không có đối tượng; `""` là `String` có độ dài 0; `"   "` không rỗng theo `isEmpty()` nhưng `isBlank()` trả `true`. Một danh sách rỗng (`List.isEmpty()`) hay mảng có `length == 0` lại là dữ liệu có cấu trúc, cần quy tắc kiểm tra riêng. Với kiểu nguyên thủy `int`, bản thân biến không nhận `null`; vấn đề thiếu dữ liệu thường xuất hiện trước khi chuyển đổi từ chuỗi hoặc qua `Integer`.

Không nên tự coi giá trị `0` là “chưa nhập”. Nó có thể là số lượng hợp lệ. Nếu muốn cấm `0`, hãy ghi thành quy tắc `1..MAX` và đổi toàn bộ test tương ứng.

## 2. Kiểm thử biên có hệ thống

Nếu miền hợp lệ là **`MIN <= x <= MAX`**, các ca có giá trị học tập cao gồm:

- `MIN - 1` (ngoài miền), `MIN` (trúng cận), `MIN + 1` (sát trong miền).
- `MAX - 1` (sát trong miền), `MAX` (trúng cận), `MAX + 1` (ngoài miền).
- Một giá trị bình thường nằm giữa miền, ví dụ `42`, để xác nhận đường đi chính.

Trong ví dụ `MIN=0`, `MAX=1_000_000`, các giá trị là `-1, 0, 1, 999999, 1000000, 1000001`. Hãy ghi rõ cận **bao gồm** (`<=`) hay **không bao gồm** (`<`); một ký tự toán tử sai có thể đổi kết quả ở đúng vị trí biên. Với phép tính cận lớn như `Integer.MAX_VALUE + 1`, không dùng phép cộng `int` khiến chính giá trị test bị tràn; chuẩn bị dữ liệu bằng `long`, `String` hoặc `BigInteger` phù hợp.

Kiểm tra số âm chỉ có ý nghĩa khi đầu vào có thể biểu diễn số âm. Nếu dữ liệu là tuổi, số lượng hay thời gian không âm, hành vi có thể là từ chối với lỗi xác định; nếu dữ liệu là nhiệt độ Celsius, số âm lại có thể hợp lệ. Vì vậy, **yêu cầu nghiệp vụ quyết định kết quả mong đợi**.

## 3. Dữ liệu sai và ngoại lệ

Khi đầu vào dạng chữ cần thành `int`, `Integer.parseInt(raw)` ném `NumberFormatException` nếu không thể phân tích hoặc giá trị vượt miền `int` (`-2147483648` đến `2147483647`). Đây là ngoại lệ con của `IllegalArgumentException`.

Một thiết kế kiểm tra rõ ràng thường đi theo trình tự:

1. Kiểm tra tham chiếu `null` và dữ liệu rỗng/trắng.
2. Phân tích đúng định dạng. Quyết định **trước** việc có `trim()`/chuẩn hóa dấu cách hay không; ví dụ này cố ý từ chối `" 5 "`.
3. Kiểm tra quy tắc miền giá trị: âm, vượt giới hạn, cận đóng/mở.
4. Chỉ thực hiện nghiệp vụ khi đầu vào đã hợp lệ; báo lỗi đủ rõ để nơi gọi xử lý.

Phân biệt dữ liệu **không hợp lệ theo định dạng** (`"12x"`) và **hợp lệ về số học nhưng sai chính sách** (`"1000001"`). Không dùng `catch (Exception)` rồi trả giá trị mặc định `0`: cách đó dễ che mất lỗi và khiến kết quả sai trông như thành công. Với ứng dụng thật, có thể trả kết quả lỗi cấu trúc hoặc ném ngoại lệ rồi xử lý ở lớp giao diện/API.

Lưu ý: dấu gạch dưới trong literal Java `1_000_000` giúp đọc **mã nguồn**, nhưng chuỗi đầu vào `"1_000_000"` không được `Integer.parseInt` chấp nhận. `"3.5"` cũng không phải chuỗi số nguyên, và ép sang `int` sau khi đọc `double` là một hành vi khác cần được đặc tả riêng.

## 4. Chương trình kiểm tra tự động bằng Java 17+

Lưu trọn chương trình sau vào tệp **`InputBoundaryChecks.java`** (không khai báo `package`). Các hàm `expectValid` và `expectInvalid` kiểm tra **cả đầu ra lẫn thông báo lỗi**; nếu hành vi thực tế không đúng, chúng ném `AssertionError`. Không cần bật JVM `-ea`.

```java
import java.math.BigInteger;

public final class InputBoundaryChecks {
    private static final int MAX_COUNT = 1_000_000;

    private InputBoundaryChecks() {
    }

    public static void main(String[] args) {
        expectInvalid("null", null, "thiếu giá trị");
        expectInvalid("rỗng", "", "rỗng hoặc chỉ khoảng trắng");
        expectInvalid("toàn khoảng trắng", "   ", "rỗng hoặc chỉ khoảng trắng");

        expectInvalid("âm -1", "-1", "phải không âm");
        expectValid("min 0", "0", 0);
        expectValid("min+1 1", "1", 1);
        expectValid("thông thường 42", "42", 42);
        expectValid("max-1 999999", "999999", 999_999);
        expectValid("max 1000000", "1000000", MAX_COUNT);
        expectInvalid("max+1 1000001", "1000001", "vượt 1000000");

        expectInvalid("sai chữ", "12x", "không phải int hợp lệ");
        expectInvalid("số thập phân", "3.5", "không phải int hợp lệ");
        expectInvalid("có khoảng trắng", " 5 ", "không phải int hợp lệ");
        expectInvalid("vượt int", "2147483648", "không phải int hợp lệ");

        checkLargeNumbers();
    }

    private static int parseCount(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("thiếu giá trị");
        }
        if (raw.isBlank()) {
            throw new IllegalArgumentException("rỗng hoặc chỉ khoảng trắng");
        }

        final int count;
        try {
            count = Integer.parseInt(raw);
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException("không phải int hợp lệ", e);
        }

        if (count < 0) {
            throw new IllegalArgumentException("phải không âm");
        }
        if (count > MAX_COUNT) {
            throw new IllegalArgumentException("vượt " + MAX_COUNT);
        }
        return count;
    }

    private static void expectValid(String name, String raw, int expected) {
        int actual = parseCount(raw);
        if (actual != expected) {
            throw new AssertionError(name + ": cần " + expected + ", nhận " + actual);
        }
        System.out.println(name + ": PASS -> " + actual);
    }

    private static void expectInvalid(
            String name, String raw, String expectedMessage) {
        try {
            parseCount(raw);
            throw new AssertionError(name + ": đáng lẽ phải báo lỗi");
        } catch (IllegalArgumentException e) {
            if (!expectedMessage.equals(e.getMessage())) {
                throw new AssertionError(name + ": sai thông báo lỗi", e);
            }
            System.out.println(name + ": PASS (" + e.getMessage() + ")");
        }
    }

    private static void checkLargeNumbers() {
        int unitPriceVnd = 50_000;
        int count = 1_000_000;

        try {
            Math.multiplyExact(unitPriceVnd, count);
            throw new AssertionError("phép nhân int phải bị tràn");
        } catch (ArithmeticException expected) {
            System.out.println("nhân int: PASS (phát hiện tràn)");
        }

        long totalPriceVnd = (long) unitPriceVnd * count;
        if (totalPriceVnd != 50_000_000_000L) {
            throw new AssertionError("sai thành tiền");
        }
        System.out.println("nhân long: " + totalPriceVnd);

        BigInteger aboveLongMax = BigInteger.valueOf(Long.MAX_VALUE)
                .add(BigInteger.ONE);
        System.out.println("BigInteger: " + aboveLongMax);
    }
}
```

Mở terminal ở thư mục chứa tệp, có JDK 17 trở lên:

```bash
javac -encoding UTF-8 InputBoundaryChecks.java
java InputBoundaryChecks
```

**Stdout chính xác khi tất cả ca kiểm tra đạt:**

```text
null: PASS (thiếu giá trị)
rỗng: PASS (rỗng hoặc chỉ khoảng trắng)
toàn khoảng trắng: PASS (rỗng hoặc chỉ khoảng trắng)
âm -1: PASS (phải không âm)
min 0: PASS -> 0
min+1 1: PASS -> 1
thông thường 42: PASS -> 42
max-1 999999: PASS -> 999999
max 1000000: PASS -> 1000000
max+1 1000001: PASS (vượt 1000000)
sai chữ: PASS (không phải int hợp lệ)
số thập phân: PASS (không phải int hợp lệ)
có khoảng trắng: PASS (không phải int hợp lệ)
vượt int: PASS (không phải int hợp lệ)
nhân int: PASS (phát hiện tràn)
nhân long: 50000000000
BigInteger: 9223372036854775808
```

Chương trình dùng `AssertionError` trực tiếp để mỗi ca sai làm chương trình thất bại ngay. `NumberFormatException` được bọc lại với thông báo theo hợp đồng của `parseCount`. `Math.multiplyExact(int, int)` phát hiện tràn bằng `ArithmeticException`; phép nhân `(long) unitPriceVnd * count` chuyển một toán hạng sang `long` **trước phép nhân**, nhận kết quả đúng `50_000_000_000`. `BigInteger` biểu diễn được giá trị lớn hơn `Long.MAX_VALUE`, nhưng trong ứng dụng vẫn cần giới hạn nghiệp vụ và bộ nhớ hợp lý.

## 5. Tràn số, kiểu dữ liệu và trường hợp đặc biệt

- `int` là số nguyên có dấu 32 bit, `long` là 64 bit. Phép cộng/nhân nguyên thường **không tự ném ngoại lệ khi tràn**; kết quả có thể bị cuốn vòng và sai. Dùng `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact`, `Math.toIntExact` khi cần phát hiện tràn.
- Ép kiểu **sau** phép tính đã tràn không cứu được dữ liệu: `long total = price * count;` vẫn nhân hai `int` trước. Chuyển ít nhất một toán hạng thành `long` trước phép toán nếu kết quả nằm trong miền `long`.
- Nếu có nguy cơ vượt cả `long`, dùng `BigInteger` cho số nguyên tùy độ lớn. Với tiền tệ có phần thập phân hoặc yêu cầu làm tròn, cân nhắc `BigDecimal` và quy tắc `RoundingMode` rõ ràng.
- Khi phải làm việc với số thực `double`/`float`, kiểm tra `NaN`, `Infinity`, độ chính xác và sai số làm tròn theo hợp đồng; không so sánh bằng tuyệt đối một cách máy móc trong bài toán xấp xỉ.
- Giá trị lớn còn có thể gây **tốn CPU/bộ nhớ** dù kiểu số vẫn chứa được; nên kiểm tra giới hạn kích thước dữ liệu, độ dài chuỗi, số phần tử hoặc độ lớn của đầu vào trước khi cấp phát.

## 6. Quy trình kiểm tra cho bài thực hành

1. Viết hợp đồng: kiểu đầu vào, giá trị có thể thiếu, cận bao gồm/loại trừ, quy tắc chuẩn hóa và hình thức báo lỗi.
2. Dựng bảng test theo lớp tương đương: **hợp lệ**, **rỗng/thiếu**, **ngoài cận**, **sai định dạng**, **vượt miền kiểu dữ liệu**, **tràn khi tính toán**.
3. Thêm các ca ngay **dưới, đúng và trên mỗi cận**; phân biệt `0` với `null` nếu chúng có nghĩa khác nhau.
4. Xác nhận đầu ra và loại/thông báo lỗi; các bài tập nhỏ có thể dùng runner như trên, dự án lớn có thể đưa cùng ca kiểm tra sang JUnit để tự chạy khi sửa mã.
5. Chạy lại sau thay đổi, nhất là khi đổi kiểu `int` sang `long`, thay giới hạn hoặc quyết định tự động `trim()` đầu vào. Test nên thất bại khi hành vi lệch khỏi hợp đồng.

**Các lỗi dễ mắc:** chỉ thử dữ liệu đẹp; bỏ sót `MIN` và `MAX`; dùng `==` để so nội dung `String` thay vì `equals`; gọi phương thức trên `null`; coi chuỗi trắng là chuỗi rỗng theo `isEmpty`; để phép tính tràn trước khi ép kiểu; nuốt ngoại lệ rồi trả `0`; hoặc viết test không có giá trị mong đợi cụ thể. Một bộ test ngắn nhưng có chủ đích về rỗng, biên, dữ liệu sai và giá trị lớn sẽ phát hiện được nhiều lỗi hơn số lượng lớn ví dụ ngẫu nhiên.